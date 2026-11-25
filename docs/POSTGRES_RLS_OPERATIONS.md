# PostgreSQL 16 tenant RLS and runtime roles

## Implementation status

Migration `t0a1b2c3d4e5` enables and FORCEs RLS for every current model table with `org_id`, plus `organizations`, and adds a separate user/token-digest policy for `browser_sessions` (51 policies total). Human queries are scoped by organization membership. Machine identities are scoped to their exact organization and workspace, including workspace discovery. Transaction-local PostgreSQL settings are bound after human/machine authentication and reset by transaction boundaries. API and worker startup verify their PostgreSQL role attributes.

**Not live-verified yet:** this Upstash development environment has no PostgreSQL server or Docker daemon. The migration can be rendered to PostgreSQL SQL and has static model-coverage tests, but it has not been applied to a live PostgreSQL 16 instance here. The live isolation suite is included and remains skipped until a disposable PostgreSQL test database is supplied.

Human organization membership currently grants access to all workspaces in that organization. There is no per-user workspace membership/assignment model yet; human workspace restrictions still rely on route-level `org_id`/`workspace_id` checks. Machine identities are database-enforced to their exact workspace.

## Roles

| Role | Use | Attributes | Purpose |
|---|---|---|---|
| `agency_os` | Postgres bootstrap only | Official-image superuser | Initial database/role creation; never use in application containers |
| `agency_os_migrator` | Migrations and trusted admin CLI | Non-superuser, `BYPASSRLS`, owns migrated tables | Schema migrations and founder bootstrap/grant CLI |
| `agency_os_app` | API only | Non-owner, `NOBYPASSRLS` | All API queries are subject to tenant RLS |
| `agency_os_worker` | Worker only | Non-owner, non-superuser, `BYPASSRLS` | Queue processing across organizations |

The worker role can read/write across tenants by design so it can claim and process queued work. Keep it isolated to the worker process, with no public SQL interface. The API must not receive migrator or worker credentials.

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
- A restricted `SECURITY DEFINER` membership predicate is owned by `agency_os_migrator`; execute is revoked from PUBLIC and granted only to the API role.

Custom PostgreSQL GUCs are defense-in-depth against missing tenant predicates, not protection against arbitrary SQL execution under the API credential. Parameterized queries and SQL-injection prevention remain mandatory.

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
- Verify worker role is non-superuser, BYPASSRLS, and owns no RLS tables. This is a privileged residual risk, not a tenant-isolation claim; replace it with narrow security-definer queue operations and per-execution tenant context before production.
- Run the live RLS test plus existing PostgreSQL tenant/worker concurrency tests.
- Complete human workspace-level authorization design and route-by-route object authorization review.
- Test OIDC, signed website intake, machine identity revocation, worker lease recovery, retention and backup restore.
- Add every future `org_id` model to the RLS migration coverage guard before release.
