package handler

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"strings"

	"meilisearch-sync-service/internal/auth"
	"meilisearch-sync-service/internal/config"
)

// NewSearchHandler 返回一个基于 JWT 鉴权的 Meilisearch 搜索 HTTP 处理函数
func NewSearchHandler(cfg config.AppConfig) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// 读取并校验 Authorization 头，要求为 Bearer <token> 格式
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

		// 解析并验证 JWT，获得当前调用方的应用身份
		identity, err := auth.IdentityFromToken(token, cfg.JWTSecret)
		if err != nil {
			http.Error(w, "令牌无效: "+err.Error(), http.StatusUnauthorized)
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
		indexUID := identity.AppName + "_" + collection

		// 读取前端请求体，用于构造 Meilisearch 的 search 请求
		bodyBytes, err := io.ReadAll(r.Body)
		if err != nil {
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
			// 将 Meilisearch 的 API Key 作为下游请求的 Bearer 令牌
			req.Header.Set("Authorization", "Bearer "+cfg.MeiliAPIKey)
		}

		// 调用 Meilisearch，并将响应原样转发给前端
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
