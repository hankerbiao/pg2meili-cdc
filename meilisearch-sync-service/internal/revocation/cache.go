package revocation

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"time"

	"meilisearch-sync-service/internal/config"

	"github.com/redis/go-redis/v9"
)

// Cache 封装了基于 Redis 的吊销列表缓存。
// 设计目标：
// 1）Redis 作为权威数据源，保证吊销信息在多实例之间共享；
// 2）本地内存作为读缓存，减少对 Redis 的频繁访问，降低延迟；
// 3）通过 TTL 控制单个吊销记录的有效期，避免数据无限增长。
type Cache struct {
	// redis 是底层 Redis 客户端，用于持久化存储吊销记录。
	redis *redis.Client
	// ttl 是单条吊销记录在 Redis 和本地缓存中的默认生存时间。
	ttl time.Duration
	// mu 保护 local，本地缓存需要并发读写。
	mu sync.RWMutex
	// local 是基于进程内的本地缓存，key 通常为 jti，value 为过期时间点。
	local map[string]time.Time
}

// NewCache 基于应用配置创建一个新的 Cache 实例。
// 会立即对 Redis 做一次 Ping，用于在启动阶段尽早发现连接问题。
func NewCache(cfg config.AppConfig) (*Cache, error) {
	redisClient := redis.NewClient(&redis.Options{
		Addr:     cfg.RedisAddr,
		Password: cfg.RedisPass,
		DB:       cfg.RedisDB,
	})
	if err := redisClient.Ping(context.Background()).Err(); err != nil {
		return nil, err
	}
	return &Cache{
		redis: redisClient,
		ttl:   time.Duration(cfg.RevokeTTL) * time.Second,
		local: make(map[string]time.Time),
	}, nil
}

// Close 关闭底层 Redis 客户端。
func (c *Cache) Close() error {
	return c.redis.Close()
}

// key 统一封装 Redis 中使用的 key 前缀约定。
// 所有吊销记录在 Redis 中都以 "revoked:{jti}" 形式存储，便于 Scan 与管理。
func (c *Cache) key(jti string) string {
	return "revoked:" + jti
}

// Warmup 会在服务启动时从 Redis 扫描所有已存在的吊销 key，
// 并按照当前 TTL 设置预热到本地缓存中。
// 这样服务启动后即可利用本地缓存进行快速判断，减少冷启动时对 Redis 的压力。
func (c *Cache) Warmup(ctx context.Context) error {
	var cursor uint64
	for {
		// 使用 Scan 遍历所有符合前缀的 key，避免一次性全量拉取。
		keys, nextCursor, err := c.redis.Scan(ctx, cursor, "revoked:*", 200).Result()
		if err != nil {
			return err
		}
		now := time.Now()
		for _, key := range keys {
			// 从 Redis key 中截取出业务层使用的 jti。
			jti := strings.TrimPrefix(key, "revoked:")
			ttl, err := c.redis.TTL(ctx, key).Result()
			if err != nil {
				return err
			}
			// 默认使用配置的 revoke TTL；若 ttl<=0 则视为永久。
			exp := time.Time{}
			if c.ttl > 0 {
				exp = now.Add(c.ttl)
				if ttl > 0 {
					exp = now.Add(ttl)
				}
			}
			c.mu.Lock()
			c.local[jti] = exp
			c.mu.Unlock()
		}
		cursor = nextCursor
		if cursor == 0 {
			break
		}
	}
	return nil
}

// IsRevoked 判断给定 jti 是否已经被吊销。
// 返回值：
//   - true, nil  表示该 jti 在吊销列表中；
//   - false, nil 表示当前未被吊销；
//   - false, err 表示查询过程中出现底层错误（例如 Redis 访问失败）。
func (c *Cache) IsRevoked(ctx context.Context, jti string) (bool, error) {
	if jti == "" {
		// 空 jti 视为未吊销，调用方可以根据业务需要做进一步校验。
		return false, nil
	}

	now := time.Now()

	// 1. 优先从本地缓存中查询，命中则快速返回，减少对 Redis 的访问。
	c.mu.RLock()
	exp, ok := c.local[jti]
	c.mu.RUnlock()
	if ok {
		// 未过期或永久有效则认为已吊销。
		if exp.IsZero() || exp.After(now) {
			return true, nil
		}
		// 已过期则从本地缓存中删除，后续走 Redis 查询。
		c.mu.Lock()
		delete(c.local, jti)
		c.mu.Unlock()
	}

	// 2. 本地未命中或已过期，回源 Redis 做一次确认。
	val, err := c.redis.Get(ctx, c.key(jti)).Result()
	if err == nil {
		// Redis 中存在记录，说明确实已吊销。
		// 同时将结果写入本地缓存，并设置新的过期时间窗口。
		exp := time.Time{}
		if c.ttl > 0 {
			exp = now.Add(c.ttl)
		}
		c.mu.Lock()
		c.local[jti] = exp
		c.mu.Unlock()
		_ = val
		return true, nil
	}
	// redis.Nil 表示 key 不存在，对调用方来说即为“未吊销”。
	if errors.Is(err, redis.Nil) {
		return false, nil
	}
	// 其他错误（网络异常、超时等）向上传递，由上层决定降级策略。
	return false, err
}

// MarkRevoked 将指定 jti 标记为已吊销。
// 会同时更新本地缓存与 Redis，确保多实例之间最终一致。
func (c *Cache) MarkRevoked(ctx context.Context, jti string, payload RevocationEvent) error {
	if jti == "" {
		// 没有有效 jti 不做任何操作。
		return nil
	}

	// 1. 更新本地缓存中的过期时间，使后续查询可以立即命中。
	exp := time.Time{}
	if c.ttl > 0 {
		exp = time.Now().Add(c.ttl)
	}
	c.mu.Lock()
	c.local[jti] = exp
	c.mu.Unlock()

	// 2. 将吊销事件序列化后写入 Redis，TTL 使用统一配置（ttl<=0 表示永久）。
	// value 目前主要用于调试与排查，例如记录是谁在何时吊销的该令牌。
	value, _ := json.Marshal(payload)
	var ttl time.Duration
	if c.ttl > 0 {
		ttl = c.ttl
	}
	return c.redis.Set(ctx, c.key(jti), value, ttl).Err()
}
