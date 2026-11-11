#!/usr/bin/env bash
# search_outbox 行定期清理：删除超过保留期的已投递事件行（分批，避免长事务）。
#
# 必须以 postgres 超级用户执行：search_outbox 启用了 FORCE ROW LEVEL SECURITY，
# 业务角色在无租户上下文时看不到任何行，应用侧全局清理会被 RLS 拦截。
# 删除产生的 after=null CDC 事件会被 sync 端（2026-11-04 版本起）按 no-op 确认，
# 不会污染 DLQ。TRUNCATE 事件 Debezium 默认跳过，但 TRUNCATE 会清掉未投递的行，
# 因此这里用分批 DELETE 只删超过保留期的旧数据。
set -u

BASE_DIR="/data/pg2meili-cdc"
LOG_FILE="$BASE_DIR/logs/outbox_cleanup.log"
RETENTION_DAYS="${1:-14}"
BATCH=5000
mkdir -p "$(dirname "$LOG_FILE")"
log() { echo "[$(date '+%F %T')] $*" >> "$LOG_FILE"; }

total=0
while :; do
  deleted=$(docker exec pg2meili-postgres-1 psql -U postgres -tA -c \
    "WITH d AS (
       DELETE FROM public.search_outbox
       WHERE ctid IN (
         SELECT ctid FROM public.search_outbox
         WHERE created_at < now() - make_interval(days => $RETENTION_DAYS)
         LIMIT $BATCH
       )
       RETURNING 1
     ) SELECT count(*) FROM d;" 2>/dev/null)
  if [ -z "$deleted" ]; then
    log "ERROR 删除查询失败（docker/pg 不可用？），已删除 $total 行"
    exit 1
  fi
  total=$((total + deleted))
  [ "$deleted" -lt "$BATCH" ] && break
done
log "完成：删除 $total 行（保留 $RETENTION_DAYS 天）"
