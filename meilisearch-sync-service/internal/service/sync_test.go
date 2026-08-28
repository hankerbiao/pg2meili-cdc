package service

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"

	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/model"

	"github.com/meilisearch/meilisearch-go"
	"github.com/twmb/franz-go/pkg/kgo"
)

type fakeProducer struct {
	err      error
	produced *kgo.Record
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return fn(request)
}

func (p *fakeProducer) ProduceSync(_ context.Context, records ...*kgo.Record) kgo.ProduceResults {
	p.produced = records[0]
	return kgo.ProduceResults{{Record: records[0], Err: p.err}}
}

func TestResolveIndexRequiresStringRoutingFields(t *testing.T) {
	if got := ResolveIndex(map[string]interface{}{"app_id": nil, "collection": "items"}); got != "" {
		t.Fatalf("ResolveIndex() = %q, want empty", got)
	}
	if got := ResolveIndex(map[string]interface{}{"app_id": "app", "collection": "items"}); got != model.IndexUID("app", "items") {
		t.Fatalf("ResolveIndex() = %q, want %q", got, model.IndexUID("app", "items"))
	}
}

func TestProcessSearchOutboxUpsert(t *testing.T) {
	input := `{"payload":{"after":{"app_id":"app-a","collection":"items","document_id":"doc-1","operation":"upsert","document":{"name":"x"}},"op":"c"}}`
	op, id, doc, delID, _, _, err := processDebeziumMessage([]byte(input))
	if err != nil {
		t.Fatalf("processDebeziumMessage() error = %v", err)
	}
	if op != "c" || id != "doc-1" || delID != "" {
		t.Fatalf("unexpected outbox result: op=%s id=%s delID=%s", op, id, delID)
	}
	if doc["name"] != "x" || doc["id"] != "doc-1" {
		t.Fatalf("unexpected outbox document: %v", doc)
	}
	if doc["_meili_id"] != model.MeiliDocumentID("doc-1") {
		t.Fatalf("unexpected Meilisearch document ID: %v", doc["_meili_id"])
	}
	if ResolveIndex(doc) != model.IndexUID("app-a", "items") {
		t.Fatalf("unexpected outbox index route: %s", ResolveIndex(doc))
	}
}

func TestProcessSearchOutboxUpsertWithStringDocument(t *testing.T) {
	// Debezium JsonConverter with schemas.enable=true serializes the
	// io.debezium.data.Json document column as a JSON string (not an object).
	input := `{"payload":{"after":{"app_id":"app-a","collection":"items","document_id":"doc-1","operation":"upsert","document":"{\"name\":\"x\"}"},"op":"c"}}`
	op, id, doc, delID, _, _, err := processDebeziumMessage([]byte(input))
	if err != nil {
		t.Fatalf("processDebeziumMessage() error = %v", err)
	}
	if op != "c" || id != "doc-1" || delID != "" {
		t.Fatalf("unexpected outbox result: op=%s id=%s delID=%s", op, id, delID)
	}
	if doc["name"] != "x" || doc["id"] != "doc-1" {
		t.Fatalf("unexpected outbox document: %v", doc)
	}
	if doc["_meili_id"] != model.MeiliDocumentID("doc-1") {
		t.Fatalf("unexpected Meilisearch document ID: %v", doc["_meili_id"])
	}
	if ResolveIndex(doc) != model.IndexUID("app-a", "items") {
		t.Fatalf("unexpected outbox index route: %s", ResolveIndex(doc))
	}
}

func TestProcessSearchOutboxDelete(t *testing.T) {
	input := `{"payload":{"after":{"app_id":"app-b","collection":"items","document_id":"doc-2","operation":"delete","document":null},"op":"c"}}`
	op, id, doc, delID, _, _, err := processDebeziumMessage([]byte(input))
	if err != nil {
		t.Fatalf("processDebeziumMessage() error = %v", err)
	}
	if op != "d" || id != "" || delID != "doc-2" {
		t.Fatalf("unexpected outbox delete result: op=%s id=%s delID=%s", op, id, delID)
	}
	if ResolveIndex(doc) != model.IndexUID("app-b", "items") {
		t.Fatalf("unexpected delete index route: %s", ResolveIndex(doc))
	}
}

func TestProcessSearchOutboxRequiresRouteFields(t *testing.T) {
	for _, input := range []string{
		`{"payload":{"after":{"collection":"items","document_id":"doc-1","operation":"upsert","document":{}},"op":"c"}}`,
		`{"payload":{"after":{"app_id":"app-a","document_id":"doc-1","operation":"upsert","document":{}},"op":"c"}}`,
		`{"payload":{"after":{"app_id":"app-a","collection":"items","operation":"upsert","document":{}},"op":"c"}}`,
		`{"payload":{"after":{"app_id":"app-a","collection":"items","document_id":"doc-1","operation":"unknown","document":{}},"op":"c"}}`,
	} {
		if _, _, _, _, _, _, err := processDebeziumMessage([]byte(input)); err == nil {
			t.Fatalf("processDebeziumMessage(%s) accepted invalid outbox event", input)
		}
	}
}

func TestValidateMeiliCommandRejectsMismatchedIndex(t *testing.T) {
	cmd := model.MeiliCommand{IndexUID: "wrong", AppID: "app-a", Collection: "items", Action: "update_settings"}
	if err := validateMeiliCommand(cmd); err == nil {
		t.Fatal("expected mismatched index UID rejection")
	}
	cmd.IndexUID = model.IndexUID(cmd.AppID, cmd.Collection)
	if err := validateMeiliCommand(cmd); err != nil {
		t.Fatalf("validateMeiliCommand() error = %v", err)
	}
}

func TestCommandTargetsRegion(t *testing.T) {
	if !commandTargetsRegion([]string{"cn-bj", "cn-sh"}, "cn-sh") {
		t.Fatal("targeted region should execute cleanup command")
	}
	if commandTargetsRegion([]string{"cn-bj"}, "cn-sh") {
		t.Fatal("non-target region must not execute cleanup command")
	}
	if commandTargetsRegion([]string{"cn-bj"}, "") {
		t.Fatal("empty region must not acknowledge cleanup command")
	}
}

func TestSendToDLQ(t *testing.T) {
	record := &kgo.Record{Topic: "source", Partition: 2, Offset: 7, Value: []byte("payload")}
	producer := &fakeProducer{}
	if err := sendToDLQ(context.Background(), producer, config.AppConfig{DLQTopic: "dlq"}, record, errors.New("bad message")); err != nil {
		t.Fatalf("sendToDLQ() error = %v", err)
	}

	var message DLQMessage
	if err := json.Unmarshal(producer.produced.Value, &message); err != nil {
		t.Fatalf("decode DLQ message: %v", err)
	}
	if message.SourceTopic != record.Topic || message.SourceOffset != record.Offset {
		t.Fatalf("unexpected DLQ message: %+v", message)
	}
}

func TestSendToDLQPropagatesFailure(t *testing.T) {
	producer := &fakeProducer{err: errors.New("kafka unavailable")}
	err := sendToDLQ(context.Background(), producer, config.AppConfig{DLQTopic: "dlq"}, &kgo.Record{}, errors.New("bad message"))
	if err == nil || !strings.Contains(err.Error(), "kafka unavailable") {
		t.Fatalf("sendToDLQ() error = %v", err)
	}
}

func TestSummarizeFetchErrorsDeduplicatesAndSorts(t *testing.T) {
	errs := []kgo.FetchError{
		{Topic: "topic-b", Partition: 0, Err: errors.New("UNKNOWN_TOPIC_ID")},
		{Topic: "topic-a", Partition: 0, Err: errors.New("UNKNOWN_TOPIC_ID")},
		{Topic: "topic-b", Partition: 1, Err: errors.New("UNKNOWN_TOPIC_ID")},
	}
	got := summarizeFetchErrors(errs)
	want := "topic-a UNKNOWN_TOPIC_ID; topic-b UNKNOWN_TOPIC_ID（x2）"
	if got != want {
		t.Fatalf("summarizeFetchErrors() = %q, want %q", got, want)
	}
}

func TestWaitForRetryHonorsCancellation(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := waitForRetry(ctx, time.Hour); !errors.Is(err, context.Canceled) {
		t.Fatalf("waitForRetry() error = %v, want context.Canceled", err)
	}
}

func TestWaitForTaskChecksFinalStatus(t *testing.T) {
	tests := []struct {
		status    string
		permanent bool
	}{
		{status: "succeeded"},
		{status: "failed", permanent: true},
	}
	for _, tt := range tests {
		t.Run(tt.status, func(t *testing.T) {
			httpClient := &http.Client{Transport: roundTripFunc(func(_ *http.Request) (*http.Response, error) {
				body := `{"uid":1,"status":"` + tt.status + `","error":{"message":"invalid document","code":"invalid_document","type":"invalid_request"}}`
				return &http.Response{
					StatusCode: http.StatusOK,
					Header:     http.Header{"Content-Type": []string{"application/json"}},
					Body:       io.NopCloser(strings.NewReader(body)),
				}, nil
			})}
			client := meilisearch.New("http://meili.test", meilisearch.WithCustomClient(httpClient))
			err := waitForTask(context.Background(), client, &meilisearch.TaskInfo{TaskUID: 1}, "test")
			if tt.permanent != isPermanent(err) {
				t.Fatalf("waitForTask() error = %v, permanent = %v", err, isPermanent(err))
			}
			if !tt.permanent && err != nil {
				t.Fatalf("waitForTask() error = %v", err)
			}
		})
	}
}

type fakeTenantGate struct {
	status string
	found  bool
	err    error
}

func (g fakeTenantGate) AppStatus(_ context.Context, _ string) (string, bool, error) {
	return g.status, g.found, g.err
}

func TestTenantGateSkipsRetiredTenants(t *testing.T) {
	for _, status := range []string{"deleting", "deleted"} {
		t.Run(status, func(t *testing.T) {
			handler := DebeziumHandler{TenantGate: fakeTenantGate{status: status, found: true}}
			record := &kgo.Record{Topic: "pg.public.search_outbox", Partition: 0, Offset: 1}
			skip, err := handler.tenantGateDecision(
				context.Background(),
				record,
				map[string]interface{}{"app_id": "app-x"},
			)
			if err != nil {
				t.Fatalf("tenantGateDecision() error = %v", err)
			}
			if !skip {
				t.Fatalf("expected message for %s tenant to be skipped", status)
			}
		})
	}
}

func TestTenantGateAllowsActiveTenant(t *testing.T) {
	handler := DebeziumHandler{TenantGate: fakeTenantGate{status: "active", found: true}}
	skip, err := handler.tenantGateDecision(
		context.Background(),
		&kgo.Record{},
		map[string]interface{}{"app_id": "app-x"},
	)
	if err != nil || skip {
		t.Fatalf("active tenant should be allowed, skip=%v err=%v", skip, err)
	}
}

func TestTenantGateRetriesUnknownTenant(t *testing.T) {
	handler := DebeziumHandler{TenantGate: fakeTenantGate{found: false}}
	_, err := handler.tenantGateDecision(
		context.Background(),
		&kgo.Record{},
		map[string]interface{}{"app_id": "app-x"},
	)
	if err == nil {
		t.Fatal("unknown tenant should be retried")
	}
}

func TestTenantGatePropagatesRegistryError(t *testing.T) {
	handler := DebeziumHandler{TenantGate: fakeTenantGate{err: errors.New("redis unavailable")}}
	_, err := handler.tenantGateDecision(
		context.Background(),
		&kgo.Record{},
		map[string]interface{}{"app_id": "app-x"},
	)
	if err == nil {
		t.Fatal("expected registry error to propagate for retry")
	}
}

func TestTenantGateIgnoresMissingRoutingField(t *testing.T) {
	handler := DebeziumHandler{TenantGate: fakeTenantGate{status: "deleted", found: true}}
	skip, err := handler.tenantGateDecision(context.Background(), &kgo.Record{}, map[string]interface{}{})
	if err != nil {
		t.Fatalf("tenantGateDecision() error = %v", err)
	}
	if skip {
		t.Fatal("message without app_id should be left for ResolveIndex handling")
	}
}
