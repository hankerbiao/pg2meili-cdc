#!/usr/bin/env bash
set -euo pipefail

# Runs only when the PostgreSQL data directory is first initialized.
# The app role owns business tables and tenant schemas (non-superuser, RLS applies).
# The CDC role is the Debezium logical replication account. BYPASSRLS lets its
# initial snapshot SELECT read every tenant's search_outbox rows (WAL-based
# pgoutput streaming is not subject to RLS anyway); UniData additionally creates
# an outbox_cdc_full_read SELECT policy for this role as an idempotent fallback
# for deployments where this init script already ran.
app_role="${UNIDATA_PG_USER:-unidata_app}"
app_password="${UNIDATA_PG_PASSWORD:-change-me}"
cdc_role="${CDC_PG_USER:-unidata_cdc}"
cdc_password="${CDC_PG_PASSWORD:-change-me}"

case "${app_role}" in
  ''|*[!A-Za-z0-9_]*) echo "invalid UNIDATA_PG_USER" >&2; exit 1 ;;
esac
case "${cdc_role}" in
  ''|*[!A-Za-z0-9_]*) echo "invalid CDC_PG_USER" >&2; exit 1 ;;
esac

role_exists() {
  psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = '${1}'" | grep -q 1
}

if role_exists "${app_role}"; then
  psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
    --set=unidata_app_password="${app_password}" \
    -c "ALTER ROLE \"${app_role}\" LOGIN PASSWORD :'unidata_app_password'"
else
  psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
    --set=unidata_app_password="${app_password}" \
    -c "CREATE ROLE \"${app_role}\" LOGIN PASSWORD :'unidata_app_password'"
fi

if role_exists "${cdc_role}"; then
  psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
    --set=unidata_cdc_password="${cdc_password}" \
    -c "ALTER ROLE \"${cdc_role}\" LOGIN REPLICATION BYPASSRLS PASSWORD :'unidata_cdc_password'"
else
  psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
    --set=unidata_cdc_password="${cdc_password}" \
    -c "CREATE ROLE \"${cdc_role}\" LOGIN REPLICATION BYPASSRLS PASSWORD :'unidata_cdc_password'"
fi

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" <<SQL
GRANT CONNECT, CREATE ON DATABASE "${POSTGRES_DB}" TO "${app_role}";
GRANT USAGE, CREATE ON SCHEMA public TO "${app_role}";
GRANT CONNECT, CREATE ON DATABASE "${POSTGRES_DB}" TO "${cdc_role}";
GRANT USAGE ON SCHEMA public TO "${cdc_role}";
ALTER DEFAULT PRIVILEGES FOR ROLE "${app_role}" IN SCHEMA public
  GRANT SELECT ON TABLES TO "${cdc_role}";
SQL
