#!/usr/bin/env bash
set -euo pipefail

# 1. 切换到脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"

cd "$APP_DIR"

# 2. 可选：整理依赖（需要网络）
# go mod tidy

# 3. 设置为 Linux 静态编译（适合部署到服务器）
export CGO_ENABLED=0
export GOOS=linux
export GOARCH=amd64

# 4. 编译
echo "Building meilisearch-sync-service ..."
go build -a -ldflags "-s -w" -o meilisearch-sync-service_go main.go

echo "Build done. Binary: $APP_DIR/meilisearch-sync-service_go"
