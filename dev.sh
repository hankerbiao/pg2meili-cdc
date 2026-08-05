#!/usr/bin/env bash
# =============================================================================
# pg2meili 开发/构建统一入口
#
# 一键完成: 重新构建 docker 镜像（前端+后端一体）/ 构建 Go 同步服务 /
#          实时把代码同步到容器（热更新）/ 本地前端 HMR 开发
#
# 部署拓扑:
#   - unidata 容器(8080): 镜像内 = open-platform-web 前端 dist + UniData 后端
#   - meilisearch-sync-service(Go): 宿主进程, 不在 docker-compose 内
#   - 旧前端 frontend/(search-tester): 构建 dist 后由 Go 服务托管
#
# 用法:
#   ./dev.sh build [unidata|go|all] [--no-cache]  重新构建并更新
#   ./dev.sh dev backend    后端热更新: 监听 UniData/app 同步到容器并自动重启
#   ./dev.sh dev frontend   前端热更新: 本地 vite(3100) HMR, API 代理到容器 8080
#   ./dev.sh dev go         本机编译 Go 服务, 监听 *.go 变更自动重编译重启
#   ./dev.sh watch [svc]    docker compose watch 实时同步到容器
#   ./dev.sh up [svc...]    启动环境(默认全部)
#   ./dev.sh logs [svc]     查看容器日志(默认 unidata)
#   ./dev.sh status         容器与 Go 服务状态
#   ./dev.sh go {build|start|stop|restart|status|log}   Go 服务进程管理
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE="docker compose"
GO_DIR="$SCRIPT_DIR/meilisearch-sync-service"
GO_CTL="$GO_DIR/start_meilisearch_sync_service.sh"
GO_BIN_LOCAL="meilisearch-sync-service_go.local"  # 本地编译版（*.local 已被 .gitignore 忽略）
GO_PID_FILE="$GO_DIR/.meili_local.pid"
GO_LOG_FILE="$GO_DIR/app.local.log"
WEB_DIR="$SCRIPT_DIR/open-platform-web"

# --- 输出工具 ---------------------------------------------------------------
info() { printf '\033[1;36m[dev]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

require_docker() {
  command -v docker >/dev/null 2>&1 || die "未找到 docker，请先安装/启动 Docker Desktop"
}

# --- 构建: unidata 镜像（open-platform-web 前端 + UniData 后端一体）-----------
build_unidata() {
  require_docker
  info "构建 unidata 镜像（open-platform-web 前端 + UniData 后端）..."
  # 注意: macOS 自带 bash 3.2 在 set -u 下空数组 "${extra[@]}" 展开会报 unbound variable，故不用数组拼参数
  if [[ "${NO_CACHE:-0}" == "1" ]]; then
    $COMPOSE build --no-cache unidata
  else
    $COMPOSE build unidata
  fi
  info "启动 unidata（自动执行数据库迁移并等待依赖健康）..."
  $COMPOSE up -d unidata
  ok "unidata 已更新并启动"
  $COMPOSE ps unidata --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'
}

# --- 构建: Go 同步服务（Linux amd64 部署版）----------------------------------
build_go() {
  (cd "$GO_DIR" && ./build.sh)
  ok "部署版二进制: $GO_DIR/meilisearch-sync-service_go"
  warn "本地实时开发请用: ./dev.sh dev go（本机架构编译 + 热重启）"
}

# --- 构建: 旧前端 search-tester（由 Go 服务托管静态文件）---------------------
build_legacy_frontend() {
  info "构建旧前端 frontend/（search-tester）..."
  (cd "$SCRIPT_DIR/frontend" && npm run build)
  ok "dist 已生成: frontend/dist"
  warn "若 Go 服务托管该目录，需重启使其生效: ./dev.sh go restart"
}

# --- 实时更新: 后端同步到容器（compose watch）--------------------------------
dev_backend() {
  require_docker
  $COMPOSE ps --status running unidata >/dev/null 2>&1 || warn "unidata 未运行，建议先 ./dev.sh up 或 ./dev.sh build"
  info "监听 UniData/app、scripts、migrations，改动自动同步容器并重启 (Ctrl+C 退出)"
  $COMPOSE watch unidata
}

# 探测 unidata 容器映射到宿主机的实际端口（兼容 UNIDATA_PORT 非 8080 的环境）
unidata_host_port() {
  local out
  out="$($COMPOSE port unidata 8080 2>/dev/null)" || return 1
  echo "$out" | sed -E 's/^[^:]+:([0-9]+)$/\1/'
}

# --- 实时更新: 前端 HMR（本地 vite dev + 代理到容器）-------------------------
dev_frontend() {
  require_docker
  local host_port
  if host_port="$(unidata_host_port)"; then
    if ! curl -fsS -m 2 "http://127.0.0.1:${host_port}/ready" >/dev/null 2>&1; then
      warn "127.0.0.1:${host_port} 未就绪，请先 ./dev.sh up 或 ./dev.sh build"
    else
      ok "unidata 容器可达: 127.0.0.1:${host_port}"
      if [[ "${host_port}" != "8080" ]]; then
        warn "当前容器映射 ${host_port}，但 vite.config.ts 代理目标写死 8080"
        warn "如 API 请求 404/ECONNREFUSED，请改 open-platform-web/vite.config.ts 的 proxy 为 http://127.0.0.1:${host_port}"
      fi
    fi
  else
    warn "未检测到 unidata 容器端口映射，请先 ./dev.sh up 或 ./dev.sh build"
  fi
  [ -d "$WEB_DIR/node_modules" ] || { info "安装前端依赖..." && (cd "$WEB_DIR" && npm ci); }
  info "启动 open-platform-web vite dev server: http://localhost:3100 （/api、/openapi.json 代理到容器）"
  (cd "$WEB_DIR" && npm run dev)
}

# --- 实时更新: Go 服务（本机编译 + 监听 *.go/.env 自动重启）------------------
build_go_local() {
  local goos goarch
  goos="$(uname -s | tr '[:upper:]' '[:lower:]')"
  case "$(uname -m)" in
    arm64|aarch64) goarch=arm64 ;;
    x86_64|amd64)  goarch=amd64 ;;
    *) die "不支持的 CPU 架构: $(uname -m)" ;;
  esac
  info "编译本机版 ($goos/$goarch): $GO_BIN_LOCAL"
  (cd "$GO_DIR" && CGO_ENABLED=0 GOOS="$goos" GOARCH="$goarch" go build -ldflags "-s -w" -o "$GO_BIN_LOCAL" main.go)
}

start_local_go() {
  if [ -f "$GO_PID_FILE" ] && kill -0 "$(cat "$GO_PID_FILE")" 2>/dev/null; then
    info "本地 Go 服务已在运行 (PID $(cat "$GO_PID_FILE"))"
    return
  fi
  [ -x "$GO_DIR/$GO_BIN_LOCAL" ] || build_go_local
  (
    cd "$GO_DIR"
    nohup "./$GO_BIN_LOCAL" >> "$GO_LOG_FILE" 2>&1 &
    echo $! > "$GO_PID_FILE"
    disown
  )
  sleep 1
  ok "本地 Go 服务已启动 (PID $(cat "$GO_PID_FILE"))，日志: $GO_LOG_FILE"
}

stop_local_go() {
  if [ -f "$GO_PID_FILE" ]; then
    local pid
    pid="$(cat "$GO_PID_FILE")"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 10); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.3
    done
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$GO_PID_FILE"
    info "本地 Go 服务已停止"
  fi
}

dev_go() {
  command -v go >/dev/null 2>&1 || die "未找到 go 工具链"
  build_go_local
  start_local_go
  local stamp="$GO_DIR/.last_build_stamp"
  touch "$stamp"
  info "监听 $GO_DIR 下 *.go / .env 变更，自动重编译并重启 (Ctrl+C 退出)..."
  trap 'stop_local_go; exit 0' INT TERM
  while :; do
    if find "$GO_DIR" \( -name '*.go' -o -name '.env' \) -print \
        | grep -v '/\.git/' \
        | while read -r f; do [ "$f" -nt "$stamp" ] && echo "$f"; done \
        | grep -q .; then
      sleep 0.4
      info "检测到代码变更，重新编译并重启..."
      stop_local_go
      build_go_local
      start_local_go
      touch "$stamp"
    fi
    sleep 1
  done
}

# --- 其他命令 ---------------------------------------------------------------
cmd_watch() {
  require_docker
  info "docker compose watch（Ctrl+C 退出）— 按 compose 内 develop.watch 规则同步/重建"
  $COMPOSE watch "$@"
}

cmd_up() {
  require_docker
  if [ $# -eq 0 ]; then
    $COMPOSE up -d
  else
    $COMPOSE up -d "$@"
  fi
  $COMPOSE ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'
}

cmd_logs() {
  require_docker
  $COMPOSE logs -f --tail=100 "${1:-unidata}"
}

cmd_status() {
  require_docker
  echo "== docker 容器 =="
  $COMPOSE ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}' || true
  echo
  echo "== Go 同步服务（生产管理脚本视角）=="
  (cd "$GO_DIR" && "$GO_CTL" status) || true
  if [ -f "$GO_PID_FILE" ] && kill -0 "$(cat "$GO_PID_FILE")" 2>/dev/null; then
    info "本地 Go dev 服务: 运行中 (PID $(cat "$GO_PID_FILE"))"
  fi
}

cmd_go() {
  local sub="${1:-}"
  case "$sub" in
    build)
      build_go
      ;;
    start|stop|restart|status|log)
      (cd "$GO_DIR" && "$GO_CTL" "$sub")
      ;;
    *)
      echo "用法: ./dev.sh go {build|start|stop|restart|status|log}"
      return 1
      ;;
  esac
}

usage() {
  cat <<'EOF'
pg2meili 开发/构建统一入口

用法:
  ./dev.sh build [unidata|go|all] [--no-cache]   重新构建并更新
      unidata      重建 unidata 镜像(前端+后端一体)并重启容器  (默认)
      go           编译 Go 同步服务部署版(Linux amd64)
      all          上述全部
      --no-cache   强制无缓存构建(遇到 COPY 层假缓存导致代码不生效时使用)

  实时更新到容器:
  ./dev.sh dev backend    监听后端代码同步容器并自动重启 (compose watch)
  ./dev.sh dev frontend   本地 vite HMR(3100), API 代理到容器 8080
  ./dev.sh dev go         本机编译 Go 服务, 监听 *.go 变更自动重启
  ./dev.sh watch [svc]    docker compose watch 全部同步规则

  其他:
  ./dev.sh up [svc...]    启动环境(默认全部)
  ./dev.sh logs [svc]     查看容器日志(默认 unidata)
  ./dev.sh status         容器与 Go 服务状态
  ./dev.sh go {build|start|stop|restart|status|log}   Go 进程管理
EOF
}

# --- 主入口 ------------------------------------------------------------------
CMD="${1:-}"
shift || true

case "$CMD" in
  build)
    TARGET="${1:-unidata}"
    [[ "${2:-}" == "--no-cache" ]] && NO_CACHE=1
    case "$TARGET" in
      unidata) build_unidata ;;
      go)      build_go ;;
      all)     build_unidata; build_go ;;
      *) die "未知构建目标: $TARGET（可选 unidata|go|all）" ;;
    esac
    ;;
  dev)
    case "${1:-}" in
      backend)  dev_backend ;;
      frontend) dev_frontend ;;
      go)       dev_go ;;
      *) die "用法: ./dev.sh dev {backend|frontend|go}" ;;
    esac
    ;;
  watch)  shift 1; cmd_watch "$@" ;;
  up)     shift 1; cmd_up "$@" ;;
  logs)   shift 1; cmd_logs "$@" ;;
  status) cmd_status ;;
  go)     shift 1; cmd_go "$@" ;;
  ""|-h|--help|help) usage ;;
  *) die "未知命令: $CMD（查看 ./dev.sh help）" ;;
esac
