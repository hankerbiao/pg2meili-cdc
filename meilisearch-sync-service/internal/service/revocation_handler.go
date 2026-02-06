package service

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"

	"meilisearch-sync-service/internal/revocation"

	"github.com/twmb/franz-go/pkg/kgo"
)

type RevocationHandler struct {
	Cache *revocation.Cache
}

func (h RevocationHandler) Handle(ctx context.Context, record *kgo.Record) error {
	var event revocation.RevocationEvent
	if err := json.Unmarshal(record.Value, &event); err != nil {
		return fmt.Errorf("解码撤销消息失败: %w", err)
	}
	if event.Event != "token_revoked" || event.JTI == "" {
		return nil
	}
	if err := h.Cache.MarkRevoked(ctx, event.JTI, event); err != nil {
		log.Printf("Redis 异常，服务退出: %v", err)
		os.Exit(1)
	}
	return nil
}
