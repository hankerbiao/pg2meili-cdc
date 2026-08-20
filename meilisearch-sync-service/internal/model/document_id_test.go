package model

import (
	"encoding/base64"
	"regexp"
	"testing"
)

func TestMeiliDocumentIDIsStableAndMeilisearchCompatible(t *testing.T) {
	valid := regexp.MustCompile(`^[A-Za-z0-9_-]+$`)
	seen := map[string]string{}
	for _, rawID := range []string{"part:54000762", "faq:2003", "a-b_c", "a:b:c", "中文:42", ""} {
		got := MeiliDocumentID(rawID)
		if !valid.MatchString(got) {
			t.Fatalf("MeiliDocumentID(%q) = %q, contains unsupported characters", rawID, got)
		}
		if previous, exists := seen[got]; exists && previous != rawID {
			t.Fatalf("IDs %q and %q collided as %q", previous, rawID, got)
		}
		seen[got] = rawID
		decoded, err := base64.RawURLEncoding.DecodeString(got[2:])
		if err != nil {
			t.Fatalf("MeiliDocumentID(%q) is not decodable: %v", rawID, err)
		}
		if string(decoded) != rawID {
			t.Fatalf("MeiliDocumentID(%q) decoded as %q", rawID, decoded)
		}
	}
}
