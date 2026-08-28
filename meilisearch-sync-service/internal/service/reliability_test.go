package service

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"meilisearch-sync-service/internal/model"

	"github.com/meilisearch/meilisearch-go"
	"github.com/twmb/franz-go/pkg/kgo"
)

// recordedCall 记录一次对假 Meilisearch 的调用，便于断言门禁行为。
type recordedCall struct {
	method string
	path   string
	body   string
}

// newFakeMeili 启动一个记录调用并返回“成功”的假 Meilisearch 服务。
// meiliUnavailable=true 时，AddDocuments 的 POST 直接返回 503（瞬时故障），
// 用于验证 Meilisearch 临时故障返回可重试错误、从而不提交 offset。
func newFakeMeili(t *testing.T, meiliUnavailable bool) (meilisearch.ServiceManager, *[]recordedCall) {
	t.Helper()
	calls := &[]recordedCall{}
	var mu sync.Mutex
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b := new(strings.Builder)
		_, _ = io.Copy(b, r.Body)
		mu.Lock()
		*calls = append(*calls, recordedCall{method: r.Method, path: r.URL.Path, body: b.String()})
		mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/documents"):
			if meiliUnavailable {
				w.WriteHeader(http.StatusServiceUnavailable)
				_, _ = w.Write([]byte(`{"message":"meili unavailable","code":"service_unavailable"}`))
				return
			}
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"taskUid":1}`))
		case r.Method == http.MethodDelete && strings.Contains(r.URL.Path, "/documents/"):
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"taskUid":1}`))
		case r.Method == http.MethodDelete && strings.HasSuffix(r.URL.Path, "/documents"):
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"taskUid":1}`))
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/documents/delete-batch"):
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"taskUid":1}`))
		case strings.HasPrefix(r.URL.Path, "/tasks/"):
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"uid":1,"status":"succeeded","error":{"message":""}}`))
		default:
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{}`))
		}
	}))
	t.Cleanup(server.Close)
	return meilisearch.New(server.URL), calls
}

func upsertEvent(appID, collection, docID string, revision int) *kgo.Record {
	return upsertEventEpoch(appID, collection, docID, revision, "")
}

func upsertEventEpoch(appID, collection, docID string, revision int, epoch string) *kgo.Record {
	epochField := ""
	if epoch != "" {
		epochField = `,"lifecycle_epoch":"` + epoch + `"`
	}
	payload := `{"payload":{"after":{"app_id":"` + appID + `","collection":"` + collection +
		`","document_id":"` + docID + `","operation":"upsert","revision":` + itoa(revision) +
		epochField + `,"document":{"name":"v` + itoa(revision) + `"}},"op":"c"}}`
	return &kgo.Record{Topic: "pg.public.search_outbox", Partition: 0, Offset: int64(revision), Value: []byte(payload)}
}

func deleteEvent(appID, collection, docID string, revision int) *kgo.Record {
	payload := `{"payload":{"after":{"app_id":"` + appID + `","collection":"` + collection +
		`","document_id":"` + docID + `","operation":"delete","revision":` + itoa(revision) +
		`,"document":null},"op":"c"}}`
	return &kgo.Record{Topic: "pg.public.search_outbox", Partition: 0, Offset: int64(revision), Value: []byte(payload)}
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}

// TestRevisionGateSkipsOldUpsertAndPreventsResurrection 验证：乱序 upsert 中旧版本被
// 丢弃、删除后旧版本 upsert 不会复活文档。
func TestRevisionGateSkipsOldUpsertAndPreventsResurrection(t *testing.T) {
	client, calls := newFakeMeili(t, false)
	handler := DebeziumHandler{MeiliClient: client, Revisions: NewMemoryRevisionStore()}

	ctx := context.Background()
	// 1) 写入 revision=5
	if err := handler.Handle(ctx, upsertEvent("app-x", "items", "doc-1", 5)); err != nil {
		t.Fatalf("handle rev5: %v", err)
	}
	// 2) 乱序到达的 revision=3（更旧）应被丢弃，不产生 AddDocuments
	if err := handler.Handle(ctx, upsertEvent("app-x", "items", "doc-1", 3)); err != nil {
		t.Fatalf("handle rev3: %v", err)
	}
	// 3) 删除 revision=7
	if err := handler.Handle(ctx, deleteEvent("app-x", "items", "doc-1", 7)); err != nil {
		t.Fatalf("handle delete rev7: %v", err)
	}
	// 4) 删除后迟到的 revision=6 upsert 必须被丢弃（不复活文档）
	if err := handler.Handle(ctx, upsertEvent("app-x", "items", "doc-1", 6)); err != nil {
		t.Fatalf("handle revive rev6: %v", err)
	}

	upserts, deletes := 0, 0
	for _, c := range *calls {
		if c.method == http.MethodPost && strings.HasSuffix(c.path, "/documents") {
			upserts++
		}
		if c.method == http.MethodDelete && strings.Contains(c.path, "/documents/") {
			deletes++
		}
	}
	if upserts != 1 {
		t.Fatalf("AddDocuments 调用次数 = %d, 期望 1（仅 rev5）", upserts)
	}
	if deletes != 1 {
		t.Fatalf("DeleteDocument 调用次数 = %d, 期望 1（仅 rev7）", deletes)
	}
}

func TestMeiliDocumentIDUsedForUpsertAndDelete(t *testing.T) {
	client, calls := newFakeMeili(t, false)
	handler := DebeziumHandler{MeiliClient: client}
	rawID := "part:54000762"

	if err := handler.Handle(context.Background(), upsertEvent("app-id", "items", rawID, 0)); err != nil {
		t.Fatalf("handle upsert: %v", err)
	}
	if err := handler.Handle(context.Background(), deleteEvent("app-id", "items", rawID, 0)); err != nil {
		t.Fatalf("handle delete: %v", err)
	}

	var upsertBody string
	var deletePath string
	for _, call := range *calls {
		if call.method == http.MethodPost && strings.HasSuffix(call.path, "/documents") {
			upsertBody = call.body
		}
		if call.method == http.MethodDelete && strings.Contains(call.path, "/documents/") {
			deletePath = call.path
		}
	}
	meiliID := model.MeiliDocumentID(rawID)
	if !strings.Contains(upsertBody, `"_meili_id":"`+meiliID+`"`) {
		t.Fatalf("upsert body does not contain encoded primary key %q: %s", meiliID, upsertBody)
	}
	if !strings.Contains(upsertBody, `"id":"`+rawID+`"`) {
		t.Fatalf("upsert body does not preserve raw ID %q: %s", rawID, upsertBody)
	}
	if !strings.HasSuffix(deletePath, "/documents/"+meiliID) {
		t.Fatalf("delete path = %q, want encoded ID %q", deletePath, meiliID)
	}
}

// TestRevisionGateIdempotentDuplicate 验证重复/重放同一 revision 是幂等的。
func TestRevisionGateIdempotentDuplicate(t *testing.T) {
	client, calls := newFakeMeili(t, false)
	handler := DebeziumHandler{MeiliClient: client, Revisions: NewMemoryRevisionStore()}
	ctx := context.Background()

	if err := handler.Handle(ctx, upsertEvent("app-y", "items", "doc-9", 4)); err != nil {
		t.Fatalf("handle rev4: %v", err)
	}
	// 完全相同的事件重放（同一 revision）应被丢弃。
	if err := handler.Handle(ctx, upsertEvent("app-y", "items", "doc-9", 4)); err != nil {
		t.Fatalf("handle duplicate rev4: %v", err)
	}

	upserts := 0
	for _, c := range *calls {
		if c.method == http.MethodPost && strings.HasSuffix(c.path, "/documents") {
			upserts++
		}
	}
	if upserts != 1 {
		t.Fatalf("AddDocuments 调用次数 = %d, 期望 1（重复事件幂等）", upserts)
	}
}

type fakeEpochGate struct {
	epoch string
	found bool
	err   error
}

func (g fakeEpochGate) AppEpoch(_ context.Context, _ string) (string, bool, error) {
	return g.epoch, g.found, g.err
}

// TestEpochGateSkipsStaleEpoch 验证应用生命周期 epoch 变化后，旧 epoch 的迟到事件被丢弃。
func TestEpochGateSkipsStaleEpoch(t *testing.T) {
	client, calls := newFakeMeili(t, false)
	// 当前 epoch=e2；事件携带 e1（旧）应被丢弃。
	handler := DebeziumHandler{
		MeiliClient: client,
		EpochGate:   fakeEpochGate{epoch: "e2", found: true},
		Revisions:   NewMemoryRevisionStore(),
	}
	ctx := context.Background()
	if err := handler.Handle(ctx, upsertEventEpoch("app-z", "items", "doc-1", 10, "e1")); err != nil {
		t.Fatalf("handle stale epoch: %v", err)
	}
	if len(*calls) != 0 {
		t.Fatalf("旧 epoch 事件不应触发 Meilisearch 调用, 实际调用 %d 次", len(*calls))
	}

	// 事件 epoch 与当前一致（e2）应正常执行。
	handler2 := DebeziumHandler{
		MeiliClient: client,
		EpochGate:   fakeEpochGate{epoch: "e2", found: true},
		Revisions:   NewMemoryRevisionStore(),
	}
	if err := handler2.Handle(ctx, upsertEventEpoch("app-z", "items", "doc-1", 10, "e2")); err != nil {
		t.Fatalf("handle current epoch: %v", err)
	}
	upserts := 0
	for _, c := range *calls {
		if c.method == http.MethodPost && strings.HasSuffix(c.path, "/documents") {
			upserts++
		}
	}
	if upserts != 1 {
		t.Fatalf("当前 epoch 事件应执行一次 AddDocuments, 实际 %d", upserts)
	}
}

// TestHandlerRetriesOnMeiliFailure 验证 Meilisearch 瞬时故障（503）返回非永久（可重试）错误，
// 使 Run 不提交该 partition 的 offset（崩溃/故障后最终一致）。
func TestHandlerRetriesOnMeiliFailure(t *testing.T) {
	client, _ := newFakeMeili(t, true) // meiliUnavailable=true -> POST 返回 503
	revisions := NewMemoryRevisionStore()
	handler := DebeziumHandler{MeiliClient: client, Revisions: revisions}
	err := handler.Handle(context.Background(), upsertEvent("app-f", "items", "doc-1", 1))
	if err == nil {
		t.Fatal("期望 Meilisearch 故障时返回错误")
	}
	if isPermanent(err) {
		t.Fatalf("Meilisearch 临时故障应可重试(非永久), 实际: %v", err)
	}
	if got := revisions.Applied("app-f", "items", "doc-1"); got != 0 {
		t.Fatalf("失败事件不能推进 revision，实际值=%d", got)
	}
}

func TestHandleBatchCoalescesUpsertsAndAdvancesRevisionsAfterTask(t *testing.T) {
	client, calls := newFakeMeili(t, false)
	revisions := NewMemoryRevisionStore()
	handler := DebeziumHandler{MeiliClient: client, Revisions: revisions}
	records := []*kgo.Record{
		upsertEvent("app-batch", "items", "one", 1),
		upsertEvent("app-batch", "items", "two", 2),
		upsertEvent("app-batch", "items", "three", 3),
	}

	results := handler.HandleBatch(context.Background(), records)
	if len(results) != len(records) {
		t.Fatalf("HandleBatch results = %d, want %d", len(results), len(records))
	}
	for _, result := range results {
		if result.Err != nil {
			t.Fatalf("HandleBatch error = %v", result.Err)
		}
	}

	posts := 0
	var body string
	for _, call := range *calls {
		if call.method == http.MethodPost && strings.HasSuffix(call.path, "/documents") {
			posts++
			body = call.body
		}
	}
	if posts != 1 {
		t.Fatalf("AddDocuments calls = %d, want 1", posts)
	}
	for _, id := range []string{"one", "two", "three"} {
		if !strings.Contains(body, `"id":"`+id+`"`) {
			t.Fatalf("batch request missing document %q: %s", id, body)
		}
	}
	for _, id := range []string{"one", "two", "three"} {
		if revisions.Applied("app-batch", "items", id) == 0 {
			t.Fatalf("revision was not advanced for %q", id)
		}
	}
}

func TestHandleBatchUsesBulkDelete(t *testing.T) {
	client, calls := newFakeMeili(t, false)
	handler := DebeziumHandler{MeiliClient: client}
	results := handler.HandleBatch(context.Background(), []*kgo.Record{
		deleteEvent("app-batch", "items", "one", 1),
		deleteEvent("app-batch", "items", "two", 2),
	})
	for _, result := range results {
		if result.Err != nil {
			t.Fatalf("HandleBatch error = %v", result.Err)
		}
	}
	deletes := 0
	for _, call := range *calls {
		if call.method == http.MethodPost && strings.HasSuffix(call.path, "/documents/delete-batch") {
			deletes++
			if !strings.Contains(call.body, model.MeiliDocumentID("one")) || !strings.Contains(call.body, model.MeiliDocumentID("two")) {
				t.Fatalf("bulk delete body = %s", call.body)
			}
		}
	}
	if deletes != 1 {
		t.Fatalf("DeleteDocuments calls = %d, want 1", deletes)
	}
}

func TestHandleBatchDoesNotAdvanceRevisionsOnRetryableFailure(t *testing.T) {
	client, _ := newFakeMeili(t, true)
	revisions := NewMemoryRevisionStore()
	handler := DebeziumHandler{MeiliClient: client, Revisions: revisions}
	results := handler.HandleBatch(context.Background(), []*kgo.Record{
		upsertEvent("app-batch", "items", "one", 1),
		upsertEvent("app-batch", "items", "two", 2),
	})
	if len(results) != 2 || results[0].Err == nil || isPermanent(results[0].Err) {
		t.Fatalf("expected retryable batch error, got %#v", results)
	}
	if revisions.Applied("app-batch", "items", "one") != 0 || revisions.Applied("app-batch", "items", "two") != 0 {
		t.Fatal("retryable batch failure must not advance revisions")
	}
}

func TestHandleBatchSplitsOnPermanentTaskFailure(t *testing.T) {
	var calls int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/documents"):
			calls++
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"taskUid":1}`))
		case strings.HasPrefix(r.URL.Path, "/tasks/"):
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"uid":1,"status":"failed","error":{"message":"invalid document","code":"invalid_document","type":"invalid_request"}}`))
		default:
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{}`))
		}
	}))
	defer server.Close()
	handler := DebeziumHandler{MeiliClient: meilisearch.New(server.URL)}
	results := handler.HandleBatch(context.Background(), []*kgo.Record{
		upsertEvent("app-batch", "items", "one", 1),
		upsertEvent("app-batch", "items", "two", 2),
	})
	if len(results) != 2 || !isPermanent(results[0].Err) || !isPermanent(results[1].Err) {
		t.Fatalf("expected permanent per-record errors, got %#v", results)
	}
	if calls != 3 { // initial two-record request plus two single-record probes
		t.Fatalf("AddDocuments calls = %d, want 3", calls)
	}
}

func TestWaitForTaskRetriesUnknownFailedTask(t *testing.T) {
	httpClient := &http.Client{Transport: roundTripFunc(func(_ *http.Request) (*http.Response, error) {
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(strings.NewReader(`{"uid":1,"status":"failed","error":{"message":"engine unavailable","code":"internal","type":"internal"}}`)),
		}, nil
	})}
	client := meilisearch.New("http://meili.test", meilisearch.WithCustomClient(httpClient))
	err := waitForTask(context.Background(), client, &meilisearch.TaskInfo{TaskUID: 1}, "test")
	if err == nil || isPermanent(err) {
		t.Fatalf("expected retryable failed task, got %v", err)
	}
}

func TestHandleBatchSplitsBySerializedPayloadSize(t *testing.T) {
	client, calls := newFakeMeili(t, false)
	handler := DebeziumHandler{MeiliClient: client, MaxBatchBytes: 80}
	results := handler.HandleBatch(context.Background(), []*kgo.Record{
		upsertEvent("app-batch", "items", "one", 1),
		upsertEvent("app-batch", "items", "two", 2),
	})
	for _, result := range results {
		if result.Err != nil {
			t.Fatalf("HandleBatch error = %v", result.Err)
		}
	}
	posts := 0
	for _, call := range *calls {
		if call.method == http.MethodPost && strings.HasSuffix(call.path, "/documents") {
			posts++
		}
	}
	if posts != 2 {
		t.Fatalf("AddDocuments calls = %d, want 2", posts)
	}
}

func TestHandleBatchKeepsPartitionsAndRevisionGateIsolated(t *testing.T) {
	client, calls := newFakeMeili(t, false)
	revisions := NewMemoryRevisionStore()
	handler := DebeziumHandler{MeiliClient: client, Revisions: revisions}
	newer := upsertEvent("app-batch", "items", "same", 2)
	older := upsertEvent("app-batch", "items", "same", 1)
	older.Partition = 1
	results := handler.HandleBatch(context.Background(), []*kgo.Record{newer, older})
	for _, result := range results {
		if result.Err != nil {
			t.Fatalf("HandleBatch error = %v", result.Err)
		}
	}
	posts := 0
	for _, call := range *calls {
		if call.method == http.MethodPost && strings.HasSuffix(call.path, "/documents") {
			posts++
		}
	}
	if posts != 1 {
		t.Fatalf("AddDocuments calls = %d, want 1 because stale revision must be skipped", posts)
	}
}

// TestExtractRevisionEpoch 验证从事件负载中提取 revision / epoch（缺省兼容）。
func TestExtractRevisionEpoch(t *testing.T) {
	rev, epoch := extractRevisionEpoch(map[string]interface{}{"revision": float64(7), "lifecycle_epoch": "e9"})
	if rev != 7 || epoch != "e9" {
		t.Fatalf("extractRevisionEpoch = (%d, %q), want (7, e9)", rev, epoch)
	}
	rev, epoch = extractRevisionEpoch(map[string]interface{}{"revision": "12"})
	if rev != 12 || epoch != "" {
		t.Fatalf("extractRevisionEpoch 字符串 revision = (%d, %q), want (12, \"\")", rev, epoch)
	}
	rev, epoch = extractRevisionEpoch(map[string]interface{}{"event_version": float64(13)})
	if rev != 13 || epoch != "" {
		t.Fatalf("extractRevisionEpoch event_version = (%d, %q), want (13, \"\")", rev, epoch)
	}
	rev, epoch = extractRevisionEpoch(map[string]interface{}{})
	if rev != 0 || epoch != "" {
		t.Fatalf("extractRevisionEpoch 缺省 = (%d, %q), want (0, \"\")", rev, epoch)
	}
}
