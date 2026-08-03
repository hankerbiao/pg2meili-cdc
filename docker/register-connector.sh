#!/usr/bin/env bash
set -euo pipefail

# 向 Kafka Connect 注册 Debezium PostgreSQL CDC connector（幂等）。
# 由 docker-compose.yml 的 connect-init 服务在 connect/postgres 就绪后运行。

CONNECT_URL="${CONNECT_URL:-http://connect:8083}"
PG_HOST="${POSTGRES_HOST:-postgres}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-postgres}"
PG_PASSWORD="${POSTGRES_PASSWORD:-change-me}"
PG_DB="${POSTGRES_DB:-postgres}"

# CDC 监控的表（逗号分隔，需带 schema 前缀）。默认仅核心搜索表 uni_documents。
TABLE_INCLUDE_LIST="${CDC_TABLE_INCLUDE_LIST:-public.uni_documents}"
SERVER_NAME="${CDC_SERVER_NAME:-pg}"
SLOT_NAME="${CDC_SLOT_NAME:-unidata_slot}"
PUBLICATION_NAME="${CDC_PUBLICATION_NAME:-unidata_pub}"
CONNECTOR_NAME="${CDC_CONNECTOR_NAME:-pg-cdc-connector}"

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
    "connector.class": "io.debezium.connector.postgresql.PostgresqlConnector",
    "database.hostname": "${PG_HOST}",
    "database.port": "${PG_PORT}",
    "database.user": "${PG_USER}",
    "database.password": "${PG_PASSWORD}",
    "database.dbname": "${PG_DB}",
    "database.server.name": "${SERVER_NAME}",
    "schema.include.list": "public",
    "table.include.list": "${TABLE_INCLUDE_LIST}",
    "plugin.name": "pgoutput",
    "publication.autocreate.mode": "filtered",
    "publication.name": "${PUBLICATION_NAME}",
    "slot.name": "${SLOT_NAME}",
    "topic.prefix": "${SERVER_NAME}",
    "key.converter": "org.apache.kafka.connect.json.JsonConverter",
    "value.converter": "org.apache.kafka.connect.json.JsonConverter",
    "key.converter.schemas.enable": "false",
    "value.converter.schemas.enable": "false"
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

curl -fsS -X POST "${CONNECT_URL}/connectors" \
  -H "Content-Type: application/json" \
  -d "${JSON}"
echo "Debezium connector 已注册: ${CONNECTOR_NAME} (tables: ${TABLE_INCLUDE_LIST})"
