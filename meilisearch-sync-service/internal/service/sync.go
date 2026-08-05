package service

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/model"

	"github.com/twmb/franz-go/pkg/kgo"
)

const maxPollRecords = 50

// Run 是消息处理的主循环函数，负责持续消费 Kafka 消息并同步到 Meilisearch。
// handlers 由 App 层按 topic 注册，便于扩展不同类型的消息处理。
func Run(
	ctx context.Context,
	client *kgo.Client,
	cfg config.AppConfig,
	handlers map[string]RecordHandler,
) error {
	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}

		// 从 Kafka 拉取一批消息，如果有错误先记录日志再继续下一轮
		fetches := client.PollRecords(ctx, maxPollRecords)
		if errs := fetches.Errors(); len(errs) > 0 {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			for _, e := range errs {
				log.Printf("从 Kafka 拉取消息出错: %v", e)
			}
			continue
		}

		// 整批处理完成后再提交，失败时允许 Kafka 重新投递。
		iter := fetches.RecordIter()
		var records []*kgo.Record

		for !iter.Done() {
			record := iter.Next()

			handler := handlers[record.Topic]
			var handleErr error
			if handler == nil {
				handleErr = permanent(fmt.Errorf("未注册的 topic: %s", record.Topic))
			} else {
				handleErr = handler.Handle(ctx, record)
			}

			if handleErr != nil {
				if !isPermanent(handleErr) {
					return fmt.Errorf("处理可重试消息失败 topic=%s partition=%d offset=%d: %w", record.Topic, record.Partition, record.Offset, handleErr)
				}
				log.Printf("永久消息错误，写入 DLQ: %v", handleErr)
				if err := sendToDLQ(ctx, client, cfg, record, handleErr); err != nil {
					return fmt.Errorf("写入 DLQ 失败，保留原消息 offset: %w", err)
				}
			}
			records = append(records, record)
		}

		if len(records) > 0 {
			if err := client.CommitRecords(ctx, records...); err != nil {
				return fmt.Errorf("提交 Kafka offset 失败: %w", err)
			}
		}
	}
}

type DLQMessage struct {
	SourceTopic     string            `json:"source_topic"`
	SourcePartition int32             `json:"source_partition"`
	SourceOffset    int64             `json:"source_offset"`
	KeyBase64       string            `json:"key_base64,omitempty"`
	ValueBase64     string            `json:"value_base64,omitempty"`
	Error           string            `json:"error"`
	Ts              int64             `json:"ts"`
	Headers         map[string]string `json:"headers,omitempty"`
}

type recordProducer interface {
	ProduceSync(context.Context, ...*kgo.Record) kgo.ProduceResults
}

func sendToDLQ(ctx context.Context, client recordProducer, cfg config.AppConfig, record *kgo.Record, err error) error {
	if cfg.DLQTopic == "" {
		return fmt.Errorf("未配置 KAFKA_DLQ_TOPIC")
	}

	headers := make(map[string]string)
	for _, h := range record.Headers {
		headers[h.Key] = string(h.Value)
	}

	msg := DLQMessage{
		SourceTopic:     record.Topic,
		SourcePartition: record.Partition,
		SourceOffset:    record.Offset,
		KeyBase64:       base64.StdEncoding.EncodeToString(record.Key),
		ValueBase64:     base64.StdEncoding.EncodeToString(record.Value),
		Error:           err.Error(),
		Ts:              time.Now().Unix(),
		Headers:         headers,
	}

	payload, marshalErr := json.Marshal(msg)
	if marshalErr != nil {
		return fmt.Errorf("序列化 DLQ 消息失败: %w", marshalErr)
	}

	ctxSend, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	res := client.ProduceSync(ctxSend, &kgo.Record{
		Topic: cfg.DLQTopic,
		Value: payload,
		Key:   record.Key,
	})
	if err := res.FirstErr(); err != nil {
		return fmt.Errorf("发送 DLQ topic=%s: %w", cfg.DLQTopic, err)
	}
	return nil
}

// processDebeziumMessage 解析 Debezium 消息，抽取操作类型、文档内容和主键 id
func processDebeziumMessage(value []byte) (string, string, map[string]interface{}, string, error) {
	// Debezium 可能发送空消息或 "null"，表示该偏移无有效数据
	trimmed := bytes.TrimSpace(value)
	if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("null")) {
		return "", "", nil, "", nil
	}

	var msg model.DebeziumMessage
	if err := json.Unmarshal(value, &msg); err != nil {
		return "", "", nil, "", fmt.Errorf("解码 Debezium 消息失败: %w", err)
	}

	payload := msg.Payload

	// The physical-tenancy contract is an append-only search_outbox row. Its
	// operation field, rather than the source table operation, is authoritative.
	if payload.After != nil {
		if _, ok := payload.After["operation"]; ok {
			return processSearchOutbox(payload.After)
		}
	}

	// 根据 Debezium 的 op 字段进行分支：
	// c: create, r: read(快照), u: update, d: delete
	switch payload.Op {
	case "c", "r", "u":
		doc, id, err := extractDocument(payload)
		if err != nil {
			return "", "", nil, "", fmt.Errorf("提取文档失败: %w", err)
		}
		if id == "" {
			return "", "", nil, "", fmt.Errorf("插入/更新文档时 id 为空: %v", doc)
		}
		return payload.Op, id, doc, "", nil
	case "d":
		// 删除操作从 before 中取 id 作为主键
		if payload.Before == nil {
			return "", "", nil, "", fmt.Errorf("删除操作缺少 before 字段")
		}
		id, err := documentID(payload.Before)
		if err != nil {
			return "", "", nil, "", fmt.Errorf("删除操作主键无效: %w", err)
		}
		before := payload.Before
		before["id"] = id
		return payload.Op, "", before, id, nil
	default:
		return "", "", nil, "", fmt.Errorf("未知的操作类型 %q", payload.Op)
	}
}

func processSearchOutbox(after map[string]interface{}) (string, string, map[string]interface{}, string, error) {
	appID, ok := nonEmptyString(after["app_id"])
	if !ok {
		return "", "", nil, "", fmt.Errorf("outbox 事件缺少 app_id")
	}
	collection, ok := nonEmptyString(after["collection"])
	if !ok {
		return "", "", nil, "", fmt.Errorf("outbox 事件缺少 collection")
	}
	documentID, err := scalarString(after["document_id"])
	if err != nil || strings.TrimSpace(documentID) == "" {
		return "", "", nil, "", fmt.Errorf("outbox 事件缺少 document_id")
	}
	operation, ok := nonEmptyString(after["operation"])
	if !ok {
		return "", "", nil, "", fmt.Errorf("outbox 事件缺少 operation")
	}

	route := map[string]interface{}{
		"app_id":     appID,
		"collection": collection,
		"id":         documentID,
	}
	switch operation {
	case "upsert":
		raw, exists := after["document"]
		if !exists || raw == nil {
			return "", "", nil, "", fmt.Errorf("outbox upsert 事件缺少 document")
		}
		document, ok := raw.(map[string]interface{})
		if !ok {
			return "", "", nil, "", fmt.Errorf("outbox document 必须是对象")
		}
		document["id"] = documentID
		document["app_id"] = appID
		document["collection"] = collection
		return "c", documentID, document, "", nil
	case "delete":
		return "d", "", route, documentID, nil
	default:
		return "", "", nil, "", fmt.Errorf("outbox operation 无效: %q", operation)
	}
}

// isDeleted 根据 is_delete 字段判断文档是否被标记删除，兼容多种类型
func isDeleted(doc map[string]interface{}) bool {
	if doc == nil {
		return false
	}
	if v, ok := doc["is_delete"]; ok {
		if b, ok := v.(bool); ok {
			return b
		}
		s := fmt.Sprint(v)
		return s == "true" || s == "1"
	}
	return false
}

// ResolveIndex 根据不可变 app_id 和 collection 计算索引名称。
func ResolveIndex(doc map[string]interface{}) string {
	if doc == nil {
		return ""
	}
	appID, appOK := nonEmptyString(doc["app_id"])
	collection, collectionOK := nonEmptyString(doc["collection"])
	if !appOK || !collectionOK {
		return ""
	}

	return model.IndexUID(appID, collection)
}

// extractDocument 从 DebeziumPayload 中抽取实际业务文档和主键 id
func extractDocument(p model.DebeziumPayload) (map[string]interface{}, string, error) {
	if p.After == nil {
		return nil, "", fmt.Errorf("After 字段为空")
	}

	base := p.After

	var doc map[string]interface{}

	// 支持 payload 嵌套字段：payload 可以是字符串（再包一层 JSON）或对象
	if raw, ok := base["payload"]; ok {
		switch v := raw.(type) {
		case string:
			if err := json.Unmarshal([]byte(v), &doc); err != nil {
				return nil, "", fmt.Errorf("解析内层 payload 字符串失败: %w", err)
			}
		case map[string]interface{}:
			doc = v
		default:
			return nil, "", fmt.Errorf("内层 payload 必须是 JSON 字符串或对象")
		}
	} else {
		// 兼容 doc 字段或直接使用 After 作为文档
		if inner, ok := base["doc"].(map[string]interface{}); ok {
			doc = inner
		} else {
			doc = base
		}
	}

	if doc == nil {
		return nil, "", fmt.Errorf("文档 payload 不能为空")
	}
	id, err := documentID(doc)
	if err != nil {
		id, err = documentID(base)
		if err != nil {
			return nil, "", err
		}
	}

	// 确保最终文档中一定带有 id 字段
	if id != "" {
		doc["id"] = id
	}

	// 保留路由与删除标记字段，供上层逻辑判断和路由
	if v, ok := base["is_delete"]; ok {
		doc["is_delete"] = v
	}
	if v, ok := base["app_id"]; ok {
		doc["app_id"] = v
	}
	if v, ok := base["collection"]; ok {
		doc["collection"] = v
	}

	return doc, id, nil
}

func documentID(doc map[string]interface{}) (string, error) {
	value, ok := doc["id"]
	if !ok || value == nil {
		return "", fmt.Errorf("缺少 id")
	}
	var id string
	switch value := value.(type) {
	case string:
		id = value
	case json.Number:
		id = value.String()
	case float64, float32, int, int8, int16, int32, int64, uint, uint8, uint16, uint32, uint64:
		id = fmt.Sprint(value)
	default:
		return "", fmt.Errorf("id 类型无效: %T", value)
	}
	if strings.TrimSpace(id) == "" {
		return "", fmt.Errorf("id 不能为空")
	}
	return id, nil
}

func scalarString(value interface{}) (string, error) {
	switch value := value.(type) {
	case string:
		return value, nil
	case json.Number:
		return value.String(), nil
	case float64, float32, int, int8, int16, int32, int64, uint, uint8, uint16, uint32, uint64:
		return fmt.Sprint(value), nil
	default:
		return "", fmt.Errorf("标识字段类型无效: %T", value)
	}
}

func nonEmptyString(value interface{}) (string, bool) {
	text, ok := value.(string)
	return text, ok && strings.TrimSpace(text) != ""
}
