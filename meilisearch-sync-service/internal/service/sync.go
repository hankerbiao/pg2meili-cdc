package service

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"sort"
	"strings"
	"time"

	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/model"

	"github.com/twmb/franz-go/pkg/kgo"
)

const (
	maxPollRecords = 50
	retryBackoff   = time.Second

	// Kafka metadata errors (for example UNKNOWN_TOPIC_ID) can be returned
	// for every subscribed partition while brokers converge.  Polling without
	// a delay turns a transient broker condition into a tight log-producing loop.
	fetchErrorInitialBackoff = time.Second
	fetchErrorMaxBackoff     = 30 * time.Second
	fetchErrorLogInterval    = time.Minute
)

type recordPartition struct {
	topic     string
	partition int32
}

// Run 是消息处理的主循环函数，负责持续消费 Kafka 消息并同步到 Meilisearch。
// handlers 由 App 层按 topic 注册，便于扩展不同类型的消息处理。
func Run(
	ctx context.Context,
	client *kgo.Client,
	cfg config.AppConfig,
	handlers map[string]RecordHandler,
) error {
	fetchErrorBackoff := fetchErrorInitialBackoff
	lastFetchError := ""
	lastFetchLog := time.Time{}
	var suppressedFetchErrors int

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
			message := summarizeFetchErrors(errs)
			now := time.Now()
			if message != lastFetchError {
				lastFetchError = message
				lastFetchLog = now
				suppressedFetchErrors = 0
				log.Printf("从 Kafka 拉取消息出错（%d条，%s后重试）: %s", len(errs), fetchErrorBackoff, message)
			} else {
				suppressedFetchErrors += len(errs)
				if now.Sub(lastFetchLog) >= fetchErrorLogInterval {
					log.Printf("从 Kafka 拉取消息仍然失败（本次%d条，期间抑制%d条，%s后重试）: %s", len(errs), suppressedFetchErrors, fetchErrorBackoff, message)
					lastFetchLog = now
					suppressedFetchErrors = 0
				}
			}
			if err := waitForRetry(ctx, fetchErrorBackoff); err != nil {
				return err
			}
			if fetchErrorBackoff < fetchErrorMaxBackoff {
				fetchErrorBackoff *= 2
				if fetchErrorBackoff > fetchErrorMaxBackoff {
					fetchErrorBackoff = fetchErrorMaxBackoff
				}
			}
			continue
		}
		if !fetches.Empty() {
			fetchErrorBackoff = fetchErrorInitialBackoff
			lastFetchError = ""
			suppressedFetchErrors = 0
		}

		// 整批处理完成后再提交，失败时允许 Kafka 重新投递。
		iter := fetches.RecordIter()
		var records []*kgo.Record
		retry := false
		blocked := make(map[recordPartition]struct{})

		for !iter.Done() {
			record := iter.Next()
			partition := recordPartition{topic: record.Topic, partition: record.Partition}
			if _, ok := blocked[partition]; ok {
				continue
			}

			handler := handlers[record.Topic]
			var handleErr error
			if handler == nil {
				handleErr = permanent(fmt.Errorf("未注册的 topic: %s", record.Topic))
			} else {
				handleErr = handler.Handle(ctx, record)
			}

			if handleErr != nil {
				if !isPermanent(handleErr) {
					if ctx.Err() != nil {
						return ctx.Err()
					}
					log.Printf("处理消息失败，将重试 topic=%s partition=%d offset=%d: %v", record.Topic, record.Partition, record.Offset, handleErr)
					blocked[partition] = struct{}{}
					retry = true
					continue
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

		if retry {
			timer := time.NewTimer(retryBackoff)
			select {
			case <-ctx.Done():
				timer.Stop()
				return ctx.Err()
			case <-timer.C:
			}
		}
	}
}

func waitForRetry(ctx context.Context, delay time.Duration) error {
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func summarizeFetchErrors(errs []kgo.FetchError) string {
	counts := make(map[string]int, len(errs))
	for _, err := range errs {
		message := fmt.Sprintf("%s %v", err.Topic, err.Err)
		counts[message]++
	}
	keys := make([]string, 0, len(counts))
	for message := range counts {
		keys = append(keys, message)
	}
	sort.Strings(keys)
	parts := make([]string, 0, len(keys))
	for _, message := range keys {
		if counts[message] == 1 {
			parts = append(parts, message)
		} else {
			parts = append(parts, fmt.Sprintf("%s（x%d）", message, counts[message]))
		}
	}
	return strings.Join(parts, "; ")
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

// processDebeziumMessage 解包 search_outbox 的 Debezium 事件。
// 业务表不再直接进入 Kafka；search_outbox 的 operation 字段是唯一协议来源。
func processDebeziumMessage(value []byte) (string, string, map[string]interface{}, string, int64, string, error) {
	trimmed := bytes.TrimSpace(value)
	if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("null")) {
		return "", "", nil, "", 0, "", nil
	}

	var msg model.DebeziumMessage
	if err := json.Unmarshal(value, &msg); err != nil {
		return "", "", nil, "", 0, "", fmt.Errorf("解码 Debezium 消息失败: %w", err)
	}

	if msg.Payload.After == nil {
		return "", "", nil, "", 0, "", fmt.Errorf("search_outbox 事件缺少 after")
	}
	return processSearchOutbox(msg.Payload.After)
}

func processSearchOutbox(after map[string]interface{}) (string, string, map[string]interface{}, string, int64, string, error) {
	revision, epoch := extractRevisionEpoch(after)
	appID, ok := nonEmptyString(after["app_id"])
	if !ok {
		return "", "", nil, "", 0, "", fmt.Errorf("outbox 事件缺少 app_id")
	}
	collection, ok := nonEmptyString(after["collection"])
	if !ok {
		return "", "", nil, "", 0, "", fmt.Errorf("outbox 事件缺少 collection")
	}
	documentID, err := scalarString(after["document_id"])
	if err != nil || strings.TrimSpace(documentID) == "" {
		return "", "", nil, "", 0, "", fmt.Errorf("outbox 事件缺少 document_id")
	}
	operation, ok := nonEmptyString(after["operation"])
	if !ok {
		return "", "", nil, "", 0, "", fmt.Errorf("outbox 事件缺少 operation")
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
			return "", "", nil, "", 0, "", fmt.Errorf("outbox upsert 事件缺少 document")
		}
		var document map[string]interface{}
		// Debezium JsonConverter with schemas.enable=true serializes the
		// io.debezium.data.Json document column as a JSON string.
		if docStr, ok := raw.(string); ok {
			if err := json.Unmarshal([]byte(docStr), &document); err != nil {
				return "", "", nil, "", 0, "", fmt.Errorf("outbox document 必须是对象")
			}
		} else if docMap, ok := raw.(map[string]interface{}); ok {
			document = docMap
		} else {
			return "", "", nil, "", 0, "", fmt.Errorf("outbox document 必须是对象")
		}
		document["id"] = documentID
		document["_meili_id"] = model.MeiliDocumentID(documentID)
		document["app_id"] = appID
		document["collection"] = collection
		return "c", documentID, document, "", revision, epoch, nil
	case "delete":
		return "d", "", route, documentID, revision, epoch, nil
	default:
		return "", "", nil, "", 0, "", fmt.Errorf("outbox operation 无效: %q", operation)
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
