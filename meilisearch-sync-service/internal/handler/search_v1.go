package handler

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"

	"meilisearch-sync-service/internal/auth"
	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/model"
)

const (
	v1SearchPathPrefix     = "/api/v1/collections/"
	maxSearchResponseBytes = 16 << 20
)

var (
	searchIdentifierPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`)
	requestIDPattern        = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,128}$`)
)

type v1SearchError struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	Retryable bool   `json:"retryable"`
}

type v1SearchMeta struct {
	RequestID  string `json:"request_id"`
	Region     string `json:"region,omitempty"`
	DurationMS int64  `json:"duration_ms,omitempty"`
}

type v1SearchEnvelope struct {
	Data  interface{}    `json:"data"`
	Meta  v1SearchMeta   `json:"meta"`
	Error *v1SearchError `json:"error"`
}

type searchRequestFailure struct {
	Status    int
	Code      string
	Message   string
	Retryable bool
}

// NewV1SearchHandler exposes a stable, versioned contract for backend integrations.
func NewV1SearchHandler(cfg config.AppConfig, credentialStore auth.CredentialStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		requestID := searchRequestID(r)
		w.Header().Set("X-Request-ID", requestID)
		w.Header().Set("Cache-Control", "no-store")

		if r.Method != http.MethodPost {
			w.Header().Set("Allow", http.MethodPost)
			writeV1SearchError(w, cfg, requestID, searchRequestFailure{
				Status:  http.StatusMethodNotAllowed,
				Code:    "METHOD_NOT_ALLOWED",
				Message: "仅支持 POST",
			})
			return
		}

		collection, failure := v1CollectionFromPath(r.URL.Path)
		if failure != nil {
			writeV1SearchError(w, cfg, requestID, *failure)
			return
		}

		identity, failure := authenticateV1Search(r, credentialStore)
		if failure != nil {
			writeV1SearchError(w, cfg, requestID, *failure)
			return
		}
		if !searchIdentifierPattern.MatchString(identity.AppName) {
			writeV1SearchError(w, cfg, requestID, searchRequestFailure{
				Status:  http.StatusUnauthorized,
				Code:    "INVALID_API_KEY_IDENTITY",
				Message: "API Key 对应的 app_name 格式无效",
			})
			return
		}

		body, failure := readV1SearchBody(w, r)
		if failure != nil {
			writeV1SearchError(w, cfg, requestID, *failure)
			return
		}

		indexUID := model.IndexUID(identity.AppName, collection)
		meiliURL := config.JoinURL(cfg.MeiliHost, "indexes/"+url.PathEscape(indexUID)+"/search")
		req, err := http.NewRequestWithContext(r.Context(), http.MethodPost, meiliURL, bytes.NewReader(body))
		if err != nil {
			log.Printf("构造 Meilisearch 请求失败 request_id=%s index=%s: %v", requestID, indexUID, err)
			writeV1SearchError(w, cfg, requestID, searchRequestFailure{
				Status:  http.StatusBadGateway,
				Code:    "SEARCH_BACKEND_REQUEST_FAILED",
				Message: "搜索服务请求构造失败",
			})
			return
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Request-ID", requestID)
		if cfg.MeiliAPIKey != "" {
			req.Header.Set("Authorization", "Bearer "+cfg.MeiliAPIKey)
		}

		startedAt := time.Now()
		resp, err := searchHTTPClient.Do(req)
		duration := time.Since(startedAt)
		if err != nil {
			log.Printf("执行 Meilisearch 搜索失败 request_id=%s index=%s: %v", requestID, indexUID, err)
			failure := searchTransportFailure(err)
			writeV1SearchErrorWithDuration(w, cfg, requestID, duration, failure)
			return
		}
		defer resp.Body.Close()

		responseBody, err := io.ReadAll(io.LimitReader(resp.Body, maxSearchResponseBytes+1))
		if err != nil {
			writeV1SearchErrorWithDuration(w, cfg, requestID, duration, searchRequestFailure{
				Status:    http.StatusBadGateway,
				Code:      "SEARCH_BACKEND_INVALID_RESPONSE",
				Message:   "读取搜索服务响应失败",
				Retryable: true,
			})
			return
		}
		if len(responseBody) > maxSearchResponseBytes {
			writeV1SearchErrorWithDuration(w, cfg, requestID, duration, searchRequestFailure{
				Status:  http.StatusBadGateway,
				Code:    "SEARCH_RESPONSE_TOO_LARGE",
				Message: "搜索服务响应过大",
			})
			return
		}

		if resp.StatusCode < http.StatusOK || resp.StatusCode >= http.StatusMultipleChoices {
			if retryAfter := resp.Header.Get("Retry-After"); retryAfter != "" {
				w.Header().Set("Retry-After", retryAfter)
			}
			failure := mapMeiliSearchFailure(resp.StatusCode, responseBody)
			writeV1SearchErrorWithDuration(w, cfg, requestID, duration, failure)
			return
		}

		var data interface{}
		if err := json.Unmarshal(responseBody, &data); err != nil {
			writeV1SearchErrorWithDuration(w, cfg, requestID, duration, searchRequestFailure{
				Status:    http.StatusBadGateway,
				Code:      "SEARCH_BACKEND_INVALID_RESPONSE",
				Message:   "搜索服务返回了无效 JSON",
				Retryable: true,
			})
			return
		}

		writeV1SearchJSON(w, http.StatusOK, v1SearchEnvelope{
			Data: data,
			Meta: v1SearchMeta{
				RequestID:  requestID,
				Region:     cfg.RegionID,
				DurationMS: duration.Milliseconds(),
			},
			Error: nil,
		})
	}
}

func v1CollectionFromPath(path string) (string, *searchRequestFailure) {
	if !strings.HasPrefix(path, v1SearchPathPrefix) {
		return "", invalidCollectionFailure()
	}
	remainder := strings.TrimPrefix(path, v1SearchPathPrefix)
	parts := strings.Split(remainder, "/")
	if len(parts) != 2 || parts[1] != "search" || !searchIdentifierPattern.MatchString(parts[0]) {
		return "", invalidCollectionFailure()
	}
	return parts[0], nil
}

func invalidCollectionFailure() *searchRequestFailure {
	return &searchRequestFailure{
		Status:  http.StatusBadRequest,
		Code:    "INVALID_COLLECTION",
		Message: "collection 只能包含字母、数字、下划线和连字符，长度为 1-128",
	}
}

func authenticateV1Search(r *http.Request, credentialStore auth.CredentialStore) (auth.AppIdentity, *searchRequestFailure) {
	authHeader := strings.TrimSpace(r.Header.Get("Authorization"))
	parts := strings.SplitN(authHeader, " ", 2)
	if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") || strings.TrimSpace(parts[1]) == "" {
		return auth.AppIdentity{}, &searchRequestFailure{
			Status:  http.StatusUnauthorized,
			Code:    "INVALID_AUTHORIZATION",
			Message: "需要有效的 Bearer API Key",
		}
	}

	identity, err := auth.IdentityFromAPIKey(r.Context(), strings.TrimSpace(parts[1]), credentialStore)
	if err != nil {
		if errors.Is(err, auth.ErrAuthUnavailable) {
			return auth.AppIdentity{}, &searchRequestFailure{
				Status: http.StatusServiceUnavailable, Code: "AUTH_SERVICE_UNAVAILABLE", Message: "鉴权服务暂时不可用", Retryable: true,
			}
		}
		return auth.AppIdentity{}, &searchRequestFailure{
			Status:  http.StatusUnauthorized,
			Code:    "INVALID_API_KEY",
			Message: "API Key 无效",
		}
	}
	if err := auth.RequireScopes(identity, []string{"search:read"}); err != nil {
		return auth.AppIdentity{}, &searchRequestFailure{
			Status:  http.StatusForbidden,
			Code:    "INSUFFICIENT_SCOPE",
			Message: "API Key 缺少 search:read 权限",
		}
	}
	return identity, nil
}

func readV1SearchBody(w http.ResponseWriter, r *http.Request) ([]byte, *searchRequestFailure) {
	r.Body = http.MaxBytesReader(w, r.Body, maxSearchBodyBytes)
	body, err := io.ReadAll(r.Body)
	if err != nil {
		var tooLarge *http.MaxBytesError
		if errors.As(err, &tooLarge) {
			return nil, &searchRequestFailure{
				Status:  http.StatusRequestEntityTooLarge,
				Code:    "REQUEST_BODY_TOO_LARGE",
				Message: "请求体不能超过 1 MB",
			}
		}
		return nil, &searchRequestFailure{
			Status:  http.StatusBadRequest,
			Code:    "INVALID_REQUEST_BODY",
			Message: "读取请求体失败",
		}
	}
	defer r.Body.Close()

	request := make(map[string]interface{})
	if len(bytes.TrimSpace(body)) > 0 {
		if err := json.Unmarshal(body, &request); err != nil {
			return nil, &searchRequestFailure{
				Status:  http.StatusBadRequest,
				Code:    "INVALID_JSON",
				Message: "请求体必须是 JSON 对象",
			}
		}
	}

	if query, ok := request["query"]; ok {
		if _, exists := request["q"]; !exists {
			request["q"] = query
		}
		delete(request, "query")
	}
	if highlight, ok := request["highlight"]; ok {
		if _, exists := request["attributesToHighlight"]; !exists {
			request["attributesToHighlight"] = highlight
		}
		delete(request, "highlight")
	}
	if _, ok := request["showRankingScore"]; !ok {
		request["showRankingScore"] = true
	}
	if rawLimit, ok := request["limit"]; ok {
		limit, valid := rawLimit.(float64)
		if !valid || limit < 1 || limit > 1000 || limit != float64(int(limit)) {
			return nil, &searchRequestFailure{
				Status:  http.StatusBadRequest,
				Code:    "INVALID_LIMIT",
				Message: "limit 必须是 1-1000 之间的整数",
			}
		}
	}

	normalized, err := json.Marshal(request)
	if err != nil {
		return nil, &searchRequestFailure{
			Status:  http.StatusBadRequest,
			Code:    "INVALID_REQUEST_BODY",
			Message: "请求参数无法序列化",
		}
	}
	return normalized, nil
}

func searchTransportFailure(err error) searchRequestFailure {
	if errors.Is(err, context.DeadlineExceeded) {
		return searchRequestFailure{
			Status:    http.StatusGatewayTimeout,
			Code:      "SEARCH_TIMEOUT",
			Message:   "搜索服务响应超时",
			Retryable: true,
		}
	}
	return searchRequestFailure{
		Status:    http.StatusBadGateway,
		Code:      "SEARCH_BACKEND_UNAVAILABLE",
		Message:   "无法连接搜索服务",
		Retryable: true,
	}
}

func mapMeiliSearchFailure(status int, body []byte) searchRequestFailure {
	message := meiliErrorMessage(body)
	switch status {
	case http.StatusBadRequest, http.StatusUnprocessableEntity:
		return searchRequestFailure{Status: http.StatusBadRequest, Code: "INVALID_SEARCH_REQUEST", Message: message}
	case http.StatusNotFound:
		return searchRequestFailure{Status: http.StatusNotFound, Code: "SEARCH_INDEX_NOT_FOUND", Message: "搜索集合不存在"}
	case http.StatusTooManyRequests:
		return searchRequestFailure{Status: http.StatusTooManyRequests, Code: "SEARCH_RATE_LIMITED", Message: "搜索请求过于频繁", Retryable: true}
	case http.StatusUnauthorized, http.StatusForbidden:
		return searchRequestFailure{Status: http.StatusBadGateway, Code: "SEARCH_BACKEND_AUTH_FAILED", Message: "搜索服务配置异常"}
	default:
		if status >= http.StatusInternalServerError {
			return searchRequestFailure{Status: http.StatusServiceUnavailable, Code: "SEARCH_BACKEND_UNAVAILABLE", Message: "搜索服务暂时不可用", Retryable: true}
		}
		return searchRequestFailure{Status: http.StatusBadGateway, Code: "SEARCH_BACKEND_ERROR", Message: "搜索服务返回异常响应"}
	}
}

func meiliErrorMessage(body []byte) string {
	var payload struct {
		Message string `json:"message"`
	}
	if json.Unmarshal(body, &payload) == nil && strings.TrimSpace(payload.Message) != "" {
		return payload.Message
	}
	return "搜索请求参数无效"
}

func searchRequestID(r *http.Request) string {
	if requestID := strings.TrimSpace(r.Header.Get("X-Request-ID")); requestIDPattern.MatchString(requestID) {
		return requestID
	}
	random := make([]byte, 16)
	if _, err := rand.Read(random); err == nil {
		return "req_" + hex.EncodeToString(random)
	}
	return fmt.Sprintf("req_%d", time.Now().UnixNano())
}

func writeV1SearchError(w http.ResponseWriter, cfg config.AppConfig, requestID string, failure searchRequestFailure) {
	writeV1SearchErrorWithDuration(w, cfg, requestID, 0, failure)
}

func writeV1SearchErrorWithDuration(w http.ResponseWriter, cfg config.AppConfig, requestID string, duration time.Duration, failure searchRequestFailure) {
	writeV1SearchJSON(w, failure.Status, v1SearchEnvelope{
		Data: nil,
		Meta: v1SearchMeta{
			RequestID:  requestID,
			Region:     cfg.RegionID,
			DurationMS: duration.Milliseconds(),
		},
		Error: &v1SearchError{
			Code:      failure.Code,
			Message:   failure.Message,
			Retryable: failure.Retryable,
		},
	})
}

func writeV1SearchJSON(w http.ResponseWriter, status int, payload v1SearchEnvelope) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		log.Printf("写入搜索 API 响应失败 request_id=%s: %v", payload.Meta.RequestID, err)
	}
}
