package app

import (
	"context"
	"meilisearch-sync-service/internal/apikey"
	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/model"
	"meilisearch-sync-service/internal/service"

	"github.com/meilisearch/meilisearch-go"
)

// Topics 聚合了同步服务需要消费的 Kafka topic。
type Topics struct {
	// CDC 是用于消费业务库变更事件的 topic 列表（通常由 Debezium 产生）。
	CDC []string
	// Command 是用于下发索引配置、维护命令的 topic（例如创建/删除索引）。
	Command string
	// APIKey 是用于接收应用与 API Key 生命周期事件的 topic。
	APIKey string
}

// BuildHandlers 将消费 topic 绑定到对应的消息处理器。
func BuildHandlers(topics Topics, meiliClient meilisearch.ServiceManager, registry *apikey.Registry, cfg config.AppConfig) map[string]service.RecordHandler {
	handlers := make(map[string]service.RecordHandler)
	register := func(topic string, handler service.RecordHandler) {
		if topic == "" {
			return
		}
		if _, exists := handlers[topic]; exists {
			panic("topic 注册重复: " + topic)
		}
		handlers[topic] = handler
	}

	// registry 同时充当租户状态门禁与生命周期 epoch 门禁：跳过已回收租户的
	// CDC 消息，并丢弃应用删除/重建后旧 epoch 的迟到事件，防止索引复活。
	// Revisions 提供文档级 revision 门禁（内存实现），丢弃乱序/重放的旧版本事件。
	cdcHandler := service.DebeziumHandler{
		MeiliClient:   meiliClient,
		TenantGate:    registry,
		EpochGate:     registry,
		Revisions:     service.NewMemoryRevisionStore(),
		MaxBatchBytes: cfg.MeiliBatchMaxBytes,
	}
	for _, topic := range topics.CDC {
		register(topic, cdcHandler)
	}
	register(topics.Command, service.MeiliCommandHandler{
		MeiliClient: meiliClient,
		RegionID:    cfg.RegionID,
		ConfirmCleanup: func(ctx context.Context, cmd model.MeiliCommand) error {
			return service.ConfirmCleanupDeletion(ctx, cfg, cmd)
		},
	})
	if registry != nil {
		register(topics.APIKey, service.APIKeyEventHandler{Registry: registry})
	}
	return handlers
}
