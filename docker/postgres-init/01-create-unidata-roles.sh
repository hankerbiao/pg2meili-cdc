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

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER}" --dbname "${POSTGRES_DB}" \
  --set=app_role="${app_role}" \
  --set=app_password="${app_password}" \
  --set=cdc_role="${cdc_role}" \
  --set=cdc_password="${cdc_password}" <<'SQL'
SELECT format(
  CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role')
    THEN 'ALTER ROLE %I LOGIN PASSWORD %L'
    ELSE 'CREATE ROLE %I LOGIN PASSWORD %L'
  END,
  :'app_role', :'app_password'
) \gexec

SELECT format(
  CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'cdc_role')
    THEN 'ALTER ROLE %I LOGIN REPLICATION BYPASSRLS PASSWORD %L'
    ELSE 'CREATE ROLE %I LOGIN REPLICATION BYPASSRLS PASSWORD %L'
  END,
  :'cdc_role', :'cdc_password'
) \gexec

SELECT format('GRANT CONNECT, CREATE ON DATABASE %I TO %I', current_database(), :'app_role') \gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA public TO %I', :'app_role') \gexec
SELECT format('GRANT CONNECT, CREATE ON DATABASE %I TO %I', current_database(), :'cdc_role') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'cdc_role') \gexec
SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', :'cdc_role') \gexec
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON TABLES TO %I',
  :'app_role', :'cdc_role'
) \gexec

SELECT CASE
  WHEN EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'unidata_search_outbox_pub')
    THEN 'ALTER PUBLICATION unidata_search_outbox_pub SET TABLE public.search_outbox'
  WHEN to_regclass('public.search_outbox') IS NOT NULL
    THEN 'CREATE PUBLICATION unidata_search_outbox_pub FOR TABLE public.search_outbox'
END
WHERE to_regclass('public.search_outbox') IS NOT NULL
\gexec
SQL
