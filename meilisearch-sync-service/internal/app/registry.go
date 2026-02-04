package app

import (
	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/service"

	"github.com/meilisearch/meilisearch-go"
)

type Topics struct {
	CDC     []string
	Command string
	DLQ     string
}

func BuildTopics(cfg config.AppConfig) Topics {
	// 将配置映射为语义化的 topic 集合。
	return Topics{
		CDC:     cfg.Topics,
		Command: cfg.CommandTopic,
		DLQ:     cfg.DLQTopic,
	}
}

// BuildHandlers 负责将各类 topic 绑定到对应的 handler。
// 新增 topic/handler 的步骤：
// 1) 在 Topics 结构体中增加字段或新增注册函数。
// 2) 在 BuildHandlers 中调用对应的注册函数完成绑定。
func BuildHandlers(topics Topics, meiliClient meilisearch.ServiceManager) map[string]service.RecordHandler {
	// registry 保证 topic 不重复绑定。
	registry := newTopicRegistry()
	registerCDCHandlers(registry, topics, meiliClient)
	registerCommandHandlers(registry, topics, meiliClient)
	registerDLQHandlers(registry, topics, meiliClient)
	return registry.handlers
}

type topicRegistry struct {
	handlers map[string]service.RecordHandler
}

func newTopicRegistry() *topicRegistry {
	// 初始化空的 registry。
	return &topicRegistry{
		handlers: make(map[string]service.RecordHandler),
	}
}

func (r *topicRegistry) register(topic string, handler service.RecordHandler) {
	// 防止重复绑定导致 handler 被覆盖。
	if topic == "" {
		return
	}
	if _, exists := r.handlers[topic]; exists {
		panic("topic 注册重复: " + topic)
	}
	r.handlers[topic] = handler
}

func registerCDCHandlers(r *topicRegistry, topics Topics, meiliClient meilisearch.ServiceManager) {
	// CDC 默认使用 DebeziumHandler。
	handler := service.DebeziumHandler{MeiliClient: meiliClient}
	for _, topic := range topics.CDC {
		r.register(topic, handler)
	}
}

func registerCommandHandlers(r *topicRegistry, topics Topics, meiliClient meilisearch.ServiceManager) {
	// 命令类 topic 用于更新 Meilisearch 设置或索引操作。
	if topics.Command == "" {
		return
	}
	handler := service.MeiliCommandHandler{MeiliClient: meiliClient}
	r.register(topics.Command, handler)
}

func registerDLQHandlers(r *topicRegistry, topics Topics, meiliClient meilisearch.ServiceManager) {
	// 当前 DLQ 仅用于写入，不消费。保留入口以便未来扩展。
	if topics.DLQ == "" {
		return
	}
}
