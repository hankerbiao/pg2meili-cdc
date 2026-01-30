package handler

import (
	"bytes"
	"io"
	"log"
	"net/http"
	"strings"

	"distributed-search/meilisearch-sync-service/internal/auth"
	"distributed-search/meilisearch-sync-service/internal/config"
)

func NewSearchHandler(cfg config.AppConfig) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
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
		token := parts[1]

		identity, err := auth.IdentityFromToken(token, cfg.JWTSecret)
		if err != nil {
			http.Error(w, "令牌无效: "+err.Error(), http.StatusUnauthorized)
			return
		}

		collection := r.URL.Query().Get("collection")
		if collection == "" {
			http.Error(w, "缺少 collection 参数", http.StatusBadRequest)
			return
		}
		if strings.Contains(collection, " ") {
			http.Error(w, "collection 不能包含空格", http.StatusBadRequest)
			return
		}

		indexUID := identity.AppName + "_" + collection

		bodyBytes, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "读取请求体失败", http.StatusBadRequest)
			return
		}
		defer r.Body.Close()

		meiliURL := strings.TrimRight(cfg.MeiliHost, "/") + "/indexes/" + indexUID + "/search"
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
			req.Header.Set("Authorization", "Bearer "+cfg.MeiliAPIKey)
		}

		resp, err := http.DefaultClient.Do(req)
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
