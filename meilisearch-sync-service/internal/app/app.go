package app

import (
	"context"
	"log"
	"net/http"
	"time"

	"meilisearch-sync-service/internal/config"
	"meilisearch-sync-service/internal/handler"
	"meilisearch-sync-service/internal/logger"
	"meilisearch-sync-service/internal/service"

	"github.com/meilisearch/meilisearch-go"
	"github.com/twmb/franz-go/pkg/kgo"
	"golang.org/x/sync/errgroup"
)

type App struct {
	cfg    config.AppConfig
	topics Topics
}

func New(cfg config.AppConfig) *App {
	// New 负责注入配置并构建 Topics。
	return &App{
		cfg:    cfg,
		topics: BuildTopics(cfg),
	}
}

func (a *App) Run(ctx context.Context) error {
	// Run 负责启动核心组件并管理生命周期。
	logger.InitLogger(a.cfg.Debug)

	meiliClient := newMeiliClient(a.cfg)
	client, err := newKafkaClient(a.cfg, a.topics)
	if err != nil {
		return err
	}
	defer client.Close()

	log.Printf(
		"服务启动，监听 cdcTopics=%v commandTopic=%s dlqTopic=%s group=%s brokers=%v meiliHost=%s debug=%v",
		a.topics.CDC, a.topics.Command, a.topics.DLQ, a.cfg.GroupID, a.cfg.Brokers, a.cfg.MeiliHost, a.cfg.Debug,
	)

	// 启动时向 UniData 注册本机代理信息（若配置了 UNIDATA_URL）
	service.RegisterAgent(a.cfg)

	server := newHTTPServer(a.cfg)

	g, ctx := errgroup.WithContext(ctx)

	g.Go(func() error {
		log.Printf("HTTP 服务启动，监听地址 %s", server.Addr)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			return err
		}
		return nil
	})

	g.Go(func() error {
		handlers := BuildHandlers(a.topics, meiliClient)
		return service.Run(ctx, client, meiliClient, a.cfg, handlers)
	})

	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("HTTP 服务关闭失败: %v", err)
	}

	return g.Wait()
}

func newMeiliClient(cfg config.AppConfig) meilisearch.ServiceManager {
	// Meilisearch 客户端用于写入与设置更新。
	return meilisearch.New(
		cfg.MeiliHost,
		meilisearch.WithAPIKey(cfg.MeiliAPIKey),
	)
}

func newKafkaClient(cfg config.AppConfig, topics Topics) (*kgo.Client, error) {
	// Kafka consumer 订阅所有需要处理的 topic。
	subscribeTopics := uniqueTopics(topics)
	return kgo.NewClient(
		kgo.SeedBrokers(cfg.Brokers...),
		kgo.ConsumerGroup(cfg.GroupID),
		kgo.ConsumeTopics(subscribeTopics...),
		// 增加 SessionTimeout 以应对网络抖动或处理延迟
		kgo.SessionTimeout(60*time.Second),
		kgo.HeartbeatInterval(5*time.Second),
	)
}

func uniqueTopics(topics Topics) []string {
	// 去重合并 CDC / Command / DLQ topics。
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
	if topics.DLQ != "" {
		if _, ok := seen[topics.DLQ]; !ok {
			seen[topics.DLQ] = struct{}{}
			result = append(result, topics.DLQ)
		}
	}
	return result
}

func newHTTPServer(cfg config.AppConfig) *http.Server {
	// HTTP server 仅对外提供 Search Proxy 接口。
	mux := http.NewServeMux()
	mux.Handle("/search", handler.NewSearchHandler(cfg))
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
