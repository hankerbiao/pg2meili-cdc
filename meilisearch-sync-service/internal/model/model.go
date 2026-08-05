package model

import (
	"crypto/sha256"
	"encoding/hex"
	"regexp"
)

var collectionPattern = regexp.MustCompile("^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

// IndexUID returns a stable, tenant-specific Meilisearch index name.
func IndexUID(appID, collection string) string {
	if appID == "" || !collectionPattern.MatchString(collection) {
		return ""
	}
	digest := sha256.Sum256([]byte(appID))
	return "t_" + hex.EncodeToString(digest[:])[:16] + "__" + collection
}

// DebeziumPayload 对应 Debezium CDC 消息中的 payload.before / payload.after / payload.op
type DebeziumPayload struct {
	Before map[string]interface{} `json:"before"`
	After  map[string]interface{} `json:"after"`
	Op     string                 `json:"op"`
}

// DebeziumMessage 是 Debezium 单条消息的顶层结构
type DebeziumMessage struct {
	Payload DebeziumPayload `json:"payload"`
}

// MeiliCommandPayload 表示索引设置变更所需字段集合。
// filterable/sortable 为既有覆盖语义（空数组=清空）；新增配置项用指针，
// nil 表示「未配置」——Go 侧不下发该字段，避免重置 Meilisearch 默认值。
type MeiliCommandPayload struct {
	FilterableAttributes       []string `json:"filterableAttributes"`
	SortableAttributes         []string `json:"sortableAttributes"`
	SearchableAttributes       []string `json:"searchableAttributes"`
	DisplayedAttributes        []string `json:"displayedAttributes"`
	DistinctAttribute          *string  `json:"distinctAttribute"`
	TypoToleranceEnabled       *bool    `json:"typoToleranceEnabled"`
	PaginationMaxTotalHits     *int64   `json:"paginationMaxTotalHits"`
	FacetingMaxValuesPerFacet  *int64   `json:"facetingMaxValuesPerFacet"`
}

// MeiliCommand 是跨地域同步的命令消息结构。
type MeiliCommand struct {
	Version    int                 `json:"version"`
	CommandID  string              `json:"command_id"`
	AppID      string              `json:"app_id"`
	Collection string              `json:"collection"`
	IndexUID   string              `json:"index_uid"`
	Action     string              `json:"action"`
	Payload    MeiliCommandPayload `json:"payload"`
	Ts         int64               `json:"ts"`
}

// SearchOutboxEvent is the stable CDC contract emitted by PostgreSQL.
type SearchOutboxEvent struct {
	EventID      string                 `json:"event_id"`
	AppID        string                 `json:"app_id"`
	Collection   string                 `json:"collection"`
	DocumentID   string                 `json:"document_id"`
	Operation    string                 `json:"operation"`
	Document     map[string]interface{} `json:"document"`
	EventVersion int64                  `json:"event_version"`
}
