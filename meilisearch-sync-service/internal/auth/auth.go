package auth

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"
)

var apiKeyPattern = regexp.MustCompile(`^ud_live_(ak_[0-9a-f]{16})\.([A-Za-z0-9_-]{40,64})$`)

var (
	ErrInvalidAPIKey   = errors.New("API Key 无效")
	ErrAuthUnavailable = errors.New("鉴权服务不可用")
)

type AppRecord struct {
	ID      string `json:"app_id"`
	AppName string `json:"app_name"`
	Status  string `json:"status"`
	Version int    `json:"resource_version"`
}

type KeyRecord struct {
	ID         string   `json:"key_id"`
	AppID      string   `json:"app_id"`
	AppName    string   `json:"app_name"`
	SecretHash string   `json:"secret_hash"`
	Scopes     []string `json:"scopes"`
	Status     string   `json:"status"`
	ExpiresAt  string   `json:"expires_at"`
	Version    int      `json:"resource_version"`
}

type CredentialStore interface {
	Lookup(context.Context, string) (KeyRecord, AppRecord, error)
}

type AppIdentity struct {
	AppID   string
	AppName string
	Scopes  []string
	KeyID   string
}

func RequireScopes(identity AppIdentity, required []string) error {
	scopeSet := make(map[string]struct{}, len(identity.Scopes))
	for _, scope := range identity.Scopes {
		scopeSet[scope] = struct{}{}
	}
	for _, scope := range required {
		if _, ok := scopeSet[scope]; !ok {
			return fmt.Errorf("缺少权限: %s", scope)
		}
	}
	return nil
}

func ParseAPIKey(value string) (string, string, error) {
	match := apiKeyPattern.FindStringSubmatch(strings.TrimSpace(value))
	if len(match) != 3 {
		return "", "", ErrInvalidAPIKey
	}
	return match[1], match[2], nil
}

func IdentityFromAPIKey(ctx context.Context, credential string, store CredentialStore) (AppIdentity, error) {
	keyID, secret, err := ParseAPIKey(credential)
	if err != nil {
		return AppIdentity{}, ErrInvalidAPIKey
	}
	if store == nil {
		return AppIdentity{}, ErrAuthUnavailable
	}
	key, app, err := store.Lookup(ctx, keyID)
	if err != nil {
		if errors.Is(err, ErrInvalidAPIKey) {
			return AppIdentity{}, ErrInvalidAPIKey
		}
		return AppIdentity{}, fmt.Errorf("%w: %v", ErrAuthUnavailable, err)
	}
	expiresAt, err := time.Parse(time.RFC3339, key.ExpiresAt)
	if err != nil || key.Status != "active" || app.Status != "active" || !expiresAt.After(time.Now()) {
		return AppIdentity{}, ErrInvalidAPIKey
	}
	digest := fmt.Sprintf("%x", sha256.Sum256([]byte(secret)))
	if subtle.ConstantTimeCompare([]byte(digest), []byte(key.SecretHash)) != 1 {
		return AppIdentity{}, ErrInvalidAPIKey
	}
	if strings.TrimSpace(app.ID) == "" || strings.TrimSpace(key.AppID) == "" || app.ID != key.AppID {
		return AppIdentity{}, ErrInvalidAPIKey
	}
	return AppIdentity{AppID: app.ID, AppName: app.AppName, Scopes: key.Scopes, KeyID: key.ID}, nil
}
