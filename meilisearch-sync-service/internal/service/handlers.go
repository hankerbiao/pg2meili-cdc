package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"time"

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

const (
	taskPollInterval = 100 * time.Millisecond
	taskTimeout      = 30 * time.Second
)

func meiliOperationError(action string, err error) error {
	wrapped := fmt.Errorf("%s: %w", action, err)
	var apiErr *meilisearch.Error
	if errors.As(err, &apiErr) && apiErr.StatusCode >= 400 && apiErr.StatusCode < 500 && apiErr.StatusCode != http.StatusRequestTimeout && apiErr.StatusCode != http.StatusTooManyRequests {
		return permanent(wrapped)
	}
	return wrapped
}

func waitForTask(ctx context.Context, client meilisearch.ServiceManager, info *meilisearch.TaskInfo, action string) error {
	if info == nil {
		return fmt.Errorf("%s: Meilisearch 未返回任务信息", action)
	}
	taskCtx, cancel := context.WithTimeout(ctx, taskTimeout)
	defer cancel()
	task, err := client.WaitForTaskWithContext(taskCtx, info.TaskUID, taskPollInterval)
	if err != nil {
		return fmt.Errorf("%s: 等待 Meilisearch 任务 %d 失败: %w", action, info.TaskUID, err)
	}
	if task == nil {
		return fmt.Errorf("%s: Meilisearch 任务 %d 未返回状态", action, info.TaskUID)
	}
	if task.Status != meilisearch.TaskStatusSucceeded {
		return permanent(fmt.Errorf("%s: Meilisearch 任务 %d 状态=%s 错误=%s", action, info.TaskUID, task.Status, task.Error.Message))
	}
	return nil
}

func (h DebeziumHandler) Handle(ctx context.Context, record *kgo.Record) error {
	op, id, doc, delID, err := processDebeziumMessage(record.Value)
	if err != nil {
		return permanent(fmt.Errorf("处理 Debezium 消息失败: %w", err))
	}
	if op == "" {
		return nil
	}

	logger.DebugLogf("收到消息 topic=%s partition=%d offset=%d op=%s id=%s delID=%s", record.Topic, record.Partition, record.Offset, op, id, delID)

	switch op {
	case "c", "r", "u":
		indexName := ResolveIndex(doc)
		if indexName == "" {
			return permanent(fmt.Errorf("写入消息缺少有效的 app_name 或 collection"))
		}

		if isDeleted(doc) {
			logger.DebugLogf("执行标记删除触发物理删除 index=%s id=%s doc=%v", indexName, id, doc)
			task, err := h.MeiliClient.Index(indexName).DeleteDocumentWithContext(ctx, id, nil)
			if err != nil {
				return meiliOperationError(fmt.Sprintf("Meilisearch 标记删除失败 index=%s id=%s", indexName, id), err)
			}
			if err := waitForTask(ctx, h.MeiliClient, task, "Meilisearch 标记删除"); err != nil {
				return err
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
		task, err := h.MeiliClient.Index(indexName).AddDocumentsWithContext(
			ctx,
			[]map[string]interface{}{doc},
			&meilisearch.DocumentOptions{PrimaryKey: meilisearch.StringPtr("id")},
		)
		if err != nil {
			return meiliOperationError(fmt.Sprintf("Meilisearch 插入/更新失败 index=%s id=%s", indexName, id), err)
		}
		if err := waitForTask(ctx, h.MeiliClient, task, "Meilisearch 插入/更新"); err != nil {
			return err
		}
		log.Printf("[upsert] Meilisearch 索引=%s id=%s", indexName, id)
	case "d":
		indexName := ResolveIndex(doc)
		if indexName == "" {
			return permanent(fmt.Errorf("删除消息缺少有效的 app_name 或 collection"))
		}
		logger.DebugLogf("执行硬删除 index=%s id=%s doc=%v", indexName, delID, doc)
		task, err := h.MeiliClient.Index(indexName).DeleteDocumentWithContext(ctx, delID, nil)
		if err != nil {
			return meiliOperationError(fmt.Sprintf("Meilisearch 硬删除失败 index=%s id=%s", indexName, delID), err)
		}
		if err := waitForTask(ctx, h.MeiliClient, task, "Meilisearch 硬删除"); err != nil {
			return err
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
		return permanent(fmt.Errorf("解码命令消息失败: %w", err))
	}

	if cmd.Action != "update_settings" {
		if cmd.Action == "delete_index" {
			if cmd.IndexUID == "" {
				return permanent(fmt.Errorf("命令缺少 index_uid"))
			}
			task, err := h.MeiliClient.DeleteIndexWithContext(ctx, cmd.IndexUID)
			if err != nil {
				return meiliOperationError(fmt.Sprintf("Meilisearch 删除索引失败 index=%s", cmd.IndexUID), err)
			}
			if err := waitForTask(ctx, h.MeiliClient, task, "Meilisearch 删除索引"); err != nil {
				return err
			}
			log.Printf("[delete-index] Meilisearch 索引=%s", cmd.IndexUID)
			return nil
		}
		return permanent(fmt.Errorf("未知命令 action=%s", cmd.Action))
	}
	if cmd.IndexUID == "" {
		return permanent(fmt.Errorf("命令缺少 index_uid"))
	}

	settings := &meilisearch.Settings{
		FilterableAttributes: cmd.Payload.FilterableAttributes,
		SortableAttributes:   cmd.Payload.SortableAttributes,
	}
	task, err := h.MeiliClient.Index(cmd.IndexUID).UpdateSettingsWithContext(ctx, settings)
	if err != nil {
		return meiliOperationError(fmt.Sprintf("Meilisearch 更新设置失败 index=%s", cmd.IndexUID), err)
	}
	if err := waitForTask(ctx, h.MeiliClient, task, "Meilisearch 更新设置"); err != nil {
		return err
	}
	log.Printf("[update-settings] Meilisearch 索引=%s filterable=%v sortable=%v", cmd.IndexUID, cmd.Payload.FilterableAttributes, cmd.Payload.SortableAttributes)
	return nil
}
