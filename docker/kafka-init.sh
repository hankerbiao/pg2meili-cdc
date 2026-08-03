#!/usr/bin/env bash
set -euo pipefail

BROKER="${KAFKA_BOOTSTRAP_SERVER:-kafka:9093}"
KAFKA_BIN="${KAFKA_BIN:-/kafka/bin}"

until "${KAFKA_BIN}/kafka-topics.sh" --bootstrap-server "${BROKER}" --list >/dev/null 2>&1; do
  echo "等待 Kafka 就绪: ${BROKER}"
  sleep 2
done

create_topic() {
  local topic="$1"
  shift
  "${KAFKA_BIN}/kafka-topics.sh" \
    --bootstrap-server "${BROKER}" \
    --create \
    --if-not-exists \
    --topic "${topic}" \
    --partitions "${KAFKA_TOPIC_PARTITIONS:-3}" \
    --replication-factor "${KAFKA_TOPIC_REPLICATION_FACTOR:-1}" \
    "$@"
}

create_topic "${KAFKA_API_KEY_TOPIC:-api_keys.events}" --config cleanup.policy=compact
"${KAFKA_BIN}/kafka-configs.sh" \
  --bootstrap-server "${BROKER}" \
  --alter \
  --entity-type topics \
  --entity-name "${KAFKA_API_KEY_TOPIC:-api_keys.events}" \
  --add-config cleanup.policy=compact

create_topic "${KAFKA_COMMAND_TOPIC:-meili.commands}"
create_topic "${KAFKA_DLQ_TOPIC:-meili.dlq}"

echo "Kafka topics 已初始化"
