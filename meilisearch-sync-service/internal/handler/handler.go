package handler

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"meilisearch-sync-service/internal/auth"
	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/model"
)

const maxSearchBodyBytes = 1 << 20

var searchHTTPClient = &http.Client{Timeout: 10 * time.Second}

// NewSearchHandler 返回一个基于开放平台 API Key 鉴权的 Meilisearch 搜索处理函数。
func NewSearchHandler(cfg config.AppConfig, credentialStore auth.CredentialStore) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", http.MethodPost)
			http.Error(w, "仅支持 POST", http.StatusMethodNotAllowed)
			return
		}

		// 读取并校验 Authorization 头，要求为 Bearer <api_key> 格式。
		authHeader := r.Header.Get("Authorization")
		if authHeader == "" {
			http.Error(w, "缺少 Authorization 头", http.StatusUnauthorized)
			return
		}
		parts := strings.SplitN(authHeader, " ", 2)
		if len(parts) != 2 || strings.ToLower(parts[0]) != "bearer" {
			http.Error(w, "Authorization 格式无效", http.StatusUnauthorized)
			return
		}
		credential := parts[1]

		identity, err := auth.IdentityFromAPIKey(r.Context(), credential, credentialStore)
		if err != nil {
			if errors.Is(err, auth.ErrAuthUnavailable) {
				http.Error(w, "鉴权服务暂时不可用", http.StatusServiceUnavailable)
				return
			}
			http.Error(w, "API Key 无效", http.StatusUnauthorized)
			return
		}
		if err := auth.RequireScopes(identity, []string{"search:read"}); err != nil {
			http.Error(w, err.Error(), http.StatusForbidden)
			return
		}
		// 从查询参数中获取 collection，用于拼接索引名称
		collection := r.URL.Query().Get("collection")
		if collection == "" {
			http.Error(w, "缺少 collection 参数", http.StatusBadRequest)
			return
		}
		if strings.Contains(collection, " ") {
			http.Error(w, "collection 不能包含空格", http.StatusBadRequest)
			return
		}

		// 索引命名规则：<app_name>_<collection>
		indexUID := model.IndexUID(identity.AppName, collection)

		// 读取前端请求体，用于构造 Meilisearch 的 search 请求
		r.Body = http.MaxBytesReader(w, r.Body, maxSearchBodyBytes)
		bodyBytes, err := io.ReadAll(r.Body)
		if err != nil {
			var tooLarge *http.MaxBytesError
			if errors.As(err, &tooLarge) {
				http.Error(w, "请求体过大", http.StatusRequestEntityTooLarge)
				return
			}
			http.Error(w, "读取请求体失败", http.StatusBadRequest)
			return
		}
		defer r.Body.Close()

		// 如果请求体为空，或者请求体中未显式声明 showRankingScore，则默认开启
		if len(bodyBytes) == 0 {
			bodyBytes, _ = json.Marshal(map[string]interface{}{"showRankingScore": true})
		} else {
			var obj map[string]interface{}
			if err := json.Unmarshal(bodyBytes, &obj); err == nil {
				if _, ok := obj["showRankingScore"]; !ok {
					obj["showRankingScore"] = true
					bodyBytes, _ = json.Marshal(obj)
				}
			}
		}

		// 构造 Meilisearch 搜索接口的 URL，并在调试模式下打印请求信息
		meiliURL := config.JoinURL(cfg.MeiliHost, "indexes/"+indexUID+"/search")
		if cfg.Debug {
			log.Printf("Meilisearch 请求 index=%s app=%s url=%s body=%s", indexUID, identity.AppName, meiliURL, string(bodyBytes))
		}
		req, err := http.NewRequestWithContext(r.Context(), http.MethodPost, meiliURL, bytes.NewReader(bodyBytes))
		if err != nil {
			log.Printf("构造 Meilisearch 请求失败 index=%s app=%s 错误=%v", indexUID, identity.AppName, err)
			http.Error(w, "搜索失败", http.StatusInternalServerError)
			return
		}
		req.Header.Set("Content-Type", "application/json")
		if cfg.MeiliAPIKey != "" {
			// 将 Meilisearch 的 API Key 作为下游请求的 Bearer 令牌
			req.Header.Set("Authorization", "Bearer "+cfg.MeiliAPIKey)
		}

		// 调用 Meilisearch，并将响应原样转发给前端
		resp, err := searchHTTPClient.Do(req)
		if err != nil {
			log.Printf("执行 Meilisearch 搜索失败 index=%s app=%s 错误=%v", indexUID, identity.AppName, err)
			http.Error(w, "搜索失败", http.StatusInternalServerError)
			return
		}
		defer resp.Body.Close()

		for k, vv := range resp.Header {
			for _, v := range vv {
				w.Header().Add(k, v)
			}
		}
		w.WriteHeader(resp.StatusCode)
		if _, err := io.Copy(w, resp.Body); err != nil {
			log.Printf("转发 Meilisearch 响应失败: %v", err)
		}
	}
}
