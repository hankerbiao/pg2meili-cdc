package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"strings"
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

// BatchRecordHandler is implemented by handlers that can acknowledge a group
// of Kafka records only after the matching downstream batch has completed.
// Results are returned in input order; a shortened result set means the first
// retryable failure stopped processing the remainder of that batch.
type BatchRecordHandler interface {
	RecordHandler
	HandleBatch(ctx context.Context, records []*kgo.Record) []BatchResult
}

type BatchResult struct {
	Record *kgo.Record
	Err    error
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
	// EpochGate 可选；为 nil 时不启用生命周期 epoch 门禁。应用删除/重建后旧
	// epoch 的迟到事件会被确认丢弃，避免旧 Kafka 消息重建 index 或文档。
	EpochGate EpochGate
	// Revisions 可选；为 nil 时不启用文档 revision 门禁。revision 严格大于已
	// 处理值才执行，旧版本事件确认丢弃，防止乱序/重放覆盖新数据。
	Revisions RevisionStore
	// MaxBatchBytes caps the serialized Meilisearch request payload. Zero uses
	// the service default so direct handler tests remain backward compatible.
	MaxBatchBytes int
}

type preparedDebeziumEvent struct {
	record     *kgo.Record
	indexName  string
	operation  string
	document   map[string]interface{}
	documentID string
	appID      string
	collection string
	revisionID string
	revision   int64
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
		err := fmt.Errorf("%s: Meilisearch 任务 %d 状态=%s 错误=%s", action, info.TaskUID, task.Status, task.Error.Message)
		if isPermanentTaskError(task.Error.Code, task.Error.Type) {
			return permanent(err)
		}
		return err
	}
	return nil
}

func (h DebeziumHandler) Handle(ctx context.Context, record *kgo.Record) error {
	event, err := h.prepare(ctx, record)
	if err != nil || event == nil {
		return err
	}
	if event.operation == "delete" {
		task, err := h.MeiliClient.Index(event.indexName).DeleteDocumentWithContext(ctx, event.documentID, nil)
		if err != nil {
			return meiliOperationError(fmt.Sprintf("Meilisearch 删除失败 index=%s id=%s", event.indexName, event.documentID), err)
		}
		if err := waitForTask(ctx, h.MeiliClient, task, "Meilisearch 删除"); err != nil {
			return err
		}
		return h.markRevisionApplied(event.appID, event.collection, event.revisionID, event.revision)
	}
	if err := h.applyPrepared(ctx, []preparedDebeziumEvent{*event}); err != nil {
		return err
	}
	return h.markRevisionApplied(event.appID, event.collection, event.revisionID, event.revision)
}

// HandleBatch keeps source order by only coalescing consecutive events that
// target the same index and operation. This avoids moving an update past a
// delete or an index command while still collapsing normal CDC bursts.
func (h DebeziumHandler) HandleBatch(ctx context.Context, records []*kgo.Record) []BatchResult {
	results := make([]BatchResult, 0, len(records))
	group := make([]preparedDebeziumEvent, 0, len(records))
	groupBytes := 0

	flush := func() bool {
		if len(group) == 0 {
			return true
		}
		groupResults := h.applyPreparedGroup(ctx, group)
		results = append(results, groupResults...)
		group = group[:0]
		groupBytes = 0
		for _, result := range groupResults {
			if result.Err != nil && !isPermanent(result.Err) {
				return false
			}
		}
		return true
	}

	for _, record := range records {
		// A Kafka partition is the ordering boundary. Flush before preparing a
		// record from another partition so its revision gate observes all
		// successful writes from the preceding partition group.
		if len(group) > 0 && (group[0].record.Topic != record.Topic || group[0].record.Partition != record.Partition) {
			if !flush() {
				return results
			}
		}
		event, err := h.prepare(ctx, record)
		if err != nil {
			if !flush() {
				return results
			}
			results = append(results, BatchResult{Record: record, Err: err})
			if !isPermanent(err) {
				return results
			}
			continue
		}
		if event == nil {
			if !flush() {
				return results
			}
			results = append(results, BatchResult{Record: record})
			continue
		}
		if len(group) > 0 && groupContainsDocument(group, *event) {
			if !flush() {
				return results
			}
			if h.revisionApplied(*event) {
				results = append(results, BatchResult{Record: record})
				continue
			}
		}
		eventBytes, sizeErr := preparedEventSize(*event)
		if sizeErr != nil {
			if !flush() {
				return results
			}
			results = append(results, BatchResult{Record: record, Err: permanent(fmt.Errorf("序列化 Meilisearch 批量事件失败: %w", sizeErr))})
			continue
		}
		if len(group) > 0 && (group[0].indexName != event.indexName || group[0].operation != event.operation || groupBytes+eventBytes > h.maxBatchBytes()) {
			if !flush() {
				return results
			}
		}
		group = append(group, *event)
		groupBytes += eventBytes
	}
	flush()
	return results
}

func groupContainsDocument(group []preparedDebeziumEvent, event preparedDebeziumEvent) bool {
	if event.revision <= 0 || event.revisionID == "" {
		return false
	}
	for _, candidate := range group {
		if candidate.appID == event.appID && candidate.collection == event.collection && candidate.revisionID == event.revisionID {
			return true
		}
	}
	return false
}

func (h DebeziumHandler) revisionApplied(event preparedDebeziumEvent) bool {
	return h.Revisions != nil && event.revision > 0 && h.Revisions.Applied(event.appID, event.collection, event.revisionID) >= event.revision
}

func (h DebeziumHandler) maxBatchBytes() int {
	if h.MaxBatchBytes > 0 {
		return h.MaxBatchBytes
	}
	return 5 * 1024 * 1024
}

func preparedEventSize(event preparedDebeziumEvent) (int, error) {
	if event.operation == "upsert" {
		payload, err := json.Marshal(event.document)
		return len(payload) + 1, err // JSON array comma / brackets overhead
	}
	payload, err := json.Marshal(event.documentID)
	return len(payload) + 1, err
}

func isPermanentTaskError(code, kind string) bool {
	kind = strings.ToLower(kind)
	code = strings.ToLower(code)
	return kind == "invalid_request" || strings.HasPrefix(code, "invalid_") || strings.HasPrefix(code, "missing_") || strings.HasPrefix(code, "malformed_") || strings.HasPrefix(code, "primary_key_")
}

func (h DebeziumHandler) prepare(ctx context.Context, record *kgo.Record) (*preparedDebeziumEvent, error) {
	op, id, doc, delID, revision, epoch, err := processDebeziumMessage(record.Value)
	if err != nil {
		return nil, permanent(fmt.Errorf("处理 Debezium 消息失败: %w", err))
	}
	if op == "" {
		return nil, nil
	}

	// 租户状态门禁：删除中/已删除的租户不再写入 Meilisearch。注册表不可用或
	// 未找到租户时报错让 Kafka 重试（fail-closed），等待应用状态事件到达。
	if h.TenantGate != nil {
		skip, err := h.tenantGateDecision(ctx, record, doc)
		if err != nil {
			return nil, err
		}
		if skip {
			return nil, nil
		}
	}

	appID, _ := nonEmptyString(doc["app_id"])
	collection, _ := nonEmptyString(doc["collection"])

	// 生命周期 epoch 门禁：应用删除/重建会生成新 epoch，旧 epoch 的迟到事件
	// 直接确认丢弃，防止旧 Kafka 消息重建已删除的 index 或文档。
	if h.EpochGate != nil && epoch != "" {
		cur, found, eerr := h.EpochGate.AppEpoch(ctx, appID)
		if eerr != nil {
			return nil, eerr
		}
		if found && cur != "" && cur != epoch {
			logger.DebugLogf(
				"跳过过期 epoch 事件 app=%s eventEpoch=%s currentEpoch=%s topic=%s partition=%d offset=%d",
				appID, epoch, cur, record.Topic, record.Partition, record.Offset,
			)
			return nil, nil
		}
	}

	// 文档 revision 门禁：只读已成功应用的版本；实际推进必须在 Meilisearch
	// 成功后进行，避免瞬时故障后重投被错误去重。
	var revisionKeyID string
	if h.Revisions != nil && revision > 0 {
		revisionKeyID = id
		if op == "d" {
			revisionKeyID = delID
		}
		if h.Revisions.Applied(appID, collection, revisionKeyID) >= revision {
			logger.DebugLogf(
				"跳过旧版本事件 app=%s collection=%s id=%s revision=%d topic=%s partition=%d offset=%d",
				appID, collection, revisionKeyID, revision, record.Topic, record.Partition, record.Offset,
			)
			return nil, nil
		}
	}

	logger.DebugLogf("收到消息 topic=%s partition=%d offset=%d op=%s id=%s delID=%s", record.Topic, record.Partition, record.Offset, op, id, delID)

	switch op {
	case "c", "r", "u":
		indexName := ResolveIndex(doc)
		if indexName == "" {
			return nil, permanent(fmt.Errorf("写入消息缺少有效的 app_id 或 collection"))
		}

		if isDeleted(doc) {
			return &preparedDebeziumEvent{record: record, indexName: indexName, operation: "delete", documentID: model.MeiliDocumentID(id), appID: appID, collection: collection, revisionID: revisionKeyID, revision: revision}, nil
		}

		if doc != nil {
			delete(doc, "app_name")
			delete(doc, "app_id")
			delete(doc, "collection")
			delete(doc, "is_delete")
		}
		return &preparedDebeziumEvent{record: record, indexName: indexName, operation: "upsert", document: doc, appID: appID, collection: collection, revisionID: revisionKeyID, revision: revision}, nil
	case "d":
		indexName := ResolveIndex(doc)
		if indexName == "" {
			return nil, permanent(fmt.Errorf("删除消息缺少有效的 app_id 或 collection"))
		}
		return &preparedDebeziumEvent{record: record, indexName: indexName, operation: "delete", documentID: model.MeiliDocumentID(delID), appID: appID, collection: collection, revisionID: revisionKeyID, revision: revision}, nil
	default:
		return nil, permanent(fmt.Errorf("未知的操作类型 %q", op))
	}
}

func (h DebeziumHandler) applyPreparedGroup(ctx context.Context, events []preparedDebeziumEvent) []BatchResult {
	err := h.applyPrepared(ctx, events)
	if err == nil {
		results := make([]BatchResult, 0, len(events))
		for _, event := range events {
			_ = h.markRevisionApplied(event.appID, event.collection, event.revisionID, event.revision)
			results = append(results, BatchResult{Record: event.record})
		}
		return results
	}
	if isPermanent(err) && len(events) > 1 {
		middle := len(events) / 2
		return append(h.applyPreparedGroup(ctx, events[:middle]), h.applyPreparedGroup(ctx, events[middle:])...)
	}
	results := make([]BatchResult, 0, len(events))
	for _, event := range events {
		results = append(results, BatchResult{Record: event.record, Err: err})
	}
	return results
}

func (h DebeziumHandler) applyPrepared(ctx context.Context, events []preparedDebeziumEvent) error {
	if len(events) == 0 {
		return nil
	}
	first := events[0]
	started := time.Now()
	if first.operation == "upsert" {
		documents := make([]map[string]interface{}, 0, len(events))
		for _, event := range events {
			documents = append(documents, event.document)
		}
		logger.DebugLogf("批量插入/更新 index=%s size=%d", first.indexName, len(documents))
		task, err := h.MeiliClient.Index(first.indexName).AddDocumentsWithContext(ctx, documents, &meilisearch.DocumentOptions{PrimaryKey: meilisearch.StringPtr("_meili_id")})
		if err != nil {
			return meiliOperationError(fmt.Sprintf("Meilisearch 批量插入/更新失败 index=%s size=%d", first.indexName, len(documents)), err)
		}
		err = waitForTask(ctx, h.MeiliClient, task, "Meilisearch 批量插入/更新")
		if err == nil {
			log.Printf("[meili-batch] completed operation=upsert index=%s size=%d duration=%s", first.indexName, len(documents), time.Since(started))
		}
		return err
	}
	ids := make([]string, 0, len(events))
	for _, event := range events {
		ids = append(ids, event.documentID)
	}
	logger.DebugLogf("批量删除 index=%s size=%d", first.indexName, len(ids))
	task, err := h.MeiliClient.Index(first.indexName).DeleteDocumentsWithContext(ctx, ids, nil)
	if err != nil {
		return meiliOperationError(fmt.Sprintf("Meilisearch 批量删除失败 index=%s size=%d", first.indexName, len(ids)), err)
	}
	err = waitForTask(ctx, h.MeiliClient, task, "Meilisearch 批量删除")
	if err == nil {
		log.Printf("[meili-batch] completed operation=delete index=%s size=%d duration=%s", first.indexName, len(ids), time.Since(started))
	}
	return err
}

func (h DebeziumHandler) markRevisionApplied(appID, collection, documentID string, revision int64) error {
	if h.Revisions != nil && revision > 0 {
		h.Revisions.TryAdvance(appID, collection, documentID, revision)
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
	MeiliClient    meilisearch.ServiceManager
	RegionID       string
	ConfirmCleanup func(context.Context, model.MeiliCommand) error
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
		if cmd.CleanupTaskID != "" && !commandTargetsRegion(cmd.TargetRegions, h.RegionID) {
			return nil
		}
		task, err := h.MeiliClient.DeleteIndexWithContext(ctx, cmd.IndexUID)
		if err != nil {
			if !isMeiliNotFound(err) {
				return meiliOperationError(fmt.Sprintf("Meilisearch 删除索引失败 index=%s", cmd.IndexUID), err)
			}
		}
		if task != nil {
			if err := waitForTask(ctx, h.MeiliClient, task, "Meilisearch 删除索引"); err != nil {
				return err
			}
		}
		if cmd.CleanupTaskID != "" && h.ConfirmCleanup != nil {
			if err := h.ConfirmCleanup(ctx, cmd); err != nil {
				return fmt.Errorf("确认索引删除失败 task=%s region=%s: %w", cmd.CleanupTaskID, h.RegionID, err)
			}
		}
		if cmd.CleanupTaskID != "" && h.ConfirmCleanup == nil {
			return fmt.Errorf("清理命令缺少确认回调 task=%s", cmd.CleanupTaskID)
		}
		log.Printf("[delete-index] Meilisearch 索引=%s", cmd.IndexUID)
	default:
		return permanent(fmt.Errorf("未知命令 action=%s", cmd.Action))
	}
	return nil
}

func commandTargetsRegion(targetRegions []string, region string) bool {
	region = strings.TrimSpace(region)
	if region == "" {
		return false
	}
	for _, target := range targetRegions {
		if strings.TrimSpace(target) == region {
			return true
		}
	}
	return false
}

func isMeiliNotFound(err error) bool {
	var apiErr *meilisearch.Error
	return errors.As(err, &apiErr) && apiErr.StatusCode == http.StatusNotFound
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
