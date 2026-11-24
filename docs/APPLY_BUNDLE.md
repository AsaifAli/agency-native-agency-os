# Applying the Agency OS consolidated bundle v5

This is a full source snapshot based on the founder-governance v4 source, with v5 delivery operations added. It is not a blind patch. It includes the complete source tree, migrations, tests and documentation.

## 1. Preserve your current checkout

From the parent directory of `agency-native-agency-os`:

```bash
cp -a agency-native-agency-os "agency-native-agency-os.backup-$(date +%Y%m%d-%H%M%S)"
cd agency-native-agency-os
git status --short
```

If you have uncommitted work, commit it or preserve it separately. Do not delete `.git`, `.env`, `.venv`, local databases, object storage or Docker volumes.

Extract the v5 archive into a separate directory first. Compare it with your checkout. The bundle deliberately uses v4's explicit Founder Authority and safer frontend dev-auth gate. Do not reintroduce the current-clean snapshot's unconditional `dev:` token fallback or its n8n-first workflow wording.

Copy the v5 source into your checkout only after reviewing the diff. Exclude `.git`, `.env`, `.venv`, `node_modules`, local database files and runtime artifacts.

## 2. Migration preflight — do not skip

The v5 migration chain is:

```text
... -> c91e2d7a4f10
    -> 7a2d9c4e1f60  (telephony records and outbox table)
    -> b4a9e2d1c673  (explicit Founder Authority)
    -> d8c5a1f20973  (playbooks, scope changes, time entries and project costs)
```

After the source has been copied, from the repository root:

```bash
export PYTHONPATH="$PWD"
alembic history --verbose
alembic current
alembic heads
```

Expected single head: `d8c5a1f20973`.

Before applying migrations:
1. Confirm `DATABASE_URL` points to the intended local development database, not production.
2. Confirm PostgreSQL is running and reachable.
3. Take a database backup using your configured PostgreSQL connection and verify the backup file is non-empty.
4. Confirm the current revision is a known ancestor in the chain above.
5. If the current revision is unknown, there are multiple heads, or migration history differs, stop and reconcile it. Do not reset, stamp, drop, downgrade or force the database to match the bundle.

After a verified backup and known migration state:

```bash
alembic upgrade head
alembic current
```

Expected revision: `d8c5a1f20973`.

The full historical migration chain has not been validated on SQLite. Use PostgreSQL for the real migration test. The v5 migration has not yet been run against your local PostgreSQL instance in this release process.

## 3. Founder Authority provisioning

New organizations created through `app.bootstrap` grant Founder Authority to the bootstrap founder.

For an existing organization, after the migration, provision from a trusted local administrative shell:

```bash
python -m app.founder_admin grant \
  --org-id YOUR_ORG_ID \
  --email founder@example.com \
  --confirm founder@example.com
```

Use the actual active founder user email and organization ID. The command requires `DATABASE_URL` to point at the intended database. It does not expose an HTTP grant endpoint.

To revoke:

```bash
python -m app.founder_admin revoke \
  --org-id YOUR_ORG_ID \
  --email founder@example.com \
  --confirm founder@example.com
```

Do not place database credentials in command arguments or shell history.

## 4. Backend verification

```bash
export PYTHONPATH="$PWD"
python -m compileall -q app migrations tests
python -m pytest -q
alembic heads
```

Build-environment evidence for this bundle:
- `102 passed, 1 skipped`.
- The skipped test is PostgreSQL worker concurrency; it requires `AGENCY_OS_TEST_DATABASE_URL`.
- Python compilation passed.
- One Alembic head: `d8c5a1f20973`.

Run the PostgreSQL concurrency test with a dedicated disposable test database before relying on worker concurrency.

## 5. Frontend verification

```bash
cd frontend
npm install
npm run build
```

The frontend build was not run when this bundle was prepared. Production authentication/token lifecycle is not implemented. Development-token behavior must never be enabled in production.

## 6. New delivery operations

Base path: `/v1/orgs/{org_id}/operations`.

- Playbooks: create/list and founder-controlled activation/retirement.
- Scope changes: create, then create an approval with action type `scope.change.accept`, exact change ID and workspace. A founder approves it through the approvals API. Finally call the scope-change approve endpoint with that approval ID. The endpoint consumes the approval and applies the change in one database transaction.
- Time entries: record time against a project and optional task.
- Project costs: record costs in the project's currency.
- Financial summary: estimates versus recorded actual time/cost and provisional margin.
- Exceptions: read-only pending approvals, blocked tasks and failed/retry-wait executions.
- Agent performance: execution reliability counts, not QA acceptance scores.

See `docs/DELIVERY_OPERATIONS_V5.md` for payload contracts and limitations.

## 7. Current implementation boundary

This bundle is a tested development foundation, not a complete autonomous business OS and not production-ready.

Still required:
- Production OIDC/JWKS/MFA and scoped machine identities.
- Complete endpoint/worker policy enforcement and Data Protection Gateway.
- Durable outbox dispatcher, leases, heartbeats, bounded retries, dead letters and reconciliation.
- Supervisor orchestration and specialist delegation.
- Complete client engagement, proposal/SOW, support and handover workflows.
- QA acceptance and rework metrics.
- Live telephony/email provider integration with consent, suppression, signed webhooks and stop conditions.
- Retention/deletion lifecycle, PostgreSQL RLS/isolation proof, monitoring and backup/restore drills.
- PostgreSQL migration and concurrency verification in your environment.

Use synthetic data until the applicable security and recovery gates pass. Do not enable real outbound communications, calls, client transcript ingestion or production side effects merely because a record API exists.
