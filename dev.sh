#!/usr/bin/env bash
# =============================================================================
# pg2meili 开发/构建统一入口
#
# 一键完成: 重新构建 UniData 镜像 / 构建 Go 同步服务 /
#          实时把代码同步到容器（热更新）
#
# 部署拓扑:
#   - unidata 容器(8080): UniData API 服务
#   - meilisearch-sync-service(Go): 宿主进程, 不在 docker-compose 内
#
# 用法:
#   ./dev.sh build [unidata|go|all] [--no-cache]  重新构建并更新
#   ./dev.sh dev backend    后端热更新: 监听 UniData/app 同步到容器并自动重启
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

# 统一用 .env.docker 作为 compose 变量插值源，避免根目录 .env 与 .env.docker 不一致
# （P0-4：env_file 注入的应用配置才能真正生效）。
COMPOSE="docker compose --env-file .env.docker"
GO_DIR="$SCRIPT_DIR/meilisearch-sync-service"
GO_CTL="$GO_DIR/start_meilisearch_sync_service.sh"
GO_BIN_LOCAL="meilisearch-sync-service_go.local"  # 本地编译版（*.local 已被 .gitignore 忽略）
GO_PID_FILE="$GO_DIR/.meili_local.pid"
GO_LOG_FILE="$GO_DIR/app.local.log"
# --- 输出工具 ---------------------------------------------------------------
info() { printf '\033[1;36m[dev]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[ok]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

require_docker() {
  command -v docker >/dev/null 2>&1 || die "未找到 docker，请先安装/启动 Docker Desktop"
}

# --- 构建: unidata 镜像 ------------------------------------------------------
build_unidata() {
  require_docker
  info "构建 unidata 镜像（UniData API 服务）..."
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


# --- 实时更新: 后端同步到容器（compose watch）--------------------------------
dev_backend() {
  require_docker
  $COMPOSE ps --status running unidata >/dev/null 2>&1 || warn "unidata 未运行，建议先 ./dev.sh up 或 ./dev.sh build"
  info "监听 UniData/app、scripts、migrations，改动自动同步容器并重启 (Ctrl+C 退出)"
  $COMPOSE watch unidata
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

# --- 测试: 运行 UniData pytest 套件 -----------------------------------------
# 用法:
#   ./dev.sh test                运行全部测试（DB 用例需 TEST_PG_CONN_STRING 或 --with-db）
#   ./dev.sh test --cov          带覆盖率报告（默认已开启 --cov=app）
#   ./dev.sh test --with-db      临时拉起 Postgres 容器跑全量（含集成/端到端）
#   ./dev.sh test <pytest args>  透传任意 pytest 参数，如 ./dev.sh test tests/test_kafka_manager.py
cmd_test() {
  local with_db=0
  local extra=()
  for arg in "$@"; do
    case "$arg" in
      --with-db) with_db=1 ;;
      --cov) ;;  # 覆盖率已在 pyproject addopts 默认开启
      *) extra+=("$arg") ;;
    esac
  done

  local venv_py="$SCRIPT_DIR/UniData/.venv/bin/python"
  [ -x "$venv_py" ] || die "未找到 UniData/.venv，请先创建虚拟环境并安装依赖（pytest pytest-asyncio pytest-cov httpx）"

  if [ "$with_db" -eq 1 ]; then
    require_docker
    info "启动临时 Postgres 测试库 (unidata_test_ci)..."
    cleanup_test_pg() {
      docker rm -f unidata_test_pg >/dev/null 2>&1 || true
    }
    trap cleanup_test_pg EXIT INT TERM
    cleanup_test_pg
    docker run -d --rm --name unidata_test_pg -e POSTGRES_USER=postgres \
      -e POSTGRES_PASSWORD=test -e POSTGRES_DB=unidata_test -p 5433:5432 postgres:16 >/dev/null
    # 等待就绪
    for _ in $(seq 1 30); do
      docker exec unidata_test_pg pg_isready -U postgres >/dev/null 2>&1 && break
      sleep 1
    done
    export TEST_PG_CONN_STRING="postgresql://postgres:test@127.0.0.1:5433/unidata_test"
    info "TEST_PG_CONN_STRING 已指向临时库，运行全量测试..."
    set +e
    if [ "${#extra[@]}" -gt 0 ]; then
      (cd "$SCRIPT_DIR/UniData" && "$venv_py" -m pytest "${extra[@]}")
    else
      (cd "$SCRIPT_DIR/UniData" && "$venv_py" -m pytest)
    fi
    local rc=$?
    set -e
    trap - EXIT INT TERM
    cleanup_test_pg
    unset -f cleanup_test_pg
    return $rc
  fi

  info "运行 UniData 测试（无 DB 用例将自动 skip；如需全量请加 --with-db）"
  if [ "${#extra[@]}" -gt 0 ]; then
    (cd "$SCRIPT_DIR/UniData" && "$venv_py" -m pytest "${extra[@]}")
  else
    (cd "$SCRIPT_DIR/UniData" && "$venv_py" -m pytest)
  fi
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
      unidata      重建 unidata API 镜像并重启容器  (默认)
      go           编译 Go 同步服务部署版(Linux amd64)
      all          上述全部
      --no-cache   强制无缓存构建(遇到 COPY 层假缓存导致代码不生效时使用)

  测试:
  ./dev.sh test                         运行 UniData pytest（无 DB 用例自动 skip）
  ./dev.sh test --with-db               临时拉起 Postgres 跑全量(集成/端到端)
  ./dev.sh test tests/test_kafka_manager.py  透传任意 pytest 参数

  实时更新到容器:
  ./dev.sh dev backend    监听后端代码同步容器并自动重启 (compose watch)
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
    NO_CACHE=0
    TARGET=""
    for arg in "$@"; do
      case "$arg" in
        --no-cache) NO_CACHE=1 ;;
        *) TARGET="$arg" ;;
      esac
    done
    TARGET="${TARGET:-unidata}"
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
      go)       dev_go ;;
      *) die "用法: ./dev.sh dev {backend|go}" ;;
    esac
    ;;
  # 注：主入口上方已 `shift` 消费掉命令名，此处直接透传剩余参数，
  # 不能再次 shift（历史上多一次 shift 导致 ./dev.sh go start 等子命令参数丢失）。
  watch)  cmd_watch "$@" ;;
  up)     cmd_up "$@" ;;
  logs)   cmd_logs "$@" ;;
  status) cmd_status ;;
  go)     cmd_go "$@" ;;
  test)   cmd_test "$@" ;;
  ""|-h|--help|help) usage ;;
  *) die "未知命令: $CMD（查看 ./dev.sh help）" ;;
esac
