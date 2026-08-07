package service

import (
	"context"
	"encoding/json"
	"strconv"
	"strings"
	"sync"
)

// RevisionStore 维护每个 (app, collection, document) 已处理的最大 revision，
// 用于跨 partition / 重放场景下丢弃旧版本事件，防止旧事件覆盖新数据或复活
// 已删除文档。revision 由生产者（PostgreSQL 触发器 / 业务写入）单调递增生成；
// 当事件未携带 revision（旧链路兼容）时，门禁自动放行，不阻断正常消费。
type RevisionStore interface {
	// Applied 返回已处理的最大 revision（0 表示未知）。
	Applied(appID, collection, documentID string) int64
	// TryAdvance 仅当 revision 严格大于已记录值时原子更新，返回是否前进。
	// 调用方必须在下游写入成功后调用。
	TryAdvance(appID, collection, documentID string, revision int64) bool
}

type memoryRevisionStore struct {
	mu   sync.RWMutex
	data map[string]int64
}

// NewMemoryRevisionStore 返回一个进程内的 revision 存储。
// 注：当前为单副本内存实现；多副本 / 重启恢复场景应改用 Redis 等共享存储，
// 使 revision 门禁在重启后仍有意义（见方案 P1/P2）。
func NewMemoryRevisionStore() RevisionStore {
	return &memoryRevisionStore{data: make(map[string]int64)}
}

func revKey(appID, collection, documentID string) string {
	return appID + "\x00" + collection + "\x00" + documentID
}

func (s *memoryRevisionStore) Applied(appID, collection, documentID string) int64 {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.data[revKey(appID, collection, documentID)]
}

func (s *memoryRevisionStore) TryAdvance(appID, collection, documentID string, revision int64) bool {
	if revision <= 0 {
		// 无版本事件不阻断，避免错误丢弃合法消息。
		return true
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	k := revKey(appID, collection, documentID)
	if cur, ok := s.data[k]; ok && cur >= revision {
		return false
	}
	s.data[k] = revision
	return true
}

// EpochGate 查询应用当前生命周期 epoch。应用删除/重建会生成新 epoch；
// 消费端仅接受与本地一致（或事件未携带）的 epoch，旧 epoch 的迟到事件直接确认丢弃，
// 防止删除后旧 Kafka 消息重建 index 或文档。
type EpochGate interface {
	AppEpoch(ctx context.Context, appID string) (epoch string, found bool, err error)
}

// extractRevisionEpoch 从事件负载（outbox after / 文档 map）中提取 revision 与 epoch。
// 缺省或非数值时返回 (0, "")，调用方据此放行（兼容旧事件）。
func extractRevisionEpoch(payload map[string]interface{}) (int64, string) {
	revision, _ := scalarInt64(payload["revision"])
	if revision == 0 {
		// PostgreSQL search_outbox 使用 event_version；revision 仅兼容旧事件。
		revision, _ = scalarInt64(payload["event_version"])
	}
	epoch, _ := nonEmptyString(payload["lifecycle_epoch"])
	return revision, epoch
}

// scalarInt64 将混合类型的数值字段解析为 int64，失败返回 (0, false)。
func scalarInt64(value interface{}) (int64, bool) {
	switch v := value.(type) {
	case int64:
		return v, true
	case int:
		return int64(v), true
	case float64:
		return int64(v), true
	case json.Number:
		if n, err := v.Int64(); err == nil {
			return n, true
		}
	case string:
		if n, err := strconv.ParseInt(strings.TrimSpace(v), 10, 64); err == nil {
			return n, true
		}
	}
	return 0, false
}
