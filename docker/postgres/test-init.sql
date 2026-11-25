-- Disposable local-only PostgreSQL test role. Never reuse these credentials.
CREATE ROLE agency_os_test_app LOGIN PASSWORD 'local-only-test-app-password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
