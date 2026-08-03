package model

import "testing"

func TestIndexUID(t *testing.T) {
	if got := IndexUID("test-app", "requirements"); got != "test-app_requirements" {
		t.Fatalf("unexpected index UID: %s", got)
	}
}
