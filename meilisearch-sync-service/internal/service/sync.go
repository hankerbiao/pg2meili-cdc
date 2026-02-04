package service

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/model"

	"github.com/meilisearch/meilisearch-go"
	"github.com/twmb/franz-go/pkg/kgo"
)

// Run 是消息处理的主循环函数，负责持续消费 Kafka 消息并同步到 Meilisearch。
// handlers 由 App 层按 topic 注册，便于扩展不同类型的消息处理。
func Run(
	ctx context.Context,
	client *kgo.Client,
	meiliClient meilisearch.ServiceManager,
	cfg config.AppConfig,
	handlers map[string]RecordHandler,
) error {
	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}

		// 从 Kafka 拉取一批消息，如果有错误先记录日志再继续下一轮
		fetches := client.PollFetches(ctx)
		if errs := fetches.Errors(); len(errs) > 0 {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			for _, e := range errs {
				log.Printf("从 Kafka 拉取消息出错: %v", e)
			}
			continue
		}

		// 遍历本批次消息，同时累积记录用于后续提交 offset
		iter := fetches.RecordIter()
		var records []*kgo.Record

		for !iter.Done() {
			record := iter.Next()
			records = append(records, record)

			handler := handlers[record.Topic]
			if handler == nil {
				log.Printf("未注册的 topic，跳过处理 topic=%s partition=%d offset=%d", record.Topic, record.Partition, record.Offset)
				continue
			}
			if err := handler.Handle(ctx, record); err != nil {
				log.Printf("处理消息出错: %v", err)
				sendToDLQ(ctx, client, cfg, record, err)
				continue
			}
		}

		if len(records) > 0 {
			client.CommitRecords(ctx, records...)
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

func sendToDLQ(ctx context.Context, client *kgo.Client, cfg config.AppConfig, record *kgo.Record, err error) {
	// 仅在配置了 DLQ topic 时写入失败消息。
	if cfg.DLQTopic == "" {
		return
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
		log.Printf("DLQ 消息序列化失败: %v", marshalErr)
		return
	}

	ctxSend, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	res := client.ProduceSync(ctxSend, &kgo.Record{
		Topic: cfg.DLQTopic,
		Value: payload,
		Key:   record.Key,
	})
	if res.FirstErr() != nil {
		log.Printf("DLQ 发送失败 topic=%s err=%v", cfg.DLQTopic, res.FirstErr())
	}
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
		id := fmt.Sprint(payload.Before["id"])
		if id == "" {
			return "", "", nil, "", fmt.Errorf("删除操作 payload 中 id 为空: %v", payload.Before)
		}
		before := payload.Before
		before["id"] = id
		return payload.Op, "", before, id, nil
	default:
		return "", "", nil, "", fmt.Errorf("未知的操作类型 %q", payload.Op)
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

// ResolveIndex 根据文档中的 app_name 和 collection 计算索引名称
func ResolveIndex(doc map[string]interface{}) string {
	if doc == nil {
		return ""
	}

	appName := ""
	if v, ok := doc["app_name"]; ok {
		appName = fmt.Sprint(v)
	}

	collection := ""
	if v, ok := doc["collection"]; ok {
		collection = fmt.Sprint(v)
	}

	if appName == "" || collection == "" {
		return ""
	}

	return appName + "_" + collection
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
			doc = map[string]interface{}{}
		}
	} else {
		// 兼容 doc 字段或直接使用 After 作为文档
		if inner, ok := base["doc"].(map[string]interface{}); ok {
			doc = inner
		} else {
			doc = base
		}
	}

	id := ""
	if v, ok := doc["id"]; ok {
		id = fmt.Sprint(v)
	} else if v, ok := base["id"]; ok {
		id = fmt.Sprint(v)
	}

	// 确保最终文档中一定带有 id 字段
	if id != "" {
		doc["id"] = id
	}

	// 保留路由与删除标记字段，供上层逻辑判断和路由
	if v, ok := base["is_delete"]; ok {
		doc["is_delete"] = v
	}
	if v, ok := base["app_name"]; ok {
		doc["app_name"] = v
	}
	if v, ok := base["collection"]; ok {
		doc["collection"] = v
	}

	return doc, id, nil
}
