#!/bin/sh
set -eu
: "${POSTGRES_MIGRATOR_PASSWORD:?POSTGRES_MIGRATOR_PASSWORD is required}"
: "${POSTGRES_APP_PASSWORD:?POSTGRES_APP_PASSWORD is required}"
: "${POSTGRES_WORKER_PASSWORD:?POSTGRES_WORKER_PASSWORD is required}"
psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=migrator_password="$POSTGRES_MIGRATOR_PASSWORD" \
  --set=app_password="$POSTGRES_APP_PASSWORD" \
  --set=worker_password="$POSTGRES_WORKER_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE agency_os_migrator LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS', :'migrator_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='agency_os_migrator') \\gexec
ALTER ROLE agency_os_migrator LOGIN PASSWORD :'migrator_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;

-- This bootstrap database is created empty by the official Postgres image.
-- Transfer only its database and default schema ownership. REASSIGN OWNED is
-- intentionally avoided: it also processes shared/system-owned objects and
-- can abort initialization on a fresh cluster.
ALTER DATABASE agency_os OWNER TO agency_os_migrator;
ALTER SCHEMA public OWNER TO agency_os_migrator;
GRANT CONNECT ON DATABASE agency_os TO agency_os, agency_os_app, agency_os_worker, agency_os_migrator;
GRANT USAGE, CREATE ON SCHEMA public TO agency_os_migrator;

SELECT format('CREATE ROLE agency_os_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='agency_os_app') \\gexec
ALTER ROLE agency_os_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;

SELECT format('CREATE ROLE agency_os_worker LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS', :'worker_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='agency_os_worker') \\gexec
ALTER ROLE agency_os_worker LOGIN PASSWORD :'worker_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
SQL
