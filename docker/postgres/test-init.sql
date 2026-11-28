-- Disposable local-only PostgreSQL test roles. Never reuse these credentials.
-- Mirror the production role names and privilege boundaries so the real RLS
-- migration can grant schema/function/table access without relying on superuser.
CREATE ROLE agency_os_migrator LOGIN PASSWORD 'local-only-test-migrator-password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS;
GRANT CONNECT, CREATE ON DATABASE agency_os_worker_test TO agency_os_migrator;
ALTER DATABASE agency_os_worker_test OWNER TO agency_os_migrator;
ALTER SCHEMA public OWNER TO agency_os_migrator;
GRANT USAGE, CREATE ON SCHEMA public TO agency_os_migrator;

CREATE ROLE agency_os_app LOGIN PASSWORD 'local-only-test-app-password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;

-- Worker test role mirrors production: non-superuser and NOBYPASSRLS.
CREATE ROLE agency_os_worker LOGIN PASSWORD 'local-only-test-worker-password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;

-- Dedicated NOBYPASSRLS login used by tenant-isolation integration tests.
-- It inherits the API role's object/function grants but keeps its own login
-- identity, allowing tests to verify the exact runtime role without using
-- the application credential itself.
CREATE ROLE agency_os_test_app LOGIN PASSWORD 'local-only-test-app-password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT agency_os_app TO agency_os_test_app WITH INHERIT TRUE;
ALTER ROLE agency_os_test_app INHERIT;
