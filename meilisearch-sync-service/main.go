package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"distributed-search/meilisearch-sync-service/internal/config"
	"distributed-search/meilisearch-sync-service/internal/handler"
	"distributed-search/meilisearch-sync-service/internal/logger"
	"distributed-search/meilisearch-sync-service/internal/service"

	"github.com/joho/godotenv"
	"github.com/meilisearch/meilisearch-go"
	"github.com/twmb/franz-go/pkg/kgo"
)

func main() {
	_ = godotenv.Load()

	cfg := config.LoadConfig()

	logger.InitLogger(cfg.Debug)

	meiliClient := newMeiliClient(cfg)
	client, err := newKafkaClient(cfg)
	if err != nil {
		log.Fatalf("创建 Kafka 客户端失败: %v", err)
	}
	defer client.Close()

	log.Printf("服务启动，监听 topics=%v group=%s brokers=%v meiliHost=%s debug=%v", cfg.Topics, cfg.GroupID, cfg.Brokers, cfg.MeiliHost, cfg.Debug)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	httpServer := newHTTPServer(cfg)

	go startHTTPServer(httpServer, cancel)
	setupGracefulShutdown(ctx, httpServer, cancel)

	if err := service.Run(ctx, client, meiliClient, cfg); err != nil && ctx.Err() == nil {
		log.Printf("运行循环出现错误: %v", err)
	}
}

func newMeiliClient(cfg config.AppConfig) meilisearch.ServiceManager {
	return meilisearch.New(
		cfg.MeiliHost,
		meilisearch.WithAPIKey(cfg.MeiliAPIKey),
	)
}

func newKafkaClient(cfg config.AppConfig) (*kgo.Client, error) {
	return kgo.NewClient(
		kgo.SeedBrokers(cfg.Brokers...),
		kgo.ConsumerGroup(cfg.GroupID),
		kgo.ConsumeTopics(cfg.Topics...),
	)
}

func newHTTPServer(cfg config.AppConfig) *http.Server {
	mux := http.NewServeMux()
	mux.Handle("/search", handler.NewSearchHandler(cfg))

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

func startHTTPServer(server *http.Server, cancel context.CancelFunc) {
	log.Printf("HTTP 服务启动，监听地址 %s", server.Addr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Printf("HTTP 服务启动失败: %v", err)
		cancel()
	}
}

func setupGracefulShutdown(ctx context.Context, server *http.Server, cancel context.CancelFunc) {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		sig := <-sigCh
		log.Printf("收到信号 %s，正在优雅退出", sig.String())
		cancel()
	}()

	go func() {
		<-ctx.Done()
		shutdownCtx, cancelShutdown := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancelShutdown()
		if err := server.Shutdown(shutdownCtx); err != nil {
			log.Printf("HTTP 服务关闭失败: %v", err)
		} else {
			log.Printf("HTTP 服务已关闭")
		}
	}()
}
