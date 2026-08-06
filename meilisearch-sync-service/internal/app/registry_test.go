package app

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"

	"meilisearch-sync-service/internal/apikey"
	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/service"
)

func TestUniqueTopics(t *testing.T) {
	topics := Topics{
		CDC:     []string{"cdc-a", "", "cdc-a", "cdc-b"},
		Command: "commands",
		APIKey:  "api-keys",
	}

	want := []string{"cdc-a", "cdc-b", "commands", "api-keys"}
	if got := uniqueTopics(topics); !reflect.DeepEqual(got, want) {
		t.Fatalf("uniqueTopics() = %v, want %v", got, want)
	}
}

func TestBuildHandlers(t *testing.T) {
	registry := &apikey.Registry{}
	handlers := BuildHandlers(Topics{
		CDC:     []string{"cdc"},
		Command: "commands",
		APIKey:  "api-keys",
	}, nil, registry)

	tests := []struct {
		topic string
		want  any
	}{
		{topic: "cdc", want: service.DebeziumHandler{}},
		{topic: "commands", want: service.MeiliCommandHandler{}},
		{topic: "api-keys", want: service.APIKeyEventHandler{}},
	}
	for _, tt := range tests {
		if got := handlers[tt.topic]; reflect.TypeOf(got) != reflect.TypeOf(tt.want) {
			t.Errorf("handler for %q has type %T, want %T", tt.topic, got, tt.want)
		}
	}
}

func TestBuildHandlersRejectsDuplicateTopic(t *testing.T) {
	defer func() {
		if recover() == nil {
			t.Fatal("BuildHandlers() did not reject duplicate topic")
		}
	}()

	BuildHandlers(Topics{CDC: []string{"shared"}, Command: "shared"}, nil, nil)
}

func TestHealthReturnsJSON(t *testing.T) {
	server := newHTTPServer(config.AppConfig{HTTPAddr: ":8091"}, nil)
	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	response := httptest.NewRecorder()

	server.Handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusOK)
	}
	var body struct {
		Status string `json:"status"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("health response is not JSON: %v", err)
	}
	if body.Status != "healthy" {
		t.Fatalf("health status = %q, want healthy", body.Status)
	}
}
