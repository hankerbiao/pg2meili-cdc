package service

import (
	"context"
	"fmt"

	"meilisearch-sync-service/internal/apikey"

	"github.com/twmb/franz-go/pkg/kgo"
)

// APIKeyEventHandler 将开放平台应用与 API Key 事件应用到区域 Redis。
type APIKeyEventHandler struct {
	Registry *apikey.Registry
}

func (h APIKeyEventHandler) Handle(ctx context.Context, record *kgo.Record) error {
	if h.Registry == nil {
		return permanent(fmt.Errorf("API Key registry 未初始化"))
	}
	if err := h.Registry.Apply(ctx, record.Value); err != nil {
		if apikey.IsPermanent(err) {
			return permanent(err)
		}
		return err
	}
	return nil
}
