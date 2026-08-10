#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE=(docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml)
CONNECTOR_NAME="${CDC_CONNECTOR_NAME:-pg-search-outbox-connector}"
HOST_HEADER="${DEPLOY_HOST:-}"

curl_local() {
  env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY curl -fsS --max-time 10 "$@"
}

echo "== Compose services =="
"${COMPOSE[@]}" ps

for service in postgres kafka meilisearch redis unidata; do
  if ! "${COMPOSE[@]}" ps --format json "$service" | grep -q '"Health":"healthy"'; then
    echo "$service is not healthy" >&2
    exit 1
  fi
done

echo "== UniData readiness =="
curl_local http://127.0.0.1:"${UNIDATA_PORT:-8080}"/ready

echo "== Debezium connector =="
connector_status="$(curl_local http://127.0.0.1:"${CONNECT_PORT:-8083}"/connectors/"$CONNECTOR_NAME"/status)"
printf '%s\n' "$connector_status"
[[ "$(printf '%s' "$connector_status" | grep -o '"state":"RUNNING"' | wc -l | tr -d ' ')" -ge 2 ]]

if [[ -n "$HOST_HEADER" ]]; then
  echo "== nginx readiness =="
  curl_local -H "Host: $HOST_HEADER" http://127.0.0.1/ready
fi

echo "Deployment verification passed."
