package model

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

type SearchProxyRequest struct {
	IndexUID string      `json:"index_uid"`
	Q        string      `json:"q"`
	Offset   *int64      `json:"offset,omitempty"`
	Limit    *int64      `json:"limit,omitempty"`
	Filter   interface{} `json:"filter,omitempty"`
	Sort     []string    `json:"sort,omitempty"`
}

// MeiliCommandPayload 表示索引设置变更所需字段集合。
type MeiliCommandPayload struct {
	FilterableAttributes []string `json:"filterableAttributes"`
	SortableAttributes   []string `json:"sortableAttributes"`
}

// MeiliCommand 是跨地域同步的命令消息结构。
type MeiliCommand struct {
	Version   int                 `json:"version"`
	CommandID string              `json:"command_id"`
	IndexUID  string              `json:"index_uid"`
	Action    string              `json:"action"`
	Payload   MeiliCommandPayload `json:"payload"`
	Ts        int64               `json:"ts"`
}
