#!/usr/bin/env bash
# MeliData CDC 链路健康巡检：由 cron 每 5 分钟执行一次。
# 输出追加到 logs/health_check.log，WARN/FAIL 行可直接 grep 告警。
# 覆盖：容器状态、服务健康接口、复制槽延迟、消费积压、DLQ 深度、
#       pg_wal 大小、outbox 表大小、磁盘、负载、僵尸进程。
set -o pipefail

BASE_DIR="/data/pg2meili-cdc"
LOG_FILE="$BASE_DIR/logs/health_check.log"
mkdir -p "$(dirname "$LOG_FILE")"

ts() { date '+%F %T'; }
log() { echo "[$(ts)] $*" >> "$LOG_FILE"; }

# 日志轮转：超过 5MB 只保留最后 2000 行
if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)" -gt 5242880 ]; then
  tail -n 2000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi

PG="docker exec pg2meili-postgres-1 psql -U postgres -tA -c"
KF="docker exec pg2meili-kafka-1 /kafka/bin"
issues=0

# 1. 容器状态
for c in pg2meili-postgres-1 pg2meili-meilisearch-1 pg2meili-kafka-1 pg2meili-redis-1 pg2meili-connect-1 pg2meili-meilisearch-sync-1 pg2meili-unidata-1 pg2meili-zookeeper-1; do
  state=$(docker ps --filter "name=^/$c$" --format '{{.Status}}')
  case "$state" in
    Up*unhealthy*|*"health: starting"*)
      log "WARN 容器 $c 状态异常: $state"; issues=$((issues + 1)) ;;
    Up*)
      log "OK 容器 $c: $state" ;;
    *)
      log "FAIL 容器 $c 未运行"; issues=$((issues + 1)) ;;
  esac
done

# 2. 服务健康接口
check_http() { # name url 期望片段
  resp=$(curl -s -m 5 "$2" 2>/dev/null)
  if echo "$resp" | grep -q "$3"; then
    log "OK $1"
  else
    log "FAIL $1 健康检查失败: ${resp:-无响应}"; issues=$((issues + 1))
  fi
}
check_http "meilisearch:7700" "http://localhost:7700/health" '"available"'
check_http "sync:8091" "http://localhost:8091/health" '"healthy"'
check_http "unidata:8080" "http://localhost:8080/health" '"healthy"'

# 3. Debezium connector task（PG 重启等故障后 task 会 FAILED 且 Connect 不自动重试）
conn_state=$(curl -s -m 5 http://localhost:8083/connectors/pg-search-outbox-connector/status 2>/dev/null)
task_state=$(echo "$conn_state" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print(d["tasks"][0]["state"])
except Exception:
    print("UNKNOWN")' 2>/dev/null)
if [ "$task_state" != "RUNNING" ]; then
  log "WARN connector task 状态 $task_state，尝试自动重启"
  curl -s -X POST 'http://localhost:8083/connectors/pg-search-outbox-connector/restart?includeTasks=true&onlyFailed=true' -o /dev/null
  sleep 8
  task_state2=$(curl -s -m 5 http://localhost:8083/connectors/pg-search-outbox-connector/status 2>/dev/null | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print(d["tasks"][0]["state"])
except Exception:
    print("UNKNOWN")' 2>/dev/null)
  if [ "$task_state2" = "RUNNING" ]; then
    log "OK connector task 已自动重启恢复"
  else
    log "FAIL connector task 重启后仍为 $task_state2，需人工介入"; issues=$((issues + 1))
  fi
else
  log "OK connector task RUNNING"
fi

# 4. 复制槽（CDC 咽喉：槽不活跃=WAL 开始无限堆积）
slot_active=$($PG "select active from pg_replication_slots where slot_name='unidata_search_outbox_slot';" 2>/dev/null)
slot_lag=$($PG "select coalesce(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)::bigint, 0) from pg_replication_slots where slot_name='unidata_search_outbox_slot';" 2>/dev/null)
if [ "$slot_active" != "t" ]; then
  log "FAIL 复制槽 unidata_search_outbox_slot 非活跃（connector 断开，WAL 将堆积）"; issues=$((issues + 1))
elif [ -n "$slot_lag" ] && [ "$slot_lag" -gt 524288000 ]; then
  log "WARN 复制槽延迟 $((slot_lag / 1048576))MB (>500MB)"; issues=$((issues + 1))
else
  log "OK 复制槽活跃，延迟 $(( ${slot_lag:-0} / 1024 ))KB"
fi

# 4. pg_wal 总大小（历史上曾因孤儿槽堆到 27GB）
wal_kb=$(docker exec pg2meili-postgres-1 du -sk /var/lib/postgresql/data/pg_wal 2>/dev/null | cut -f1)
if [ -n "$wal_kb" ] && [ "$wal_kb" -gt 5242880 ]; then
  log "WARN pg_wal $((wal_kb / 1048576))GB (>5GB)，检查是否有复制槽滞留"; issues=$((issues + 1))
else
  log "OK pg_wal $(( ${wal_kb:-0} / 1024 ))MB"
fi

# 5. outbox 消费积压与消费者存活（--group 模式下列序：$1=组名 $2=topic $6=lag $7=consumer-id）
cg=$(docker exec pg2meili-kafka-1 /kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group meilisearch-sync-service-local 2>/dev/null | awk '$2=="pg.public.search_outbox"{print $6"/"$7}')
if [ -z "$cg" ]; then
  log "FAIL 消费组 meilisearch-sync-service-local 无 outbox 消费记录"; issues=$((issues + 1))
else
  lag_out="${cg%%/*}"
  consumer_alive="${cg##*/}"
  if [ "$consumer_alive" = "-" ]; then
    log "WARN outbox 消费组无在线消费者（sync 可能已退出）"; issues=$((issues + 1))
  fi
  if [ "$lag_out" -gt 10000 ] 2>/dev/null; then
    log "WARN outbox 消费积压 $lag_out (>10000)"; issues=$((issues + 1))
  else
    log "OK outbox 消费积压 ${lag_out:-0}"
  fi
fi

# 6. DLQ 深度（latest - earliest，物理删除后 offset 不归零不能用 latest 判断）
dlq_latest=$(docker exec pg2meili-kafka-1 /kafka/bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic meili.dlq 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}')
dlq_earliest=$(docker exec pg2meili-kafka-1 /kafka/bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic meili.dlq --time -2 2>/dev/null | awk -F: '{s+=$NF} END{print s+0}')
dlq_depth=$((dlq_latest - dlq_earliest))
if [ "$dlq_depth" -gt 100 ]; then
  log "WARN meili.dlq 积压 $dlq_depth 条，需要人工排查回放"; issues=$((issues + 1))
else
  log "OK DLQ 深度 $dlq_depth"
fi

# 7. outbox 表大小
outbox_bytes=$($PG "select pg_total_relation_size('public.search_outbox')::bigint;" 2>/dev/null)
if [ -n "$outbox_bytes" ] && [ "$outbox_bytes" -gt 10737418240 ]; then
  log "WARN search_outbox 表 $((outbox_bytes / 1073741824))GB (>10GB)，检查清理任务"; issues=$((issues + 1))
else
  log "OK search_outbox 表 $(( ${outbox_bytes:-0} / 1048576 ))MB"
fi

# 8. 磁盘 / 负载 / 僵尸进程
for mp in / /data; do
  pct=$(df -P "$mp" | awk 'NR==2{gsub("%","");print $5}')
  if [ "$pct" -gt 85 ]; then
    log "WARN 磁盘 $mp 使用 ${pct}% (>85%)"; issues=$((issues + 1))
  else
    log "OK 磁盘 $mp 使用 ${pct}%"
  fi
done
load1=$(awk '{print $1}' /proc/loadavg)
cores=$(nproc)
if awk "BEGIN{exit !($load1 > $cores * 1.5)}"; then
  log "WARN 负载 $load1 超过 $cores 核的 1.5 倍"; issues=$((issues + 1))
else
  log "OK 负载 $load1 (${cores}核)"
fi
zombies=$(ps -eo stat | grep -c '^Z' || true)
if [ "$zombies" -gt 100 ]; then
  log "WARN 僵尸进程 $zombies 个 (>100)，可重启 kafka 容器清理"; issues=$((issues + 1))
else
  log "OK 僵尸进程 ${zombies:-0} 个"
fi

log "SUMMARY issues=$issues"
exit $(( issues > 0 ? 1 : 0 ))
