package service

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"

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

func TestProcessDebeziumMessageRejectsInvalidIDs(t *testing.T) {
	tests := []string{
		`{"payload":{"before":{"app_name":"app","collection":"items"},"op":"d"}}`,
		`{"payload":{"before":{"id":null,"app_name":"app","collection":"items"},"op":"d"}}`,
		`{"payload":{"after":{"id":null,"app_name":"app","collection":"items"},"op":"u"}}`,
	}
	for _, input := range tests {
		if _, _, _, _, err := processDebeziumMessage([]byte(input)); err == nil {
			t.Errorf("processDebeziumMessage(%s) accepted invalid id", input)
		}
	}
}

func TestProcessDebeziumMessageRejectsInvalidNestedPayload(t *testing.T) {
	input := `{"payload":{"after":{"id":1,"payload":42,"app_name":"app","collection":"items"},"op":"u"}}`
	if _, _, _, _, err := processDebeziumMessage([]byte(input)); err == nil {
		t.Fatal("expected invalid nested payload to be rejected")
	}
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
	op, id, doc, delID, err := processDebeziumMessage([]byte(input))
	if err != nil {
		t.Fatalf("processDebeziumMessage() error = %v", err)
	}
	if op != "c" || id != "doc-1" || delID != "" {
		t.Fatalf("unexpected outbox result: op=%s id=%s delID=%s", op, id, delID)
	}
	if doc["name"] != "x" || doc["id"] != "doc-1" {
		t.Fatalf("unexpected outbox document: %v", doc)
	}
	if ResolveIndex(doc) != model.IndexUID("app-a", "items") {
		t.Fatalf("unexpected outbox index route: %s", ResolveIndex(doc))
	}
}

func TestProcessSearchOutboxDelete(t *testing.T) {
	input := `{"payload":{"after":{"app_id":"app-b","collection":"items","document_id":"doc-2","operation":"delete","document":null},"op":"c"}}`
	op, id, doc, delID, err := processDebeziumMessage([]byte(input))
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
		if _, _, _, _, err := processDebeziumMessage([]byte(input)); err == nil {
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
				body := `{"uid":1,"status":"` + tt.status + `","error":{"message":"invalid document"}}`
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
