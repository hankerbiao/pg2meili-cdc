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
	if got := ResolveIndex(map[string]interface{}{"app_name": nil, "collection": "items"}); got != "" {
		t.Fatalf("ResolveIndex() = %q, want empty", got)
	}
	if got := ResolveIndex(map[string]interface{}{"app_name": "app", "collection": "items"}); got != "app_items" {
		t.Fatalf("ResolveIndex() = %q, want app_items", got)
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
