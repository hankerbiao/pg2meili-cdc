package app

import (
	// app 包负责整个同步服务的装配与启动：
	// 1）创建 Meilisearch 客户端与 Kafka 消费者；
	// 2）初始化吊销缓存、HTTP 搜索代理；
	// 3）根据配置构建 topic -> handler 路由并启动消费循环；
	// 4）统一管理服务的启动与优雅关闭。
	"context"
	"log"
	"net/http"
	"time"

	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/handler"
	"meilisearch-sync-service/internal/logger"
	"meilisearch-sync-service/internal/revocation"
	"meilisearch-sync-service/internal/service"

	"github.com/meilisearch/meilisearch-go"
	"github.com/twmb/franz-go/pkg/kgo"
	"golang.org/x/sync/errgroup"
)

type App struct {
	// cfg 保存从外部加载的应用配置（包括 Kafka、Meilisearch、HTTP 等）。
	cfg config.AppConfig
	// topics 是基于 cfg 构造出的语义化 topic 集合，用于后续注册各类 handler。
	topics Topics
}

func New(cfg config.AppConfig) *App {
	// New 负责注入配置并构建 Topics。
	// 一般在 main 包中调用，用于完成 app 的最小初始化。
	return &App{
		cfg:    cfg,
		topics: BuildTopics(cfg),
	}
}

func (a *App) Run(ctx context.Context) error {
	// Run 是应用的主入口，负责启动所有核心组件并管理它们的生命周期。
	// 调用方通过传入的 ctx 控制整体退出（例如收到系统信号后 cancel）。

	// 1. 初始化全局日志器（根据 Debug 开关调整日志级别与格式）。
	logger.InitLogger(a.cfg.Debug)

	// 2. 创建 Meilisearch 客户端，用于后续索引写入和配置更新。
	meiliClient := newMeiliClient(a.cfg)

	// 3. 创建 Kafka 客户端并订阅所有需要消费的 topic。
	client, err := newKafkaClient(a.cfg, a.topics)
	if err != nil {
		return err
	}
	defer client.Close()

	// 4. 初始化令牌吊销缓存，用于搜索前的权限校验（黑名单/撤销列表）。
	revocationCache, err := revocation.NewCache(a.cfg)
	if err != nil {
		return err
	}
	defer func() {
		_ = revocationCache.Close()
	}()
	// 预热吊销缓存，使服务启动后立即具备最新的吊销状态。
	if err := revocationCache.Warmup(ctx); err != nil {
		return err
	}

	log.Printf(
		"服务启动，监听 cdcTopics=%v commandTopic=%s revokeTopic=%s dlqTopic=%s group=%s brokers=%v meiliHost=%s debug=%v",
		a.topics.CDC, a.topics.Command, a.topics.Revoke, a.topics.DLQ, a.cfg.GroupID, a.cfg.Brokers, a.cfg.MeiliHost, a.cfg.Debug,
	)

	// 5. 启动时向 UniData 注册本机代理信息（若配置了 UNIDATA_URL），
	// 便于管理端发现并展示当前可用的搜索代理节点。
	service.RegisterAgent(a.cfg)

	// 6. 创建对外 HTTP 服务，提供 /search 代理与 /health 健康检查接口。
	server := newHTTPServer(a.cfg, revocationCache)

	// 7. 使用 errgroup 并发管理 HTTP 服务与 Kafka 消费循环，
	// 任一子协程返回错误都会导致整体退出。
	g, ctx := errgroup.WithContext(ctx)

	g.Go(func() error {
		log.Printf("HTTP 服务启动，监听地址 %s", server.Addr)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			return err
		}
		return nil
	})

	g.Go(func() error {
		// 根据 topics 构建 topic -> handler 路由表。
		handlers := BuildHandlers(a.topics, meiliClient, revocationCache)
		// 启动消费主循环：从 Kafka 拉取消息，按 topic 分发给对应 handler。
		return service.Run(ctx, client, meiliClient, a.cfg, handlers)
	})

	// 8. 等待外部 ctx 被取消（例如收到中断信号）。
	<-ctx.Done()

	// 9. 在限定时间内优雅关闭 HTTP 服务，避免强制中断正在处理的请求。
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("HTTP 服务关闭失败: %v", err)
	}

	return g.Wait()
}

func newMeiliClient(cfg config.AppConfig) meilisearch.ServiceManager {
	// newMeiliClient 基于配置创建一个 Meilisearch 客户端。
	// 该客户端在整个应用生命周期内复用，用于：
	// 1）写入文档数据；
	// 2）更新索引设置（分词、排序规则等）；
	// 3）执行索引管理操作（创建/删除索引等）。
	return meilisearch.New(
		cfg.MeiliHost,
		meilisearch.WithAPIKey(cfg.MeiliAPIKey),
	)
}

func newKafkaClient(cfg config.AppConfig, topics Topics) (*kgo.Client, error) {
	// newKafkaClient 创建 Kafka 客户端，并以消费者身份订阅所有需要处理的 topic。
	// 使用 franz-go 提供的 kgo.Client，可以在单个 consumer group 内实现高可用消费。

	// 计算需要订阅的去重后的 topic 列表。
	subscribeTopics := uniqueTopics(topics)
	return kgo.NewClient(
		kgo.SeedBrokers(cfg.Brokers...),
		kgo.ConsumerGroup(cfg.GroupID),
		kgo.ConsumeTopics(subscribeTopics...),
		// 增大 SessionTimeout 以应对网络抖动或 handler 处理耗时稍长的情况。
		kgo.SessionTimeout(60*time.Second),
		// HeartbeatInterval 用于维持与 broker 的心跳，避免因心跳超时被移出消费组。
		kgo.HeartbeatInterval(5*time.Second),
	)
}

func uniqueTopics(topics Topics) []string {
	// uniqueTopics 负责从 Topics 中提取出所有需要订阅的 topic，并进行去重。
	// 由于同一个物理 topic 可能同时承载 CDC 与其他用途，这里通过 map 进行去重，
	// 保证 Kafka 客户端不会重复订阅同名 topic。
	seen := make(map[string]struct{})
	var result []string
	for _, t := range topics.CDC {
		if t == "" {
			continue
		}
		if _, ok := seen[t]; ok {
			continue
		}
		seen[t] = struct{}{}
		result = append(result, t)
	}
	if topics.Command != "" {
		if _, ok := seen[topics.Command]; !ok {
			seen[topics.Command] = struct{}{}
			result = append(result, topics.Command)
		}
	}
	if topics.Revoke != "" {
		if _, ok := seen[topics.Revoke]; !ok {
			seen[topics.Revoke] = struct{}{}
			result = append(result, topics.Revoke)
		}
	}
	if topics.DLQ != "" {
		if _, ok := seen[topics.DLQ]; !ok {
			seen[topics.DLQ] = struct{}{}
			result = append(result, topics.DLQ)
		}
	}
	return result
}

func newHTTPServer(cfg config.AppConfig, revocationCache *revocation.Cache) *http.Server {
	// newHTTPServer 创建对外的 HTTP Server。
	// 目前仅提供两个接口：
	// 1）/search：搜索代理，将请求转发到对应的 Meilisearch 集群；
	// 2）/health：健康检查，用于存活探测与监控。
	mux := http.NewServeMux()
	mux.Handle("/search", handler.NewSearchHandler(cfg, revocationCache))
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"healthy"}`))
	})

	return &http.Server{
		Addr:    cfg.HTTPAddr,
		Handler: withCORS(mux),
	}
}

func withCORS(h http.Handler) http.Handler {
	// withCORS 为 HTTP 接口增加简单的 CORS 支持，方便跨域调用搜索代理。
	// 当前策略较为宽松（允许任意 Origin），如需收紧可在此调整。
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

		reqHeaders := r.Header.Get("Access-Control-Request-Headers")
		if reqHeaders != "" {
			w.Header().Set("Access-Control-Allow-Headers", reqHeaders)
		} else {
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-App-Name, x-app-name")
		}

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}

		h.ServeHTTP(w, r)
	})
}
