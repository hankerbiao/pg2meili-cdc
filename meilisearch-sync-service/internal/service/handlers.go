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

func derefStr(v *string) string {
	if v == nil {
		return "<未配置>"
	}
	return *v
}

func derefBool(v *bool) string {
	if v == nil {
		return "<未配置>"
	}
	if *v {
		return "true"
	}
	return "false"
}

func derefInt64(v *int64) string {
	if v == nil {
		return "<未配置>"
	}
	return fmt.Sprintf("%d", *v)
}

type RecordHandler interface {
	// Handle 处理单条 Kafka 消息。
	Handle(ctx context.Context, record *kgo.Record) error
}

// TenantGate 供 CDC 消费端查询租户应用状态，阻止已回收租户的在途消息复活索引。
type TenantGate interface {
	AppStatus(ctx context.Context, appID string) (status string, found bool, err error)
}

// DebeziumHandler 负责处理 CDC 数据写入/删除。
type DebeziumHandler struct {
	MeiliClient meilisearch.ServiceManager
	// TenantGate 可选；为 nil 时不启用租户状态门禁（测试/单机场景）。
	TenantGate TenantGate
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

// deleteDocument 统一执行 Meilisearch 文档删除并等待任务完成。
func (h DebeziumHandler) deleteDocument(ctx context.Context, indexName, id, label string) error {
	task, err := h.MeiliClient.Index(indexName).DeleteDocumentWithContext(ctx, id, nil)
	if err != nil {
		return meiliOperationError(fmt.Sprintf("Meilisearch %s失败 index=%s id=%s", label, indexName, id), err)
	}
	return waitForTask(ctx, h.MeiliClient, task, "Meilisearch "+label)
}

func (h DebeziumHandler) Handle(ctx context.Context, record *kgo.Record) error {
	op, id, doc, delID, err := processDebeziumMessage(record.Value)
	if err != nil {
		return permanent(fmt.Errorf("处理 Debezium 消息失败: %w", err))
	}
	if op == "" {
		return nil
	}

	// 租户状态门禁：删除中/已删除的租户不再写入 Meilisearch。注册表不可用或
	// 未找到租户时报错让 Kafka 重试（fail-closed），等待应用状态事件到达。
	if h.TenantGate != nil {
		skip, err := h.tenantGateDecision(ctx, record, doc)
		if err != nil {
			return err
		}
		if skip {
			return nil
		}
	}

	logger.DebugLogf("收到消息 topic=%s partition=%d offset=%d op=%s id=%s delID=%s", record.Topic, record.Partition, record.Offset, op, id, delID)

	switch op {
	case "c", "r", "u":
		indexName := ResolveIndex(doc)
		if indexName == "" {
			return permanent(fmt.Errorf("写入消息缺少有效的 app_id 或 collection"))
		}

		if isDeleted(doc) {
			logger.DebugLogf("执行标记删除触发物理删除 index=%s id=%s", indexName, id)
			if err := h.deleteDocument(ctx, indexName, id, "标记删除"); err != nil {
				return err
			}
			log.Printf("[delete-by-flag] Meilisearch 索引=%s id=%s", indexName, id)
			return nil
		}

		if doc != nil {
			delete(doc, "app_name")
			delete(doc, "app_id")
			delete(doc, "collection")
			delete(doc, "is_delete")
		}
		logger.DebugLogf("执行插入/更新 index=%s id=%s", indexName, id)
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
			return permanent(fmt.Errorf("删除消息缺少有效的 app_id 或 collection"))
		}
		logger.DebugLogf("执行硬删除 index=%s id=%s", indexName, delID)
		if err := h.deleteDocument(ctx, indexName, delID, "硬删除"); err != nil {
			return err
		}
		log.Printf("[delete] Meilisearch 索引=%s id=%s", indexName, delID)
	default:
		return fmt.Errorf("未知的操作类型 %q", op)
	}

	return nil
}

// tenantGateDecision 返回 (true, nil) 表示应跳过该消息。
func (h DebeziumHandler) tenantGateDecision(ctx context.Context, record *kgo.Record, doc map[string]interface{}) (bool, error) {
	appID, ok := nonEmptyString(doc["app_id"])
	if !ok {
		// 缺少路由字段时交由后续 ResolveIndex 报永久错误处理。
		return false, nil
	}
	status, found, err := h.TenantGate.AppStatus(ctx, appID)
	if err != nil {
		return false, fmt.Errorf("查询租户状态失败 app=%s: %w", appID, err)
	}
	if found && (status == "deleting" || status == "deleted") {
		logger.DebugLogf(
			"跳过已停用租户的 CDC 消息 app=%s status=%s topic=%s partition=%d offset=%d",
			appID, status, record.Topic, record.Partition, record.Offset,
		)
		return true, nil
	}
	if !found {
		return false, fmt.Errorf("租户状态不存在 app=%s", appID)
	}
	return false, nil
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

	if err := validateMeiliCommand(cmd); err != nil {
		return permanent(err)
	}

	switch cmd.Action {
	case "update_settings":
		settings := &meilisearch.Settings{
			FilterableAttributes: cmd.Payload.FilterableAttributes,
			SortableAttributes:   cmd.Payload.SortableAttributes,
		}
		if cmd.Payload.SearchableAttributes != nil {
			settings.SearchableAttributes = cmd.Payload.SearchableAttributes
		}
		if cmd.Payload.DisplayedAttributes != nil {
			settings.DisplayedAttributes = cmd.Payload.DisplayedAttributes
		}
		if cmd.Payload.DistinctAttribute != nil {
			settings.DistinctAttribute = cmd.Payload.DistinctAttribute
		}
		if cmd.Payload.TypoToleranceEnabled != nil {
			settings.TypoTolerance = &meilisearch.TypoTolerance{Enabled: *cmd.Payload.TypoToleranceEnabled}
		}
		if cmd.Payload.PaginationMaxTotalHits != nil {
			settings.Pagination = &meilisearch.Pagination{MaxTotalHits: *cmd.Payload.PaginationMaxTotalHits}
		}
		if cmd.Payload.FacetingMaxValuesPerFacet != nil {
			settings.Faceting = &meilisearch.Faceting{MaxValuesPerFacet: *cmd.Payload.FacetingMaxValuesPerFacet}
		}
		task, err := h.MeiliClient.Index(cmd.IndexUID).UpdateSettingsWithContext(ctx, settings)
		if err != nil {
			return meiliOperationError(fmt.Sprintf("Meilisearch 更新设置失败 index=%s", cmd.IndexUID), err)
		}
		if err := waitForTask(ctx, h.MeiliClient, task, "Meilisearch 更新设置"); err != nil {
			return err
		}
		log.Printf("[update-settings] Meilisearch 索引=%s filterable=%v sortable=%v searchable=%v displayed=%v distinct=%v typo=%v pagination=%v faceting=%v",
			cmd.IndexUID, cmd.Payload.FilterableAttributes, cmd.Payload.SortableAttributes,
			cmd.Payload.SearchableAttributes, cmd.Payload.DisplayedAttributes,
			derefStr(cmd.Payload.DistinctAttribute), derefBool(cmd.Payload.TypoToleranceEnabled),
			derefInt64(cmd.Payload.PaginationMaxTotalHits), derefInt64(cmd.Payload.FacetingMaxValuesPerFacet))
	case "delete_index":
		task, err := h.MeiliClient.DeleteIndexWithContext(ctx, cmd.IndexUID)
		if err != nil {
			return meiliOperationError(fmt.Sprintf("Meilisearch 删除索引失败 index=%s", cmd.IndexUID), err)
		}
		if err := waitForTask(ctx, h.MeiliClient, task, "Meilisearch 删除索引"); err != nil {
			return err
		}
		log.Printf("[delete-index] Meilisearch 索引=%s", cmd.IndexUID)
	default:
		return permanent(fmt.Errorf("未知命令 action=%s", cmd.Action))
	}
	return nil
}

func validateMeiliCommand(cmd model.MeiliCommand) error {
	if cmd.IndexUID == "" {
		return fmt.Errorf("命令缺少 index_uid")
	}
	if cmd.AppID == "" || cmd.Collection == "" {
		return fmt.Errorf("命令缺少 app_id 或 collection")
	}
	expectedIndexUID := model.IndexUID(cmd.AppID, cmd.Collection)
	if expectedIndexUID == "" || expectedIndexUID != cmd.IndexUID {
		return fmt.Errorf("命令 index_uid 与租户路由不匹配")
	}
	return nil
}
