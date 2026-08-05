package auth

import (
	"context"
	"crypto/sha256"
	"fmt"
	"testing"
	"time"
)

const testSecret = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"

type testStore struct {
	key KeyRecord
	app AppRecord
	err error
}

func (s testStore) Lookup(context.Context, string) (KeyRecord, AppRecord, error) {
	return s.key, s.app, s.err
}

func validStore() testStore {
	return testStore{
		key: KeyRecord{ID: "ak_0123456789abcdef", AppID: "app-id", SecretHash: fmt.Sprintf("%x", sha256.Sum256([]byte(testSecret))), Scopes: []string{"search:read"}, Status: "active", ExpiresAt: time.Now().Add(time.Hour).UTC().Format(time.RFC3339), Version: 1},
		app: AppRecord{ID: "app-id", AppName: "test-app", Status: "active", Version: 1},
	}
}

func TestIdentityFromAPIKey(t *testing.T) {
	identity, err := IdentityFromAPIKey(context.Background(), "ud_live_ak_0123456789abcdef."+testSecret, validStore())
	if err != nil {
		t.Fatalf("authenticate: %v", err)
	}
	if identity.AppID != "app-id" || identity.AppName != "test-app" || identity.KeyID != "ak_0123456789abcdef" {
		t.Fatalf("unexpected identity: %+v", identity)
	}
}

func TestIdentityFromAPIKeyRejectsAppMismatch(t *testing.T) {
	store := validStore()
	store.key.AppID = "other-app"
	if _, err := IdentityFromAPIKey(context.Background(), "ud_live_ak_0123456789abcdef."+testSecret, store); err == nil {
		t.Fatal("expected app mismatch rejection")
	}
}

func TestIdentityFromAPIKeyRejectsJWT(t *testing.T) {
	if _, err := IdentityFromAPIKey(context.Background(), "eyJhbGciOiJIUzI1NiJ9.payload.signature", validStore()); err == nil {
		t.Fatal("expected legacy JWT to be rejected")
	}
}

func TestIdentityFromAPIKeyRejectsExpiredAndRevoked(t *testing.T) {
	store := validStore()
	store.key.ExpiresAt = time.Now().Add(-time.Minute).UTC().Format(time.RFC3339)
	if _, err := IdentityFromAPIKey(context.Background(), "ud_live_ak_0123456789abcdef."+testSecret, store); err == nil {
		t.Fatal("expected expired key rejection")
	}
	store = validStore()
	store.key.Status = "revoked"
	if _, err := IdentityFromAPIKey(context.Background(), "ud_live_ak_0123456789abcdef."+testSecret, store); err == nil {
		t.Fatal("expected revoked key rejection")
	}
}
