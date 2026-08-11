#!/usr/bin/env bash
set -euo pipefail

# PostgreSQL init scripts run only for a new data directory. Reuse the same
# idempotent role setup for existing volumes before migrations and CDC start.
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}}"
exec /docker-entrypoint-initdb.d/01-create-unidata-roles.sh
