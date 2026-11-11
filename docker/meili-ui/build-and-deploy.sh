#!/usr/bin/env bash
# 构建官方 Meilisearch mini-dashboard 并部署到远端（目标机无需外网 / 无需 node）
#
# 用法：
#   ./docker/meili-ui/build-and-deploy.sh                 # 用默认目标和地址
#   MEILI_UI_HOST=root@10.17.158.114 \
#   MEILI_SERVER_ADDRESS=http://10.17.158.114:7700 \
#   ./docker/meili-ui/build-and-deploy.sh
#
# 说明：
# - mini-dashboard 需要 Yarn 4（走 corepack），Node >= 18
# - prebuild 的 validate-env 强制要求 VITE_HUBSPOT_* 两个变量，这里填占位值绕过
# - VITE_MEILI_SERVER_ADDRESS 是构建期注入的，改了地址必须重新构建
set -euo pipefail

MEILI_UI_HOST="${MEILI_UI_HOST:-root@10.17.158.114}"
MEILI_SERVER_ADDRESS="${MEILI_SERVER_ADDRESS:-http://10.17.158.114:7700}"
MEILI_UI_REMOTE_DIR="${MEILI_UI_REMOTE_DIR:-/opt/meili-ui}"
MEILI_UI_PORT="${MEILI_UI_PORT:-7701}"
MINI_DASHBOARD_REPO="${MINI_DASHBOARD_REPO:-https://github.com/meilisearch/mini-dashboard.git}"
WORK_DIR="${WORK_DIR:-/tmp/mini-dashboard}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> 1/4 准备源码 $WORK_DIR"
if [ -d "$WORK_DIR/.git" ]; then
  git -C "$WORK_DIR" fetch --depth 1 origin main
  git -C "$WORK_DIR" reset --hard FETCH_HEAD
else
  rm -rf "$WORK_DIR"
  git clone --depth 1 "$MINI_DASHBOARD_REPO" "$WORK_DIR"
fi

echo "==> 2/4 安装依赖并构建（目标 API: $MEILI_SERVER_ADDRESS）"
cd "$WORK_DIR"
COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn install
VITE_HUBSPOT_PORTAL_ID=0 \
VITE_HUBSPOT_FORM_GUID=placeholder \
VITE_MEILI_SERVER_ADDRESS="$MEILI_SERVER_ADDRESS" \
COREPACK_ENABLE_DOWNLOAD_PROMPT=0 corepack yarn vite build

echo "==> 3/4 上传到 $MEILI_UI_HOST:$MEILI_UI_REMOTE_DIR"
tar czf /tmp/meili-ui-dist.tgz -C "$WORK_DIR/build" .
ssh "$MEILI_UI_HOST" "mkdir -p $MEILI_UI_REMOTE_DIR/dist"
scp -q /tmp/meili-ui-dist.tgz "$MEILI_UI_HOST:$MEILI_UI_REMOTE_DIR/"
scp -q "$SCRIPT_DIR/nginx.conf" "$MEILI_UI_HOST:$MEILI_UI_REMOTE_DIR/nginx.conf"
scp -q "$SCRIPT_DIR/docker-compose.yml" "$MEILI_UI_HOST:$MEILI_UI_REMOTE_DIR/docker-compose.yml"
ssh "$MEILI_UI_HOST" "set -e
  cd $MEILI_UI_REMOTE_DIR
  rm -rf dist && mkdir -p dist
  tar xzf meili-ui-dist.tgz -C dist
  rm -f meili-ui-dist.tgz
  find dist -name '._*' -delete
  chmod -R a+rX dist"

echo "==> 4/4 启动 / 重启容器"
ssh "$MEILI_UI_HOST" "set -e
  cd $MEILI_UI_REMOTE_DIR
  docker rm -f meili-ui >/dev/null 2>&1 || true
  MEILI_UI_PORT=$MEILI_UI_PORT docker compose up -d
  sleep 2
  docker ps --filter name=meili-ui --format '{{.Names}} {{.Status}} {{.Ports}}'"

echo
echo "完成: http://${MEILI_UI_HOST#*@}:$MEILI_UI_PORT"
echo "首次打开会要求填 API key（Meilisearch 为 production 模式），填 master key 或 admin key 后存 localStorage。"
