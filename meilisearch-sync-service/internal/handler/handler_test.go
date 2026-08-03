package handler

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"meilisearch-sync-service/internal/auth"
	"meilisearch-sync-service/internal/config"
)

const handlerTestSecret = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"

type handlerCredentialStore struct{}

func (handlerCredentialStore) Lookup(context.Context, string) (auth.KeyRecord, auth.AppRecord, error) {
	return auth.KeyRecord{
		ID: "ak_0123456789abcdef", AppID: "app-id", SecretHash: fmt.Sprintf("%x", sha256.Sum256([]byte(handlerTestSecret))),
		Scopes: []string{"search:read"}, Status: "active", ExpiresAt: "2099-01-01T00:00:00Z", Version: 1,
	}, auth.AppRecord{ID: "app-id", AppName: "app", Status: "active", Version: 1}, nil
}

func testAPIKey() string { return "ud_live_ak_0123456789abcdef." + handlerTestSecret }

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return f(request)
}

func TestSearchHandlerRequiresPost(t *testing.T) {
	handler := NewSearchHandler(config.AppConfig{}, nil)
	request := httptest.NewRequest(http.MethodGet, "/search", nil)
	response := httptest.NewRecorder()

	handler.ServeHTTP(response, request)
	if response.Code != http.StatusMethodNotAllowed {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusMethodNotAllowed)
	}
}

func TestSearchHandlerLimitsBodySize(t *testing.T) {
	handler := NewSearchHandler(config.AppConfig{}, handlerCredentialStore{})
	request := httptest.NewRequest(
		http.MethodPost,
		"/search?collection=items",
		strings.NewReader(strings.Repeat("x", maxSearchBodyBytes+1)),
	)
	request.Header.Set("Authorization", "Bearer "+testAPIKey())
	response := httptest.NewRecorder()

	handler.ServeHTTP(response, request)
	if response.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusRequestEntityTooLarge)
	}
}

func TestV1SearchHandlerReturnsStableEnvelope(t *testing.T) {
	originalClient := searchHTTPClient
	searchHTTPClient = &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		if r.URL.Path != "/indexes/app_items/search" {
			t.Fatalf("backend path = %q", r.URL.Path)
		}
		if r.Header.Get("X-Request-ID") != "request-123" {
			t.Fatalf("backend request id = %q", r.Header.Get("X-Request-ID"))
		}
		body, err := io.ReadAll(r.Body)
		if err != nil {
			t.Fatalf("read backend body: %v", err)
		}
		var request map[string]interface{}
		if err := json.Unmarshal(body, &request); err != nil {
			t.Fatalf("decode backend body: %v", err)
		}
		if request["q"] != "power" {
			t.Fatalf("query alias was not normalized: %v", request)
		}
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(strings.NewReader(`{"hits":[],"estimatedTotalHits":0}`)),
		}, nil
	})}
	t.Cleanup(func() { searchHTTPClient = originalClient })

	handler := NewV1SearchHandler(config.AppConfig{
		MeiliHost: "http://meili.test",
		RegionID:  "beijing",
	}, handlerCredentialStore{})
	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/collections/items/search",
		strings.NewReader(`{"query":"power","limit":20}`),
	)
	request.Header.Set("Authorization", "Bearer "+testAPIKey())
	request.Header.Set("X-Request-ID", "request-123")
	response := httptest.NewRecorder()

	handler.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", response.Code, response.Body.String())
	}
	if response.Header().Get("X-Request-ID") != "request-123" {
		t.Fatalf("response request id = %q", response.Header().Get("X-Request-ID"))
	}
	var envelope struct {
		Data map[string]interface{} `json:"data"`
		Meta struct {
			RequestID string `json:"request_id"`
			Region    string `json:"region"`
		} `json:"meta"`
		Error interface{} `json:"error"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if envelope.Meta.RequestID != "request-123" || envelope.Meta.Region != "beijing" {
		t.Fatalf("unexpected meta: %+v", envelope.Meta)
	}
	if envelope.Error != nil {
		t.Fatalf("unexpected error: %v", envelope.Error)
	}
}

func TestV1SearchHandlerRejectsInvalidCollection(t *testing.T) {
	handler := NewV1SearchHandler(config.AppConfig{}, nil)
	request := httptest.NewRequest(http.MethodPost, "/api/v1/collections/../private/search", nil)
	response := httptest.NewRecorder()

	handler.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusBadRequest)
	}
	assertV1ErrorCode(t, response, "INVALID_COLLECTION", false)
}

func TestV1SearchHandlerMapsBackendUnavailable(t *testing.T) {
	originalClient := searchHTTPClient
	searchHTTPClient = &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		return &http.Response{
			StatusCode: http.StatusInternalServerError,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(strings.NewReader(`{"message":"internal failure"}`)),
		}, nil
	})}
	t.Cleanup(func() { searchHTTPClient = originalClient })

	handler := NewV1SearchHandler(config.AppConfig{MeiliHost: "http://meili.test"}, handlerCredentialStore{})
	request := httptest.NewRequest(http.MethodPost, "/api/v1/collections/items/search", strings.NewReader(`{}`))
	request.Header.Set("Authorization", "Bearer "+testAPIKey())
	response := httptest.NewRecorder()

	handler.ServeHTTP(response, request)
	if response.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusServiceUnavailable)
	}
	assertV1ErrorCode(t, response, "SEARCH_BACKEND_UNAVAILABLE", true)
}

func assertV1ErrorCode(t *testing.T, response *httptest.ResponseRecorder, code string, retryable bool) {
	t.Helper()
	var envelope struct {
		Error *v1SearchError `json:"error"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	if envelope.Error == nil || envelope.Error.Code != code || envelope.Error.Retryable != retryable {
		t.Fatalf("unexpected error response: %+v", envelope.Error)
	}
}
