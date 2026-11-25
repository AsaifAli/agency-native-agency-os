# PostgreSQL 16 tenant RLS and runtime roles

## Implementation status

Migration `t0a1b2c3d4e5` enables and FORCEs RLS for organization-scoped model tables, `organizations` and `browser_sessions`. Follow-up migration `u1b2c3d4e5f6` adds RLS to `execution_attempts`, scopes org-level outbox events and adds two private SECURITY DEFINER worker operations. The worker role is changed to non-superuser `NOBYPASSRLS`; it enumerates org/workspace identifiers through a narrowly granted function, then runs normal queue, execution, session and outbox queries with a transaction-local exact workspace context. Browser-session retention runs through a bounded, audited SECURITY DEFINER function. Direct worker privileges on users, browser sessions, memberships, founder authorities and machine identities are revoked. API and worker startup verify their PostgreSQL role attributes.

**Not live-verified yet:** this Upstash development environment has no PostgreSQL server or Docker daemon. The migration can be rendered to PostgreSQL SQL and has static model-coverage tests, but it has not been applied to a live PostgreSQL 16 instance here. The live isolation suite is included and remains skipped until a disposable PostgreSQL test database is supplied.

Human organization membership currently grants access to all workspaces in that organization. There is no per-user workspace membership/assignment model yet; human workspace restrictions still rely on route-level `org_id`/`workspace_id` checks. Machine identities are database-enforced to their exact workspace.

## Roles

| Role | Use | Attributes | Purpose |
|---|---|---|---|
| `agency_os` | Postgres bootstrap only | Official-image superuser | Initial database/role creation; never use in application containers |
| `agency_os_migrator` | Migrations and trusted admin CLI | Non-superuser, `BYPASSRLS`, owns migrated tables | Schema migrations and founder bootstrap/grant CLI |
| `agency_os_app` | API only | Non-owner, `NOBYPASSRLS` | All API queries are subject to tenant RLS |
| `agency_os_worker` | Worker only | Non-owner, non-superuser, `NOBYPASSRLS` | Workspace-scoped queue processing with explicit transaction-local RLS context |

The worker role is non-superuser `NOBYPASSRLS`. Its code enumerates workspace identifiers through the private scope function and processes one workspace at a time with transaction-local RLS context. The scope function and browser-session retention function are the only cross-workspace SECURITY DEFINER entry points granted to the worker. The worker still has operational authority to process every workspace; PostgreSQL custom GUC context is defense-in-depth against missing predicates, not a boundary against arbitrary SQL execution under the worker credential. For isolation against a compromised worker credential, use per-tenant worker credentials or move all tenant data operations behind narrowly scoped database functions. The API must never receive migrator or worker credentials.

## Local Compose setup

1. Copy `.env.example` to `.env` for Postgres bootstrap/role passwords.
2. Copy `.env.runtime.example` to `.env.runtime` for API/worker settings.
3. Replace placeholders with unique URL-safe random values (for example, `openssl rand -hex 32`). Keep both files untracked.
4. Start with `docker compose up --build`.

The Postgres entrypoint creates roles on a fresh volume. The idempotent role bootstrap also transfers existing database objects owned by the old `agency_os` bootstrap role to `agency_os_migrator`, so the restricted migration role can apply later DDL/RLS without resetting a populated volume. `migrate` connects as `agency_os_migrator`; API connects only as `agency_os_app`; worker connects only as `agency_os_worker`. `MIGRATION_DATABASE_URL` is passed only to the migration container. Do not place it in `.env.runtime`.

For an existing Postgres volume, the init script is not run automatically. After updating `.env` role passwords, run the idempotent bootstrap script and migration:

```bash
docker compose exec postgres /docker-entrypoint-initdb.d/01-roles.sh
docker compose run --rm migrate
```

Do not reset/delete the volume. Back up first.

## Trusted administrative CLI

`app/bootstrap.py` and `app/founder_admin.py` use `AdminSessionLocal`. In production, explicitly supply `MIGRATION_DATABASE_URL` in the trusted command environment pointing to `agency_os_migrator`. Do not put this URL in API/worker env files, prompts, shell history or source control.

## Context behavior

- Human authentication binds `agency_os.user_id` transaction-locally after resolving the active user.
- Machine authentication first binds only the supplied identity ID for one-row lookup; after digest verification it binds the machine organization and exact workspace.
- Signed website intake binds only its configured org/workspace after signature and idempotency checks.
- SQLAlchemy reapplies context after each new transaction. `set_config(..., true)` resets at commit/rollback so pooled connections do not retain a previous request's tenant identity.
- A restricted `SECURITY DEFINER` membership predicate is owned by `agency_os_migrator`; execute is revoked from PUBLIC and granted only to the API and worker roles.
- Worker scope enumeration returns only org/workspace identifiers. All worker data queries use a workspace-scoped session factory. Execution attempts inherit their parent execution's RLS scope.
- Browser-session retention is a bounded, audited SECURITY DEFINER operation; the worker has no direct browser-session table privileges.

Custom PostgreSQL GUCs are defense-in-depth against missing tenant predicates, not protection against arbitrary SQL execution under the API or worker credential. The worker remains a cross-workspace operational principal because it must process all agency workspaces; a compromised worker credential could set another workspace's GUC. Stronger isolation against a compromised worker requires per-tenant worker credentials or moving tenant data operations behind narrowly scoped database functions. Parameterized queries and SQL-injection prevention remain mandatory.

## Live test

Apply migrations to a disposable PostgreSQL 16 database and create the four roles. Then run:

```bash
AGENCY_OS_TEST_RLS_ADMIN_DATABASE_URL='postgresql+psycopg://agency_os_migrator:...@localhost:5432/agency_os_test' \
AGENCY_OS_TEST_RLS_DATABASE_URL='postgresql+psycopg://agency_os_app:...@localhost:5432/agency_os_test' \
python -m pytest tests/test_tenant_rls_postgres.py -q
```

This creates and deletes synthetic test rows. It verifies human cross-org read isolation, machine workspace scope, cross-tenant write rejection and pooled-connection context cleanup.

## Production gate

- Apply all migrations on PostgreSQL 16 as `agency_os_migrator`.
- Verify API role is non-superuser, NOBYPASSRLS, and owns no RLS tables.
- Verify worker role is non-superuser, NOBYPASSRLS, and owns no RLS tables. Verify scope enumeration, direct-table revocations, execution-attempt RLS, browser-session retention and cross-workspace isolation. Review the residual GUC-spoofing risk: the worker remains a cross-workspace operational principal, not a tenant-isolated process.
- Run the live RLS test plus existing PostgreSQL tenant/worker concurrency tests.
- Complete human workspace-level authorization design and route-by-route object authorization review.
- Test OIDC, signed website intake, machine identity revocation, worker lease recovery, retention and backup restore.
- Add every future `org_id` model to the RLS migration coverage guard before release.
