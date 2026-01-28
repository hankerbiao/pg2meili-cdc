package handler

import (
	"encoding/json"
	"log"
	"net/http"
	"strings"

	"distributed-search/meilisearch-sync-service/internal/auth"
	"distributed-search/meilisearch-sync-service/internal/config"
	"distributed-search/meilisearch-sync-service/internal/model"

	"github.com/meilisearch/meilisearch-go"
)

func NewSearchHandler(meiliClient meilisearch.ServiceManager, cfg config.AppConfig) http.HandlerFunc {
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

		defer r.Body.Close()
		var req model.SearchProxyRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, "请求体不是有效 JSON", http.StatusBadRequest)
			return
		}
		if req.Q == "" {
			http.Error(w, "缺少 q 字段", http.StatusBadRequest)
			return
		}

		expectedIndex := cfg.MeiliIndex
		if identity.AppName != "" {
			expectedIndex = identity.AppName + "_" + cfg.MeiliIndex
		}

		indexUID := req.IndexUID
		if indexUID == "" {
			indexUID = expectedIndex
		} else if indexUID != expectedIndex {
			http.Error(w, "无权访问该索引", http.StatusForbidden)
			return
		}

		searchReq := &meilisearch.SearchRequest{}
		if req.Offset != nil {
			searchReq.Offset = *req.Offset
		}
		if req.Limit != nil {
			searchReq.Limit = *req.Limit
		}
		if req.Filter != nil {
			searchReq.Filter = req.Filter
		}
		if len(req.Sort) > 0 {
			searchReq.Sort = req.Sort
		}

		resp, err := meiliClient.Index(indexUID).Search(req.Q, searchReq)
		if err != nil {
			log.Printf("执行 Meilisearch 搜索失败 index=%s app=%s 错误=%v", indexUID, identity.AppName, err)
			http.Error(w, "搜索失败", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json; charset=utf-8")
		if err := json.NewEncoder(w).Encode(resp); err != nil {
			log.Printf("编码搜索响应失败: %v", err)
		}
	}
}
