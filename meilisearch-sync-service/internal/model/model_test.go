package model

import (
	"crypto/sha256"
	"encoding/hex"
	"testing"
)

func TestIndexUID(t *testing.T) {
	digest := sha256.Sum256([]byte("test-app"))
	want := "t_" + hex.EncodeToString(digest[:])[:16] + "__requirements"
	if got := IndexUID("test-app", "requirements"); got != want {
		t.Fatalf("unexpected index UID: %s, want %s", got, want)
	}
}

func TestIndexUIDRejectsInvalidRoute(t *testing.T) {
	for _, test := range []struct {
		appID      string
		collection string
	}{
		{appID: "", collection: "requirements"},
		{appID: "app-a", collection: "../requirements"},
		{appID: "app-a", collection: "requirement with space"},
	} {
		if got := IndexUID(test.appID, test.collection); got != "" {
			t.Fatalf("IndexUID(%q, %q) = %q, want empty", test.appID, test.collection, got)
		}
	}
}
