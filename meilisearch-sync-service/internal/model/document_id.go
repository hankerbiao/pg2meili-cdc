package model

import "encoding/base64"

// MeiliDocumentID returns the stable, Meilisearch-compatible primary key for a
// business document ID. Raw URL-safe base64 is injective and only uses the
// characters accepted by Meilisearch (letters, digits, '-' and '_').
func MeiliDocumentID(rawID string) string {
	return "d_" + base64.RawURLEncoding.EncodeToString([]byte(rawID))
}
