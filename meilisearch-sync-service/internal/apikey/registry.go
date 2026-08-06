package apikey

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"meilisearch-sync-service/internal/auth"
	"meilisearch-sync-service/internal/config"

	"github.com/redis/go-redis/v9"
)

const (
	appPrefix = "unidata:api-key:app:"
	keyPrefix = "unidata:api-key:key:"
)

type Registry struct {
	redis *redis.Client
}

type Event struct {
	Event           string   `json:"event"`
	AppID           string   `json:"app_id"`
	AppName         string   `json:"app_name"`
	KeyID           string   `json:"key_id"`
	SecretHash      string   `json:"secret_hash"`
	Scopes          []string `json:"scopes"`
	Status          string   `json:"status"`
	ExpiresAt       string   `json:"expires_at"`
	ResourceVersion int      `json:"resource_version"`
}

type snapshotResponse struct {
	Data struct {
		Apps []auth.AppRecord `json:"apps"`
		Keys []auth.KeyRecord `json:"keys"`
	} `json:"data"`
}

func New(cfg config.AppConfig) (*Registry, error) {
	client := redis.NewClient(&redis.Options{Addr: cfg.RedisAddr, Password: cfg.RedisPass, DB: cfg.RedisDB})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		_ = client.Close()
		return nil, fmt.Errorf("连接 API Key Redis: %w", err)
	}
	return &Registry{redis: client}, nil
}

func (r *Registry) Close() error { return r.redis.Close() }

func (r *Registry) Lookup(ctx context.Context, keyID string) (auth.KeyRecord, auth.AppRecord, error) {
	var key auth.KeyRecord
	if err := r.getRecord(ctx, keyPrefix+keyID, &key); err != nil {
		return auth.KeyRecord{}, auth.AppRecord{}, err
	}
	var app auth.AppRecord
	if err := r.getRecord(ctx, appPrefix+key.AppID, &app); err != nil {
		return auth.KeyRecord{}, auth.AppRecord{}, err
	}
	return key, app, nil
}

// AppStatus 返回本地注册表中应用的状态。记录不存在时返回 ("", false, nil)，
// 供 CDC 消费端做租户状态门禁：已删除/删除中的应用不再写入 Meilisearch，
// 避免在途消息复活已回收租户的索引。
func (r *Registry) AppStatus(ctx context.Context, appID string) (string, bool, error) {
	var app auth.AppRecord
	if err := r.getRecord(ctx, appPrefix+appID, &app); err != nil {
		if errors.Is(err, auth.ErrInvalidAPIKey) {
			return "", false, nil
		}
		return "", false, err
	}
	return app.Status, true, nil
}

func (r *Registry) getRecord(ctx context.Context, redisKey string, out interface{}) error {
	raw, err := r.redis.Get(ctx, redisKey).Bytes()
	if errors.Is(err, redis.Nil) {
		return auth.ErrInvalidAPIKey
	}
	if err != nil {
		return err
	}
	return json.Unmarshal(raw, out)
}

func (r *Registry) Apply(ctx context.Context, payload []byte) error {
	var event Event
	if err := json.Unmarshal(payload, &event); err != nil {
		return permanent(fmt.Errorf("解析 API Key 事件: %w", err))
	}
	switch event.Event {
	case "app.upsert":
		return r.storeApp(ctx, auth.AppRecord{ID: event.AppID, AppName: event.AppName, Status: event.Status, Version: event.ResourceVersion})
	case "key.upsert", "key.revoked":
		return r.storeKey(ctx, auth.KeyRecord{ID: event.KeyID, AppID: event.AppID, AppName: event.AppName, SecretHash: event.SecretHash, Scopes: event.Scopes, Status: event.Status, ExpiresAt: event.ExpiresAt, Version: event.ResourceVersion})
	default:
		return permanent(fmt.Errorf("未知 API Key 事件 %q", event.Event))
	}
}

func (r *Registry) storeApp(ctx context.Context, record auth.AppRecord) error {
	if record.ID == "" || record.Version <= 0 {
		return permanent(fmt.Errorf("应用事件缺少标识或版本"))
	}
	return r.storeNewer(ctx, appPrefix+record.ID, record.Version, record)
}

func (r *Registry) storeKey(ctx context.Context, record auth.KeyRecord) error {
	if record.ID == "" || record.AppID == "" || record.Version <= 0 {
		return permanent(fmt.Errorf("Key 事件缺少标识、应用或版本"))
	}
	return r.storeNewer(ctx, keyPrefix+record.ID, record.Version, record)
}

func (r *Registry) storeNewer(ctx context.Context, redisKey string, version int, value any) error {
	existing, err := r.redis.Get(ctx, redisKey).Bytes()
	if err == nil {
		var current struct {
			Version int `json:"resource_version"`
		}
		if json.Unmarshal(existing, &current) == nil && current.Version >= version {
			return nil
		}
	} else if !errors.Is(err, redis.Nil) {
		return err
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return err
	}
	return r.redis.Set(ctx, redisKey, encoded, 0).Err()
}

func (r *Registry) Warmup(ctx context.Context, cfg config.AppConfig) error {
	if strings.TrimSpace(cfg.UniDataURL) == "" || strings.TrimSpace(cfg.AgentRegistrationToken) == "" {
		return fmt.Errorf("API Key 快照需要 UNIDATA_URL 和 AGENT_REGISTRATION_TOKEN")
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, config.JoinURL(cfg.UniDataURL, "api/v1/internal/api-keys/snapshot"), nil)
	if err != nil {
		return err
	}
	request.Header.Set("X-Agent-Token", cfg.AgentRegistrationToken)
	response, err := (&http.Client{Timeout: 15 * time.Second}).Do(request)
	if err != nil {
		return fmt.Errorf("获取 API Key 快照: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("获取 API Key 快照状态码=%d", response.StatusCode)
	}
	var snapshot snapshotResponse
	if err := json.NewDecoder(response.Body).Decode(&snapshot); err != nil {
		return fmt.Errorf("解析 API Key 快照: %w", err)
	}
	if err := r.clearNamespace(ctx); err != nil {
		return err
	}
	for _, app := range snapshot.Data.Apps {
		if err := r.storeApp(ctx, app); err != nil {
			return err
		}
	}
	for _, key := range snapshot.Data.Keys {
		if err := r.storeKey(ctx, key); err != nil {
			return err
		}
	}
	return nil
}

func (r *Registry) clearNamespace(ctx context.Context) error {
	for _, pattern := range []string{appPrefix + "*", keyPrefix + "*"} {
		var cursor uint64
		for {
			keys, next, err := r.redis.Scan(ctx, cursor, pattern, 200).Result()
			if err != nil {
				return err
			}
			if len(keys) > 0 {
				if err := r.redis.Del(ctx, keys...).Err(); err != nil {
					return err
				}
			}
			cursor = next
			if cursor == 0 {
				break
			}
		}
	}
	return nil
}
