package service

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"

	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/logger"
	"meilisearch-sync-service/internal/model"

	"github.com/meilisearch/meilisearch-go"
	"github.com/twmb/franz-go/pkg/kgo"
)

// Run 是消息处理的主循环函数，负责持续消费 Kafka 消息并同步到 Meilisearch
func Run(ctx context.Context, client *kgo.Client, meiliClient meilisearch.ServiceManager, cfg config.AppConfig) error {
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

			// 将 Debezium 原始消息解析为操作类型、文档内容和 id
			op, id, doc, delID, err := processDebeziumMessage(record.Value)
			if err != nil {
				log.Printf("处理消息出错: %v", err)
				continue
			}

			logger.DebugLogf("收到消息 topic=%s partition=%d offset=%d op=%s id=%s delID=%s", record.Topic, record.Partition, record.Offset, op, id, delID)

			// 根据 Debezium 的操作类型执行 upsert 或删除
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

				// 如果文档被标记为删除，则触发物理删除
				if isDeleted(doc) {
					logger.DebugLogf("执行标记删除触发物理删除 index=%s id=%s doc=%v", indexName, id, doc)
					_, err := meiliClient.Index(indexName).DeleteDocument(id, nil)
					if err != nil {
						log.Printf("Meilisearch 标记删除物理删除失败 index=%s id=%s 错误=%v", indexName, id, err)
					} else {
						log.Printf("[delete-by-flag] Meilisearch 索引=%s id=%s", indexName, id)
					}
				} else {
					// 写入前移除路由相关字段，避免污染索引 schema
					if doc != nil {
						delete(doc, "app_name")
						delete(doc, "collection")
						delete(doc, "is_delete")
					}
					logger.DebugLogf("执行插入/更新 index=%s id=%s doc=%v", indexName, id, doc)
					// 使用主键 id 做 upsert，确保同一文档主键一致
					_, err := meiliClient.Index(indexName).AddDocuments(
						[]map[string]interface{}{doc},
						&meilisearch.DocumentOptions{PrimaryKey: meilisearch.StringPtr("id")},
					)
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
				// 删除事件使用 before 中的 id 执行硬删除
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
