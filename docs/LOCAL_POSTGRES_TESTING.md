# Isolated local PostgreSQL integration tests

This test stack is deliberately separate from the normal Agency OS Compose stack.
It uses PostgreSQL 16, a dedicated Compose project/volume, a dedicated database
(`agency_os_worker_test`) and synthetic test records. It does not connect to
Supabase or any hosted database.

## Requirements

- Docker Engine with the Compose v2 plugin
- Enough local disk space to build the Python test image and pull PostgreSQL 16

## Run

From the repository root, execute these stages in order. Do not combine them
with `--abort-on-container-exit`: the migration and privilege-grant containers
are expected to exit successfully before the test container starts, and that
flag would stop PostgreSQL prematurely.

```sh
# 1. Start only the isolated PostgreSQL server and wait for its health check.
docker compose -p agency-os-pg-test -f docker-compose.postgres-test.yml up -d --build postgres-test

# 2. Apply all Alembic migrations as the dedicated migrator role.
docker compose -p agency-os-pg-test -f docker-compose.postgres-test.yml run --rm --no-deps migrate-test

# 3. Grant the dedicated NOBYPASSRLS test role the table privileges needed by RLS tests.
docker compose -p agency-os-pg-test -f docker-compose.postgres-test.yml run --rm --no-deps grant-test-app

# 4. Run live PostgreSQL tenant-integrity, RLS and worker/outbox concurrency tests.
docker compose -p agency-os-pg-test -f docker-compose.postgres-test.yml run --rm --no-deps postgres-tests
```

The last command exits non-zero on a test failure. Preserve its complete output
when reporting results. The worker concurrency tests currently use the isolated
database bootstrap test connection for synthetic fixtures; they do not prove
the production worker role is safe.

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
- The RLS test connects as a separate non-owner, NOBYPASSRLS role and verifies
  cross-organization visibility, write rejection, machine workspace scope and
  pooled-connection context cleanup.
- The tests clean up only rows created by their own unique test IDs. If a test
  process is forcibly terminated, the entire disposable volume can be removed
  using the cleanup command above.
- The migrations configure `agency_os_worker` as non-superuser `NOBYPASSRLS`.
  Worker data access is capability-scoped, and migration `d5e7f9a1c3b5` narrows
  its effective public-table/column privileges. Verify the exact role attributes,
  grants, ownership and function ACLs in this isolated PostgreSQL run before
  considering a deployment. This test does not certify any hosted environment.
