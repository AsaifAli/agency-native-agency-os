# PostgreSQL 16 tenant RLS and runtime roles

## Implementation status

The PostgreSQL security model uses additive migrations to enable and FORCE RLS across the tenant-owned schema, including organization-scoped records, workspace-owned records, `organizations`, `browser_sessions`, `execution_attempts`, outcome evidence, orchestration links and Private Operations records. The current startup inventory is maintained in `app/db.py` (`REQUIRED_RLS_TABLES`, currently 58 tables) and startup fails closed if an expected table is missing RLS, FORCE RLS or a policy. Dedicated runtime roles are non-superusers and `NOBYPASSRLS`; the migrator is the only role with `BYPASSRLS` and owns migrated objects. Worker scope discovery is an atomic bounded claim. Execution work uses a PID/transaction-bound lease capability; maintenance uses a separate short-lived workspace capability. The legacy global workspace enumerator is not an authorized worker entry point. Browser-session retention runs through a bounded, audited SECURITY DEFINER function, and direct worker privileges on sensitive tables are revoked. PostgreSQL integration tests verify role grants, worker capabilities, human workspace grants, machine identity lookup, append-only audit and outcome evidence.

**Validation status:** the user applied migration `u1b2c3d4e5f6` and completed the worker role grant/bootstrap step against the isolated PostgreSQL Compose test database. The configured `postgres-tests` image then passed **22 tests (22 passed, 0 failed)**, including the worker-role RLS integration tests. This is isolated local test evidence, not a production migration rehearsal or production approval. The assistant-side development environment has no Docker daemon or live PostgreSQL service.

Human access requires both active organization membership and an explicit, auditable `workspace_grants` row. Existing membership access was backfilled when the workspace-grant migration was introduced; future workspace access changes are explicit. Machine identities are database-enforced to their exact workspace. Worker data access uses a separate execution- or maintenance-capability context.

## Roles

| Role | Use | Attributes | Purpose |
|---|---|---|---|
| `agency_os` | Postgres bootstrap only | Official-image superuser | Initial database/role creation; never use in application containers |
| `agency_os_migrator` | Migrations and trusted admin CLI | Non-superuser, `BYPASSRLS`, owns migrated tables | Schema migrations and founder bootstrap/grant CLI |
| `agency_os_app` | API only | Non-owner, `NOBYPASSRLS` | All API queries are subject to tenant RLS |
| `agency_os_worker` | Worker only | Non-owner, non-superuser, `NOBYPASSRLS` | Workspace-scoped queue processing with explicit transaction-local RLS context |

The worker role is non-superuser `NOBYPASSRLS`. It claims one workspace at a time through bounded execution/maintenance capability functions and processes it with transaction-local RLS context. It has no general-purpose global workspace-list function. Worker claim/lease lifecycle functions and bounded browser-session retention are narrowly scoped SECURITY DEFINER entry points; none grants arbitrary tenant-table access. The worker still has operational authority to process every workspace; PostgreSQL custom GUC context is defense-in-depth against missing predicates, not a boundary against arbitrary SQL execution under the worker credential. For isolation against a compromised worker credential, use per-tenant worker credentials or move all tenant data operations behind narrowly scoped database functions. The API must never receive migrator or worker credentials.

### Shared user identity directory

`public.users` is intentionally excluded from tenant RLS because it stores only the agency's shared, pre-provisioned internal identities; it is not a client/contact directory. This is a deliberate global identity boundary, not a tenant-owned business-data exception to copy elsewhere. The API role may read identities for authentication and same-agency operational references, and may update only `oidc_issuer` and `oidc_subject` when linking a verified, pre-provisioned OIDC account. It cannot insert/delete users or update email, display name, active state or the primary key. The worker has no privileges on `users`. Provisioning and profile/activation changes remain trusted migrator/founder-admin operations. Client people belong in workspace-scoped `contacts`, never in `users`.

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
- Machine authentication first binds only the supplied identity ID for one-row lookup; after digest verification it retains that exact identity ID together with the machine organization and exact workspace. Service-session credential SECURITY DEFINER functions require all three context values to match their target parameters and reject cross-identity calls.
- Signed website intake binds only its configured org/workspace after signature and idempotency checks.
- SQLAlchemy reapplies context after each new transaction. `set_config(..., true)` resets at commit/rollback so pooled connections do not retain a previous request's tenant identity.
- Restricted `SECURITY DEFINER` organization/workspace access predicates are owned by `agency_os_migrator`; execute is revoked from PUBLIC and granted only to API and worker roles. Each predicate requires its actor argument to equal the transaction-local authenticated user. Worker calls always return false, and API callers cannot use the helpers as cross-user membership/workspace oracles.
- Worker scope discovery is an atomic, bounded claim, not a global workspace list. Execution work uses a PID/transaction-bound lease capability; maintenance uses a separate short-lived workspace capability. Execution attempts inherit their parent execution's RLS scope.
- Browser-session retention is a bounded, audited SECURITY DEFINER operation; the worker has no direct browser-session table privileges.
- Default privileges no longer automatically grant future public tables or sequences to the worker; new worker dependencies require explicit reviewed grants.

Custom PostgreSQL GUCs are defense-in-depth against missing tenant predicates, not protection against arbitrary SQL execution under the API or worker credential. The worker remains a cross-workspace operational principal because it must process all agency workspaces; a compromised worker credential could set another workspace's GUC. Stronger isolation against a compromised worker requires per-tenant worker credentials or moving tenant data operations behind narrowly scoped database functions. Parameterized queries and SQL-injection prevention remain mandatory.

## Live test

Apply migrations to a disposable PostgreSQL 16 database and create the bootstrap, migrator, app, test-app and worker roles using `docker/postgres/test-init.sql`. The `agency_os_test_app` login inherits `agency_os_app` grants but remains a separate `NOBYPASSRLS` session identity. Then run:

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
