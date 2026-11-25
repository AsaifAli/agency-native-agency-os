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
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='agency_os_migrator') \gexec
ALTER ROLE agency_os_migrator LOGIN PASSWORD :'migrator_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;
-- Existing installations created objects as the bootstrap superuser. Transfer
-- this database's objects so the restricted migrator can apply future DDL/RLS.
REASSIGN OWNED BY agency_os TO agency_os_migrator;
GRANT CONNECT, CREATE ON DATABASE agency_os TO agency_os_migrator;
GRANT USAGE, CREATE ON SCHEMA public TO agency_os_migrator;

SELECT format('CREATE ROLE agency_os_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='agency_os_app') \gexec
ALTER ROLE agency_os_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;

SELECT format('CREATE ROLE agency_os_worker LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS', :'worker_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='agency_os_worker') \gexec
ALTER ROLE agency_os_worker LOGIN PASSWORD :'worker_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT CONNECT ON DATABASE agency_os TO agency_os_app, agency_os_worker;
SQL
