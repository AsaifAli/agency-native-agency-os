-- Disposable local-only PostgreSQL test roles. Never reuse these credentials.
-- Mirror the production split: migrations own schema objects; application
-- tests connect through a distinct NOBYPASSRLS role.
CREATE ROLE agency_os_migrator LOGIN PASSWORD 'local-only-test-migrator-password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;
GRANT CONNECT, CREATE ON DATABASE agency_os_worker_test TO agency_os_migrator;
GRANT USAGE, CREATE ON SCHEMA public TO agency_os_migrator;

CREATE ROLE agency_os_test_app LOGIN PASSWORD 'local-only-test-app-password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
