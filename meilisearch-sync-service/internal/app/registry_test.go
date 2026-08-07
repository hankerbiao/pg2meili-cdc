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
	}, nil, registry, config.AppConfig{})

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

	BuildHandlers(Topics{CDC: []string{"shared"}, Command: "shared"}, nil, nil, config.AppConfig{})
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

func TestWithCORSReflectsAllowedOrigin(t *testing.T) {
	handler := withCORS([]string{"https://console.example.com"})(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	request.Header.Set("Origin", "https://console.example.com")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if got := response.Header().Get("Access-Control-Allow-Origin"); got != "https://console.example.com" {
		t.Fatalf("Access-Control-Allow-Origin = %q, want https://console.example.com", got)
	}
}

func TestWithCORSRejectsDisallowedOrigin(t *testing.T) {
	handler := withCORS([]string{"https://console.example.com"})(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	request.Header.Set("Origin", "https://evil.example.com")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if got := response.Header().Get("Access-Control-Allow-Origin"); got != "" {
		t.Fatalf("disallowed origin should not get ACAO, got %q", got)
	}
	// 预检对未授权 Origin 返回 403。
	preflight := httptest.NewRequest(http.MethodOptions, "/health", nil)
	preflight.Header.Set("Origin", "https://evil.example.com")
	preflightResp := httptest.NewRecorder()
	handler.ServeHTTP(preflightResp, preflight)
	if preflightResp.Code != http.StatusForbidden {
		t.Fatalf("preflight status = %d, want 403", preflightResp.Code)
	}
}

func TestWithCORSAllowAllInDev(t *testing.T) {
	handler := withCORS(nil)(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	request := httptest.NewRequest(http.MethodGet, "/health", nil)
	request.Header.Set("Origin", "https://anything.example.com")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if got := response.Header().Get("Access-Control-Allow-Origin"); got != "*" {
		t.Fatalf("dev mode should reflect *, got %q", got)
	}
}
