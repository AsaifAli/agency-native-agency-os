# Phase 1 — Execution Reliability: Outbox Delivery Foundation

## Scope

This increment adds durable dispatch mechanics to the existing PostgreSQL transactional outbox. It does not replace the existing execution worker lifecycle, retry scheduler, execution leases, heartbeats, or expired-execution recovery.

## Existing execution foundation retained

- Execution claims use row-level locking with `FOR UPDATE SKIP LOCKED`.
- Attempts are persisted and associated with a worker ID.
- Worker leases and heartbeat renewals are persisted.
- Runtime calls occur outside database transactions.
- Retry scheduling uses bounded exponential backoff.
- Expired execution leases are recovered by worker maintenance.
- Execution idempotency is enforced by a database uniqueness constraint.

## Added in this increment

- Outbox delivery ownership (`claimed_by`) and expiring leases.
- Bounded delivery attempts (`max_attempts`) and sanitized `last_error`.
- Publication timestamp (`published_at`).
- Concurrent-safe batch claiming with `FOR UPDATE SKIP LOCKED`.
- Handler invocation outside database transactions.
- At-least-once delivery with retry backoff and dead-letter transition.
- Recovery/reconciliation of expired processing leases.
- Worker maintenance integration for registered event handlers.
- Synthetic SQLite tests and an opt-in PostgreSQL concurrency test.

## Delivery contract

A handler receives an immutable `OutboxMessage` containing the event ID, schema version, payload, and idempotency key. Handlers MUST use the idempotency key to deduplicate side effects. A process can crash after a side effect but before the outbox acknowledgement commits; redelivery is therefore expected and exactly-once delivery is not claimed.

Only explicitly registered event types are claimed. Unknown event types remain pending; they are never silently marked published. The initial registry is intentionally empty. No external side-effect handlers are enabled by this change. Register a handler only after its authorization, data classification, idempotency, timeout, and failure behavior have been reviewed.

## Migration

Revision `e3f1a9c7b2d4` adds nullable delivery lease/claim fields, a publication timestamp, a bounded error field, a max-attempts column with a safe default, a check constraint, and a recovery index. It is additive; it does not delete or rewrite existing outbox rows.

Before applying it to a real database, take and verify a PostgreSQL backup. Then run:

```bash
docker compose run --rm migrate alembic upgrade head
docker compose run --rm migrate alembic current
```

Expected head: `e3f1a9c7b2d4`.


## Verification performed

Latest local validation:

- `python -m pytest -q`: 129 passed, 1 non-blocking deprecation warning.
- `python -m pytest -q -rs tests/test_worker_postgres.py`: 3 passed, 0 skipped.
- PostgreSQL execution-worker concurrency test passed.
- PostgreSQL outbox-worker concurrency test passed.
- PostgreSQL expired-lease recovery and dead-letter test passed.
- `git diff --check`: passed.
- `docker compose run --rm migrate alembic check`: no new upgrade operations detected.
- Development database Alembic revision: `e3f1a9c7b2d4` (head).

The PostgreSQL tests use the dedicated `agency_os_worker_test` database.
The migration was applied to the development database after a backup was
created and its archive was verified.

These results establish local development and test-database validation.
They do not establish production readiness or compliance.

## Delivery limitations

- The outbox handler registry is intentionally empty.
- No external event side effects are enabled.
- The recovery integration test simulates an expired lease in PostgreSQL.
  It does not kill and restart a running worker process.
- Outbox handlers do not currently renew leases while running.
- Consumers must implement idempotency using the supplied idempotency key.
- Operational metrics and alerting for pending age, retry counts, and
  dead-letter counts are not yet implemented.

## Migration rollback policy

Revision `e3f1a9c7b2d4` intentionally blocks automatic downgrade because
some delivery columns may have existed before Alembic recorded this revision.

Before any future migration rollback:

1. Stop affected workers.
2. Take and verify a database backup.
3. Inspect the actual schema and migration history.
4. Prepare and review a database-specific recovery procedure.
5. Obtain approval before any destructive schema operation.

Do not bypass the downgrade guard or manually drop columns as a routine
rollback procedure.

## Remaining acceptance work

1. Perform an actual worker process crash/restart recovery test.
2. Define handler-specific authorization, idempotency, timeout, and
   failure behavior before registering any external handler.
3. Add operational visibility for pending events, retries, and dead letters.
4. Review lease duration and recovery behavior for long-running handlers.
5. Complete the final code review and commit the Phase 1 changes.

The PostgreSQL concurrency tests have not run because no dedicated `agency_os_worker_test` database was provided. No migration has been applied to the user's database, and no production event handlers have been enabled.

## Operational configuration

- `OUTBOX_LEASE_SECONDS=120`
- `OUTBOX_BASE_RETRY_SECONDS=15`
- `OUTBOX_MAX_RETRY_SECONDS=3600`

Rows use `max_attempts=8` by default. Change this only through a reviewed schema/configuration change.

## Remaining before Phase 1 can be called production-validated

1. Apply the additive migration after a verified backup.
2. Run both PostgreSQL concurrency tests against the dedicated test database.
3. Register only the event handlers that have a defined consumer and idempotency strategy.
4. Exercise worker crash/restart and expired outbox lease recovery against PostgreSQL.
5. Add operational visibility/alerting for pending age, retries, and dead-letter counts.
