package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	"meilisearch-sync-service/internal/app"
	"meilisearch-sync-service/internal/config"

	"github.com/joho/godotenv"
)

func main() {
	// 入口仅负责加载配置与启动应用，避免业务逻辑下沉到 main。
	if err := godotenv.Load(); err != nil {
		log.Printf("提示: 未加载 .env 文件 (%v)，将完全依赖环境变量", err)
	}

	cfg := config.LoadConfig()
	application := app.New(cfg)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	setupGracefulShutdown(cancel)

	if err := application.Run(ctx); err != nil && ctx.Err() == nil {
		log.Fatalf("服务运行失败: %v", err)
	}
}

func setupGracefulShutdown(cancel context.CancelFunc) {
	// 监听退出信号并触发统一的取消，交由 App 层完成收敛关闭。
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		sig := <-sigCh
		log.Printf("收到信号 %s，正在优雅退出", sig.String())
		cancel()
	}()
}
