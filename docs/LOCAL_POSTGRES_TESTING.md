# Isolated local PostgreSQL integration tests

This test stack is deliberately separate from the normal Agency OS Compose stack.
It uses PostgreSQL 16, a dedicated Compose project/volume, a dedicated database
(`agency_os_worker_test`) and synthetic test records. It does not connect to
Supabase or any hosted database.

## Requirements

- Docker Engine with the Compose v2 plugin
- Enough local disk space to build the Python test image and pull PostgreSQL 16

## Run

From the repository root:

```sh
docker compose -p agency-os-pg-test -f docker-compose.postgres-test.yml up \
  --build --abort-on-container-exit --exit-code-from postgres-tests
```

The command applies the current Alembic migrations to the isolated test database,
grants the dedicated NOBYPASSRLS test role the table privileges required by the
RLS test, and runs the PostgreSQL tenant-integrity, RLS and worker concurrency
tests. The test container exits non-zero on a failure.

## Cleanup

After saving the test output:

```sh
docker compose -p agency-os-pg-test -f docker-compose.postgres-test.yml down -v --remove-orphans
```

This removes only the named `agency-os-pg-test` Compose project's containers and
its `agency_os_pg_test` volume. Do not substitute the normal Compose project
name and do not run `docker compose down -v` against the regular Agency OS
stack.

## Safety notes

- The credentials in this file are fixed, disposable local-only test credentials.
  They must never be used outside this isolated test stack.
- Do not point these variables at Supabase, staging, production or any shared DB.
- The worker concurrency tests use the isolated database's bootstrap test
  connection to create synthetic fixtures. They do not prove the production
  worker role is safe; the separate worker-privilege blocker remains open.
- The RLS test connects as a separate non-owner, NOBYPASSRLS role and verifies
  cross-organization visibility, write rejection, machine workspace scope and
  pooled-connection context cleanup.
- The tests clean up only rows created by their own unique test IDs. If a test
  process is forcibly terminated, the entire disposable volume can be removed
  using the cleanup command above.
