#!/usr/bin/env bash
set -euo pipefail

# 向 Kafka Connect 注册 Debezium PostgreSQL CDC connector（幂等）。
# 由 docker-compose.yml 的 connect-init 服务在 connect/postgres 就绪后运行。

CONNECT_URL="${CONNECT_URL:-http://connect:8083}"
PG_HOST="${POSTGRES_HOST:-postgres}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_DB="${POSTGRES_DB:-postgres}"

# CDC 监控的表（逗号分隔，需带 schema 前缀）。仅捕获公共 search_outbox。
TABLE_INCLUDE_LIST="${CDC_TABLE_INCLUDE_LIST:-public.search_outbox}"
SERVER_NAME="${CDC_SERVER_NAME:-pg}"
SLOT_NAME="${CDC_SLOT_NAME:-unidata_search_outbox_slot}"
PUBLICATION_NAME="${CDC_PUBLICATION_NAME:-unidata_search_outbox_pub}"
CONNECTOR_NAME="${CDC_CONNECTOR_NAME:-pg-search-outbox-connector}"
# Debezium 使用独立复制账号，不使用业务写入账号
PG_USER="${CDC_PG_USER:-unidata_cdc}"
PG_PASSWORD="${CDC_PG_PASSWORD:-change-me}"

# 等待 Connect REST API 真正可用（容器启动 ≠ API 就绪），超时则退出非零
RETRY=0
until curl -fsS "${CONNECT_URL}/" >/dev/null 2>&1; do
  RETRY=$((RETRY + 1))
  if [ "${RETRY}" -ge "${CONNECT_RETRIES:-60}" ]; then
    echo "错误: Kafka Connect ${CONNECT_URL} 在 ${CONNECT_RETRIES:-60} 次重试后仍未就绪" >&2
    exit 1
  fi
  echo "等待 Kafka Connect 就绪: ${CONNECT_URL} (${RETRY}/${CONNECT_RETRIES:-60})"
  sleep 3
done

JSON=$(cat <<EOF
{
  "name": "${CONNECTOR_NAME}",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "${PG_HOST}",
    "database.port": "${PG_PORT}",
    "database.user": "${PG_USER}",
    "database.password": "${PG_PASSWORD}",
    "database.dbname": "${PG_DB}",
    "database.server.name": "${SERVER_NAME}",
    "schema.include.list": "public",
    "table.include.list": "${TABLE_INCLUDE_LIST}",
    "plugin.name": "pgoutput",
    "snapshot.mode": "always",
    "publication.autocreate.mode": "filtered",
    "publication.name": "${PUBLICATION_NAME}",
    "slot.name": "${SLOT_NAME}",
    "topic.prefix": "${SERVER_NAME}",
    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "true",
    "value.converter.schemas.enable": "true"
  }
}
EOF
)

# 幂等：已存在则先删除再重建（便于表清单等配置变更后重跑）
if curl -fsS "${CONNECT_URL}/connectors/${CONNECTOR_NAME}" >/dev/null 2>&1; then
  echo "connector ${CONNECTOR_NAME} 已存在，删除后重建"
  curl -fsS -X DELETE "${CONNECT_URL}/connectors/${CONNECTOR_NAME}" >/dev/null
  sleep 2
fi

curl -fsS -o /dev/null -X POST "${CONNECT_URL}/connectors" \
  -H "Content-Type: application/json" \
  -d "${JSON}"
echo "Debezium connector 已注册: ${CONNECTOR_NAME} (tables: ${TABLE_INCLUDE_LIST})"
