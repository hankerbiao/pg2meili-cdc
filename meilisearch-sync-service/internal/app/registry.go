package app

import (
	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/revocation"
	"meilisearch-sync-service/internal/service"

	"github.com/meilisearch/meilisearch-go"
)

// Topics 聚合了同步服务关心的所有 Kafka topic。
// 通过一个结构体集中管理，便于在不同 handler 注册函数之间传递，
// 也让配置项在代码中具备明确语义（CDC、命令、吊销、DLQ 等）。
type Topics struct {
	// CDC 是用于消费业务库变更事件的 topic 列表（通常由 Debezium 产生）。
	CDC []string
	// Command 是用于下发索引配置、维护命令的 topic（例如创建/删除索引）。
	Command string
	// Revoke 是用于接收令牌吊销、权限变更等通知的 topic。
	Revoke string
	// DLQ 是死信队列的 topic，当消息无法正常消费时可以写入此处做后续排查。
	DLQ string
}

// BuildTopics 根据应用配置构造 Topics 实例。
// 该函数是配置到运行时结构的适配层，方便调用方在后续注册 handler 时直接使用语义化字段，
// 而不需要关心具体配置项的命名细节。
func BuildTopics(cfg config.AppConfig) Topics {
	// 将配置映射为语义化的 topic 集合。
	return Topics{
		CDC:     cfg.Topics,
		Command: cfg.CommandTopic,
		Revoke:  cfg.RevokeTopic,
		DLQ:     cfg.DLQTopic,
	}
}

// BuildHandlers 负责将各类 topic 绑定到对应的 handler，并返回一个路由表。
// 外层消费循环只需要根据消息所属的 topic，从返回的 map 中取出对应的 RecordHandler 即可。
//
// 新增 topic/handler 时的典型步骤：
// 1) 在 Topics 结构体中增加新的字段，或定义新的语义化 topic 分组；
// 2) 实现一个 registerXXXHandlers 函数，将该类 topic 与具体 handler 关联；
// 3) 在 BuildHandlers 中调用新的注册函数，完成统一注册。
func BuildHandlers(topics Topics, meiliClient meilisearch.ServiceManager, revocationCache *revocation.Cache) map[string]service.RecordHandler {
	// registry 保证 topic 不重复绑定。
	registry := newTopicRegistry()
	// CDC 变更消息处理（业务数据增删改同步到 Meilisearch）。
	registerCDCHandlers(registry, topics, meiliClient)
	// 管理类命令处理（索引创建、删除、设置更新等）。
	registerCommandHandlers(registry, topics, meiliClient)
	// 令牌吊销、权限变更通知处理。
	registerRevocationHandlers(registry, topics, revocationCache)
	// DLQ 目前只保留入口，未来如需消费可在此扩展。
	registerDLQHandlers(registry, topics, meiliClient)
	return registry.handlers
}

// topicRegistry 是内部使用的注册中心，用于维护 topic 到 handler 的一对一映射。
// 之所以单独定义结构体，而不是直接使用 map，是为了在注册阶段做一些约束检查，
// 例如防止相同 topic 被重复绑定不同的 handler。
type topicRegistry struct {
	handlers map[string]service.RecordHandler
}

// newTopicRegistry 创建一个空的 topicRegistry。
// 目前仅封装了 map 的初始化逻辑，后续如需增强（例如增加默认 handler）可以在这里集中修改。
func newTopicRegistry() *topicRegistry {
	// 初始化空的 registry。
	return &topicRegistry{
		handlers: make(map[string]service.RecordHandler),
	}
}

// register 将指定 topic 与 handler 关联起来。
// 保证一个 topic 只会有一个 handler，如果出现重复注册会直接 panic，
// 以便在启动阶段就暴露配置或代码问题，而不是在运行期默默覆盖。
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

// registerCDCHandlers 为所有 CDC 相关的 topic 注册统一的 DebeziumHandler。
// 这些 topic 通常承载数据库变更日志，handler 会解析 Debezium 事件并更新对应的 Meilisearch 索引。
func registerCDCHandlers(r *topicRegistry, topics Topics, meiliClient meilisearch.ServiceManager) {
	// CDC 默认使用 DebeziumHandler。
	handler := service.DebeziumHandler{MeiliClient: meiliClient}
	for _, topic := range topics.CDC {
		r.register(topic, handler)
	}
}

// registerCommandHandlers 为命令类 topic 注册 MeiliCommandHandler。
// 该 handler 负责处理对 Meilisearch 的管理操作，例如：创建/删除索引、更新索引设置等。
func registerCommandHandlers(r *topicRegistry, topics Topics, meiliClient meilisearch.ServiceManager) {
	// 命令类 topic 用于更新 Meilisearch 设置或索引操作。
	if topics.Command == "" {
		return
	}
	handler := service.MeiliCommandHandler{MeiliClient: meiliClient}
	r.register(topics.Command, handler)
}

// registerRevocationHandlers 为吊销相关的 topic 注册 RevocationHandler。
// 当上游产生令牌失效、权限回收等事件时，会写入该 topic，由 handler 更新本地缓存，
// 从而使搜索服务在短时间内感知到权限变更。
func registerRevocationHandlers(r *topicRegistry, topics Topics, revocationCache *revocation.Cache) {
	if topics.Revoke == "" || revocationCache == nil {
		return
	}
	handler := service.RevocationHandler{Cache: revocationCache}
	r.register(topics.Revoke, handler)
}

// registerDLQHandlers 为 DLQ 预留注册入口。
// 当前设计下 DLQ 仅作为写入目标（即“消息失败后写入 DLQ”），暂不在此服务中做消费。
// 如果未来需要从 DLQ 进行补偿或重放，只需在此函数中为 topics.DLQ 注册相应的 handler。
func registerDLQHandlers(r *topicRegistry, topics Topics, meiliClient meilisearch.ServiceManager) {
	// 当前 DLQ 仅用于写入，不消费。保留入口以便未来扩展。
	if topics.DLQ == "" {
		return
	}
}
