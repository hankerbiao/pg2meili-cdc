package service

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"meilisearch-sync-service/internal/logger"
	"meilisearch-sync-service/internal/model"

	"github.com/meilisearch/meilisearch-go"
	"github.com/twmb/franz-go/pkg/kgo"
)

type RecordHandler interface {
	// Handle 处理单条 Kafka 消息。
	Handle(ctx context.Context, record *kgo.Record) error
}

// DebeziumHandler 负责处理 CDC 数据写入/删除。
type DebeziumHandler struct {
	MeiliClient meilisearch.ServiceManager
}

func (h DebeziumHandler) Handle(ctx context.Context, record *kgo.Record) error {
	op, id, doc, delID, err := processDebeziumMessage(record.Value)
	if err != nil {
		return fmt.Errorf("处理 Debezium 消息失败: %w", err)
	}
	if op == "" {
		return nil
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
			return nil
		}

		if isDeleted(doc) {
			logger.DebugLogf("执行标记删除触发物理删除 index=%s id=%s doc=%v", indexName, id, doc)
			_, err := h.MeiliClient.Index(indexName).DeleteDocument(id, nil)
			if err != nil {
				return fmt.Errorf("Meilisearch 标记删除物理删除失败 index=%s id=%s: %w", indexName, id, err)
			}
			log.Printf("[delete-by-flag] Meilisearch 索引=%s id=%s", indexName, id)
			return nil
		}

		if doc != nil {
			delete(doc, "app_name")
			delete(doc, "collection")
			delete(doc, "is_delete")
		}
		logger.DebugLogf("执行插入/更新 index=%s id=%s doc=%v", indexName, id, doc)
		_, err := h.MeiliClient.Index(indexName).AddDocuments(
			[]map[string]interface{}{doc},
			&meilisearch.DocumentOptions{PrimaryKey: meilisearch.StringPtr("id")},
		)
		if err != nil {
			return fmt.Errorf("Meilisearch 插入/更新失败 index=%s id=%s: %w", indexName, id, err)
		}
		log.Printf("[upsert] Meilisearch 索引=%s id=%s", indexName, id)
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
			return nil
		}
		logger.DebugLogf("执行硬删除 index=%s id=%s doc=%v", indexName, delID, doc)
		_, err := h.MeiliClient.Index(indexName).DeleteDocument(delID, nil)
		if err != nil {
			return fmt.Errorf("Meilisearch 硬删除失败 index=%s id=%s: %w", indexName, delID, err)
		}
		log.Printf("[delete] Meilisearch 索引=%s id=%s", indexName, delID)
	default:
		return fmt.Errorf("未知的操作类型 %q", op)
	}

	return nil
}

// MeiliCommandHandler 负责处理索引设置与管理命令。
type MeiliCommandHandler struct {
	MeiliClient meilisearch.ServiceManager
}

func (h MeiliCommandHandler) Handle(ctx context.Context, record *kgo.Record) error {
	var cmd model.MeiliCommand
	if err := json.Unmarshal(record.Value, &cmd); err != nil {
		return fmt.Errorf("解码命令消息失败: %w", err)
	}

	if cmd.Action != "update_settings" {
		if cmd.Action == "delete_index" {
			if cmd.IndexUID == "" {
				return fmt.Errorf("命令缺少 index_uid")
			}
			_, err := h.MeiliClient.DeleteIndex(cmd.IndexUID)
			if err != nil {
				return fmt.Errorf("Meilisearch 删除索引失败 index=%s: %w", cmd.IndexUID, err)
			}
			log.Printf("[delete-index] Meilisearch 索引=%s", cmd.IndexUID)
			return nil
		}
		log.Printf("忽略未知命令 action=%s topic=%s partition=%d offset=%d", cmd.Action, record.Topic, record.Partition, record.Offset)
		return nil
	}
	if cmd.IndexUID == "" {
		return fmt.Errorf("命令缺少 index_uid")
	}
	if len(cmd.Payload.FilterableAttributes) == 0 || len(cmd.Payload.SortableAttributes) == 0 {
		return fmt.Errorf("命令 payload 缺少 filterableAttributes 或 sortableAttributes")
	}

	settings := &meilisearch.Settings{
		FilterableAttributes: cmd.Payload.FilterableAttributes,
		SortableAttributes:   cmd.Payload.SortableAttributes,
	}
	_, err := h.MeiliClient.Index(cmd.IndexUID).UpdateSettings(settings)
	if err != nil {
		return fmt.Errorf("Meilisearch 更新设置失败 index=%s: %w", cmd.IndexUID, err)
	}
	log.Printf("[update-settings] Meilisearch 索引=%s filterable=%v sortable=%v", cmd.IndexUID, cmd.Payload.FilterableAttributes, cmd.Payload.SortableAttributes)
	return nil
}
