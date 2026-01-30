package service

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"

	"distributed-search/meilisearch-sync-service/internal/config"
	"distributed-search/meilisearch-sync-service/internal/logger"
	"distributed-search/meilisearch-sync-service/internal/model"

	"github.com/meilisearch/meilisearch-go"
	"github.com/twmb/franz-go/pkg/kgo"
)

// Run 是消息处理的主循环函数，负责持续消费 Kafka 消息并同步到 Meilisearch
func Run(ctx context.Context, client *kgo.Client, meiliClient meilisearch.ServiceManager, cfg config.AppConfig) error {
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
				log.Printf("从 Kafka 拉取消息出错: %v", e)
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
				log.Printf("处理消息出错: %v", err)
				continue
			}

			logger.DebugLogf("收到消息 topic=%s partition=%d offset=%d op=%s id=%s delID=%s", record.Topic, record.Partition, record.Offset, op, id, delID)

			switch op {
			case "c", "r", "u":
				indexName := ResolveIndex(doc)
				if indexName == "" {
					appNameVal := ""
					collectionVal := ""
					if doc != nil {
						if v, ok := doc["app_name"]; ok {
							appNameVal = fmt.Sprint(v)
						}
						if v, ok := doc["collection"]; ok {
							collectionVal = fmt.Sprint(v)
						}
					}
					log.Printf("跳过写入: app_name 或 collection 为空 topic=%s partition=%d offset=%d app_name=%s collection=%s doc=%v", record.Topic, record.Partition, record.Offset, appNameVal, collectionVal, doc)
					continue
				}

				if isDeleted(doc) {
					logger.DebugLogf("执行标记删除触发物理删除 index=%s id=%s doc=%v", indexName, id, doc)
					_, err := meiliClient.Index(indexName).DeleteDocument(id, nil)
					if err != nil {
						log.Printf("Meilisearch 标记删除物理删除失败 index=%s id=%s 错误=%v", indexName, id, err)
					} else {
						log.Printf("[delete-by-flag] Meilisearch 索引=%s id=%s", indexName, id)
					}
				} else {
					if doc != nil {
						delete(doc, "app_name")
						delete(doc, "collection")
						delete(doc, "is_delete")
					}
					logger.DebugLogf("执行插入/更新 index=%s id=%s doc=%v", indexName, id, doc)
					_, err := meiliClient.Index(indexName).AddDocuments([]map[string]interface{}{doc}, nil)
					if err != nil {
						log.Printf("Meilisearch 插入/更新失败 index=%s id=%s 错误=%v", indexName, id, err)
					} else {
						log.Printf("[upsert] Meilisearch 索引=%s id=%s", indexName, id)
					}
				}
			case "d":
				indexName := ResolveIndex(doc)
				if indexName == "" {
					appNameVal := ""
					collectionVal := ""
					if doc != nil {
						if v, ok := doc["app_name"]; ok {
							appNameVal = fmt.Sprint(v)
						}
						if v, ok := doc["collection"]; ok {
							collectionVal = fmt.Sprint(v)
						}
					}
					log.Printf("跳过删除: app_name 或 collection 为空 topic=%s partition=%d offset=%d app_name=%s collection=%s doc=%v", record.Topic, record.Partition, record.Offset, appNameVal, collectionVal, doc)
					continue
				}
				logger.DebugLogf("执行硬删除 index=%s id=%s doc=%v", indexName, delID, doc)
				_, err := meiliClient.Index(indexName).DeleteDocument(delID, nil)
				if err != nil {
					log.Printf("Meilisearch 硬删除失败 index=%s id=%s 错误=%v", indexName, delID, err)
				} else {
					log.Printf("[delete] Meilisearch 索引=%s id=%s", indexName, delID)
				}
			}
		}

		if len(records) > 0 {
			client.CommitRecords(ctx, records...)
		}
	}
}

func processDebeziumMessage(value []byte) (string, string, map[string]interface{}, string, error) {
	trimmed := bytes.TrimSpace(value)
	if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("null")) {
		return "", "", nil, "", nil
	}

	var msg model.DebeziumMessage
	if err := json.Unmarshal(value, &msg); err != nil {
		return "", "", nil, "", fmt.Errorf("解码 Debezium 消息失败: %w", err)
	}

	payload := msg.Payload

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

func extractDocument(p model.DebeziumPayload) (map[string]interface{}, string, error) {
	if p.After == nil {
		return nil, "", fmt.Errorf("After 字段为空")
	}

	base := p.After

	var doc map[string]interface{}

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

	if id != "" {
		doc["id"] = id
	}

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
