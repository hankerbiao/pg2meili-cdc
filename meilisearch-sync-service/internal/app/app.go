package app

import (
	// app 包负责整个同步服务的装配与启动：
	// 1）创建 Meilisearch 客户端与 Kafka 消费者；
	// 2）初始化 API Key 注册表、HTTP 搜索代理；
	// 3）根据配置构建 topic -> handler 路由并启动消费循环；
	// 4）统一管理服务的启动与优雅关闭。
	"context"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"meilisearch-sync-service/internal/apikey"
	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/handler"
	"meilisearch-sync-service/internal/logger"
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
		cfg: cfg,
		topics: Topics{
			CDC:     cfg.Topics,
			Command: cfg.CommandTopic,
			APIKey:  cfg.APIKeyTopic,
		},
	}
}

func (a *App) Run(ctx context.Context) error {
	// Run 是应用的主入口，负责启动所有核心组件并管理它们的生命周期。
	// 调用方通过传入的 ctx 控制整体退出（例如收到系统信号后 cancel）。

	if err := a.cfg.Validate(); err != nil {
		return fmt.Errorf("配置校验失败: %w", err)
	}
	// 1. 初始化全局日志器（根据 Debug 开关调整日志级别与格式）。
	logger.InitLogger(a.cfg.Debug)

	// 2. 创建 Meilisearch 客户端，用于后续索引写入和配置更新。
	meiliClient := newMeiliClient(a.cfg)

	// 3. 为 CDC 与 API Key 事件建立独立的消费者。
	// CDC 写入 Meilisearch 可能耗时较长，不能阻塞 API Key 更新，否则新密钥
	// 会在快照回放期间持续返回 401。
	cdcClient, err := newKafkaClient(a.cfg, a.cfg.GroupID, append(a.topics.CDC, a.topics.Command))
	if err != nil {
		return err
	}
	defer cdcClient.Close()
	apiKeyClient, err := newKafkaClient(a.cfg, a.cfg.GroupID+"-api-keys", []string{a.topics.APIKey})
	if err != nil {
		return err
	}
	defer apiKeyClient.Close()

	// 4. 初始化并预热区域 API Key 注册表。
	keyRegistry, err := apikey.New(a.cfg)
	if err != nil {
		return err
	}
	defer func() {
		_ = keyRegistry.Close()
	}()
	if err := keyRegistry.Warmup(ctx, a.cfg); err != nil {
		return err
	}
	log.Printf(
		"服务启动，监听 region=%s cdcTopics=%v commandTopic=%s apiKeyTopic=%s dlqTopic=%s group=%s brokers=%v meiliHost=%s batchEnabled=%v batchSize=%d batchFlushMS=%d batchMaxBytes=%d debug=%v",
		a.cfg.RegionID, a.topics.CDC, a.topics.Command, a.topics.APIKey, a.cfg.DLQTopic, a.cfg.GroupID, a.cfg.Brokers, a.cfg.MeiliHost, a.cfg.MeiliBatchEnabled, a.cfg.MeiliBatchSize, a.cfg.MeiliBatchFlushMS, a.cfg.MeiliBatchMaxBytes, a.cfg.Debug,
	)

	// 5. 创建对外 HTTP 服务，提供 /search 代理与 /health 健康检查接口。
	server := newHTTPServer(a.cfg, keyRegistry)

	// 6. 使用 errgroup 并发管理 HTTP 服务、注册重试与 Kafka 消费循环，
	// 任一子协程返回错误都会导致整体退出。
	g, ctx := errgroup.WithContext(ctx)

	// 注册失败不影响本地搜索服务启动，但会在后台退避重试，直到中心服务可用。
	g.Go(func() error {
		service.RegisterAgentLoop(ctx, a.cfg)
		return nil
	})

	g.Go(func() error {
		log.Printf("HTTP 服务启动，监听地址 %s", server.Addr)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			return err
		}
		return nil
	})

	g.Go(func() error {
		handlers := BuildHandlers(Topics{CDC: a.topics.CDC, Command: a.topics.Command}, meiliClient, keyRegistry, a.cfg)
		return service.Run(ctx, cdcClient, a.cfg, handlers)
	})

	g.Go(func() error {
		handlers := BuildHandlers(Topics{APIKey: a.topics.APIKey}, meiliClient, keyRegistry, a.cfg)
		return service.Run(ctx, apiKeyClient, a.cfg, handlers)
	})

	// 7. 等待外部 ctx 被取消（例如收到中断信号）。
	<-ctx.Done()

	// 8. 在限定时间内优雅关闭 HTTP 服务，避免强制中断正在处理的请求。
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
		meilisearch.WithCustomClient(&http.Client{Timeout: 15 * time.Second}),
	)
}

func newKafkaClient(cfg config.AppConfig, groupID string, topics []string) (*kgo.Client, error) {
	// newKafkaClient 创建 Kafka 客户端，并以消费者身份订阅所有需要处理的 topic。
	// 使用 franz-go 提供的 kgo.Client，可以在单个 consumer group 内实现高可用消费。

	// 计算需要订阅的去重后的 topic 列表。
	subscribeTopics := uniqueStrings(topics)
	return kgo.NewClient(
		kgo.SeedBrokers(cfg.Brokers...),
		kgo.ConsumerGroup(groupID),
		kgo.ConsumeTopics(subscribeTopics...),
		// 新区域首次创建 group 时从仍在保留期内的最早消息开始回放。
		// 已存在的 group 仍优先使用其已提交 offset。
		kgo.ConsumeStartOffset(kgo.NewOffset().AtStart()),
		kgo.ConsumeResetOffset(kgo.NewOffset().AtStart()),
		kgo.DisableAutoCommit(),
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
	return uniqueStrings(append(append(append([]string{}, topics.CDC...), topics.Command), topics.APIKey))
}

func uniqueStrings(topics []string) []string {
	seen := make(map[string]struct{}, len(topics))
	result := make([]string, 0, len(topics))
	for _, topic := range topics {
		if topic == "" {
			continue
		}
		if _, ok := seen[topic]; ok {
			continue
		}
		seen[topic] = struct{}{}
		result = append(result, topic)
	}
	return result
}

func newHTTPServer(cfg config.AppConfig, keyRegistry *apikey.Registry) *http.Server {
	// newHTTPServer 创建对外的 HTTP Server。
	// 对外只保留版本化搜索代理契约。
	mux := http.NewServeMux()
	mux.Handle("/api/v1/collections/", handler.NewV1SearchHandler(cfg, keyRegistry))
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"healthy"}`))
	})

	return &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           withCORS(cfg.CORSAllowedOrigins)(mux),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
}

func withCORS(allowed []string) func(http.Handler) http.Handler {
	// withCORS 为 HTTP 接口增加跨域支持。
	// 生产环境应配置 CORS_ALLOWED_ORIGINS 白名单：仅反射白名单内的 Origin，
	// 未匹配的跨域请求不返回 ACAO，浏览器将拒绝；预检也返回 403。
	// 白名单为空时退化为允许任意 Origin（*），仅用于本地/开发，且需配合
	// CORS_REQUIRE_ALLOWLIST=true 在生产启动阶段拦截空配置。
	allowAll := len(allowed) == 0
	allowedSet := make(map[string]struct{}, len(allowed))
	for _, o := range allowed {
		if o = strings.TrimSpace(o); o != "" {
			allowedSet[o] = struct{}{}
		}
	}
	return func(h http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			origin := r.Header.Get("Origin")
			if origin != "" {
				if allowAll {
					w.Header().Set("Access-Control-Allow-Origin", "*")
				} else if _, ok := allowedSet[origin]; ok {
					w.Header().Set("Access-Control-Allow-Origin", origin)
					w.Header().Set("Vary", "Origin")
				}
			} else if allowAll {
				w.Header().Set("Access-Control-Allow-Origin", "*")
			}

			w.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
			w.Header().Set("Access-Control-Expose-Headers", "X-Request-ID, Retry-After")

			reqHeaders := r.Header.Get("Access-Control-Request-Headers")
			if reqHeaders != "" {
				w.Header().Set("Access-Control-Allow-Headers", reqHeaders)
			} else {
				w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, X-App-Name, X-Request-ID")
			}

			if r.Method == http.MethodOptions {
				_, originOK := allowedSet[origin]
				if allowAll || (origin != "" && originOK) {
					w.WriteHeader(http.StatusNoContent)
				} else {
					w.WriteHeader(http.StatusForbidden)
				}
				return
			}

			h.ServeHTTP(w, r)
		})
	}
}
