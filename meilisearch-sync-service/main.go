package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"github.com/joho/godotenv"
	"github.com/meilisearch/meilisearch-go"
	"github.com/twmb/franz-go/pkg/kgo"
)

// DebeziumPayload 对应 Debezium CDC 消息中的 payload.before / payload.after / payload.op
// - Before: 更新 / 删除前的行数据
// - After : 插入 / 更新后的行数据
// - Op    : 操作类型 (c=create, u=update, d=delete, r=snapshot)
type DebeziumPayload struct {
	Before map[string]interface{} `json:"before"`
	After  map[string]interface{} `json:"after"`
	Op     string                 `json:"op"`
}

// DebeziumMessage 是 Debezium 单条消息的顶层结构
type DebeziumMessage struct {
	Payload DebeziumPayload `json:"payload"`
}

type AppConfig struct {
	Brokers         []string
	Topics          []string
	GroupID         string
	MeiliHost       string
	MeiliAPIKey     string
	MeiliIndex      string
	MeiliIndexField string
}

// getenv 从环境变量读取配置，不存在时返回默认值
func getenv(key, def string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}
	return def
}

func loadConfig() AppConfig {
	brokersEnv := getenv("KAFKA_BROKERS", "10.17.154.252:9092")
	topicEnv := getenv("KAFKA_TOPIC", "test_case.public.test_cases")

	return AppConfig{
		Brokers:         strings.Split(brokersEnv, ","),
		Topics:          strings.Split(topicEnv, ","),
		GroupID:         getenv("KAFKA_GROUP_ID", "meilisearch-sync-service"),
		MeiliHost:       getenv("MEILI_HOST", "http://10.17.154.252:7700"),
		MeiliAPIKey:     getenv("MEILI_API_KEY", ""),
		MeiliIndex:      getenv("MEILI_INDEX", "testcases"),
		MeiliIndexField: getenv("MEILI_INDEX_FIELD", ""),
	}
}

// main 是 Meilisearch 同步服务的入口：
// 1. 从环境变量读取 Kafka 与 Meilisearch 的连接配置
// 2. 初始化 Kafka 消费者和 Meilisearch 客户端
// 3. 循环消费 Debezium CDC 消息，并同步到 Meilisearch
func main() {
	_ = godotenv.Load()

	cfg := loadConfig()

	meiliClient := meilisearch.New(
		cfg.MeiliHost,
		meilisearch.WithAPIKey(cfg.MeiliAPIKey),
	)

	client, err := kgo.NewClient(
		kgo.SeedBrokers(cfg.Brokers...),
		kgo.ConsumerGroup(cfg.GroupID),
		kgo.ConsumeTopics(cfg.Topics...),
	)
	if err != nil {
		log.Fatalf("failed to create kafka client: %v", err)
	}
	defer client.Close() // 延迟到 run 函数结束执行关闭

	log.Printf("listening topics=%v group=%s brokers=%v meiliHost=%s", cfg.Topics, cfg.GroupID, cfg.Brokers, cfg.MeiliHost)

	// 使用 context + 信号量实现优雅退出
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		sig := <-sigCh
		log.Printf("received signal %s, shutting down", sig.String())
		cancel()
	}()
	if err := run(ctx, client, meiliClient, cfg); err != nil && ctx.Err() == nil {
		log.Printf("run loop error: %v", err)
	}
}

func run(ctx context.Context, client *kgo.Client, meiliClient meilisearch.ServiceManager, cfg AppConfig) error {
	for {
		if ctx.Err() != nil {
			return ctx.Err()
		}

		fetches := client.PollFetches(ctx)
		if errs := fetches.Errors(); len(errs) > 0 {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			for _, e := range errs {
				log.Printf("fetch error: %v", e)
			}
			continue
		}

		iter := fetches.RecordIter()
		var records []*kgo.Record

		for !iter.Done() {
			record := iter.Next()
			records = append(records, record)

			op, id, doc, delID, err := processDebeziumMessage(record.Value)
			if err != nil {
				log.Printf("process message error: %v", err)
				continue
			}

			baseIndex := cfg.MeiliIndex
			if len(cfg.Topics) > 1 {
				baseIndex = getBaseIndex(record.Topic, cfg.MeiliIndex)
			}

			switch op {
			case "c", "r", "u":
				indexName := resolveIndex(baseIndex, cfg.MeiliIndexField, doc)
				if isDeleted(doc) {
					_, err := meiliClient.Index(indexName).DeleteDocument(id, nil)
					if err != nil {
						log.Printf("meilisearch soft-delete error id=%s error=%v", id, err)
					} else {
						log.Printf("[soft-delete] meilisearch index=%s id=%s", indexName, id)
					}
				} else {
					_, err := meiliClient.Index(indexName).AddDocuments([]map[string]interface{}{doc}, nil)
					if err != nil {
						log.Printf("meilisearch upsert error id=%s error=%v", id, err)
					} else {
						log.Printf("[upsert] meilisearch index=%s id=%s", indexName, id)
					}
				}
			case "d":
				indexName := resolveIndex(baseIndex, cfg.MeiliIndexField, doc)
				_, err := meiliClient.Index(indexName).DeleteDocument(delID, nil)
				if err != nil {
					log.Printf("meilisearch delete error id=%s error=%v", delID, err)
				} else {
					log.Printf("[delete] meilisearch index=%s id=%s", indexName, delID)
				}
			}
		}

		if len(records) > 0 {
			client.CommitRecords(ctx, records...)
		}
	}
}

// processDebeziumMessage 负责解析单条 Debezium 消息，并抽象为上层可以直接使用的结构：
// - 返回 op: 操作类型 (c/r/u/d)
// - 对于写操作，返回 id 与 doc
// - 对于删除操作，返回 delID
func processDebeziumMessage(value []byte) (string, string, map[string]interface{}, string, error) {
	trimmed := bytes.TrimSpace(value)
	if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("null")) {
		return "", "", nil, "", nil
	}

	var msg DebeziumMessage
	if err := json.Unmarshal(value, &msg); err != nil {
		return "", "", nil, "", fmt.Errorf("decode debezium message error: %w", err)
	}

	payload := msg.Payload

	switch payload.Op {
	case "c", "r", "u":
		// 插入 / 更新 / 快照：从 After 中解析业务文档
		doc, id, err := extractDocument(payload)
		if err != nil {
			return "", "", nil, "", fmt.Errorf("extract document error: %w", err)
		}
		if id == "" {
			return "", "", nil, "", fmt.Errorf("empty id in upsert document: %v", doc)
		}
		return payload.Op, id, doc, "", nil
	case "d":
		if payload.Before == nil {
			return "", "", nil, "", fmt.Errorf("delete op without before payload")
		}
		id := fmt.Sprint(payload.Before["id"])
		if id == "" {
			return "", "", nil, "", fmt.Errorf("empty id in delete payload: %v", payload.Before)
		}
		before := payload.Before
		before["id"] = id
		return payload.Op, "", before, id, nil
	default:
		return "", "", nil, "", fmt.Errorf("unknown op %q", payload.Op)
	}
}

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

func resolveIndex(base, field string, doc map[string]interface{}) string {
	if field == "" || doc == nil {
		return base
	}
	if v, ok := doc[field]; ok {
		s := fmt.Sprint(v)
		if s != "" {
			return base + "_" + s
		}
	}
	return base
}

func getBaseIndex(topic, defaultIndex string) string {
	switch topic {
	case "test_case.public.test_cases":
		return defaultIndex // 比如 defaultIndex = "testcases"
	case "test_case.public.bug_info":
		return "bug_info"
	default:
		return defaultIndex
	}
}

// extractDocument 从 Debezium 的 After 部分提取业务文档：
// 1. 兼容 payload 字段为字符串 JSON / 对象 / 不存在的情况
// 2. 尝试从 doc.id 或 after.id 中推导出文档主键
func extractDocument(p DebeziumPayload) (map[string]interface{}, string, error) {
	if p.After == nil {
		return nil, "", fmt.Errorf("after payload is nil")
	}

	base := p.After

	var doc map[string]interface{}

	// Debezium 对 JSONB 字段的序列化方式可能有多种：
	// 1. payload 为字符串，内部再包一层 JSON
	// 2. payload 直接为 JSON 对象
	// 3. 不存在 payload 字段，直接使用行内容
	if raw, ok := base["payload"]; ok {
		switch v := raw.(type) {
		case string:
			if err := json.Unmarshal([]byte(v), &doc); err != nil {
				return nil, "", fmt.Errorf("decode inner payload string: %w", err)
			}
		case map[string]interface{}:
			doc = v
		default:
			doc = map[string]interface{}{}
		}
	} else {
		if inner, ok := base["doc"].(map[string]interface{}); ok {
			doc = inner
		} else {
			doc = base
		}
	}

	id := ""

	// 优先从业务文档中读取 id
	if v, ok := doc["id"]; ok {
		id = fmt.Sprint(v)
		// 其次从外层 After 中读取 id
	} else if v, ok := base["id"]; ok {
		id = fmt.Sprint(v)
	}

	// 确保最终写入 Meilisearch 的 doc 中一定包含 id 字段
	if id != "" {
		doc["id"] = id
	}

	// 将外层的 is_delete 合并进业务文档，方便统一判断软删除
	if v, ok := base["is_delete"]; ok {
		doc["is_delete"] = v
	}

	return doc, id, nil
}
