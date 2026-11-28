# Phase 1 — Failure-Injection Acceptance Plan

**Baseline:** `main` at `f07a8b7b8a864cbc08da35bf4b4c422cd4baf25e` (2026-11-28).
**Current posture:** reliability foundation implemented; final crash/restart and long-handler acceptance is not complete.
**Safety:** synthetic events and disposable PostgreSQL only. Never point these tests at a development, staging, or production database containing business data.

## Verified baseline

GitHub Actions run [46165349483](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/46165349483) completed successfully on the baseline commit. Both the backend and frontend jobs passed. The backend job explicitly completed runtime-image verification, isolated PostgreSQL role bootstrap, migration graph validation, migrations to disposable PostgreSQL, Python compilation, and backend/PostgreSQL integration tests. The frontend job completed type-checking and production build.

This confirms CI success for that commit. It does not establish a worker process crash/restart test, live provider behavior, production migration safety, or production readiness.

## Known behavior and gaps

- Outbox delivery is at-least-once. A handler can complete an external side effect and the process can die before the acknowledgement commits. Consumers must deduplicate with the stable `OutboxMessage.idempotency_key`.
- The handler registry is intentionally empty; no external side-effect handler is enabled.
- Expired processing leases can be reconciled and reclaimed.
- Outbox delivery now renews active leases from an independent session while a handler runs. Renewal is conditional on processing status, worker ID, claim-generation attempt count, and an unexpired current lease.
- If renewal fails or ownership is reclaimed, the handler is not forcibly interrupted. Its eventual acknowledgement/failure is rejected by the authoritative ownership check. Any external side effect still requires consumer-side idempotency.
- New PostgreSQL coverage simulates a real subprocess crash after claim commit, then reclaims the expired synthetic event. This does not simulate a process crash after an external side effect has committed.
- Health summaries are workspace-scoped and payload-free. Alert delivery and metrics export are not yet implemented.

## Required failure-injection matrix

Run every case against a disposable PostgreSQL database with the same role separation and RLS policies used by CI. Use a synthetic event with a stable idempotency key and a test consumer that records effects in a dedicated test table with a unique constraint on that key.

| Case | Injection point | Required assertion |
|---|---|---|
| A | Kill worker after claim commit, before handler starts | Lease expires; event is reclaimed; one effect is recorded |
| B | Kill worker after consumer effect commits, before outbox acknowledgement | Event is redelivered; consumer deduplicates; exactly one effect is recorded |
| C | Kill worker after handler raises, before failure state commits | Lease recovery eventually retries or dead-letters according to persisted attempt count |
| D | Pause handler beyond lease expiry, start second worker | Stale worker cannot acknowledge or overwrite the new owner's state; consumer idempotency prevents duplicate effect |
| E | Restart worker after lease expiry | Event progresses to published or dead-letter; no event remains permanently processing |
| F | Run two workers concurrently against a batch | A row is not concurrently owned by both workers before lease expiry |
| G | Exhaust configured attempts | Event reaches dead-letter and appears in workspace health without exposing payload |
| H | Inject provider-like credentials in exception text | Persisted error contains only safe error classification, never secret text |

## Long-running handler lease acceptance

Lease renewal is implemented, but handlers remain disabled until all remaining acceptance points pass:

1. Choose and document a strict handler timeout and maximum execution duration.
2. Python handlers are not forcibly interrupted when ownership is lost. They may finish, but must not acknowledge or mutate outbox state after losing ownership.
3. Implemented: renew only when the event is still `processing`, the claimant and claim-generation attempt count match, and the current lease has not already expired.
4. Implemented: use an independent session for renewal; stop the heartbeat on handler completion/failure and always perform an authoritative ownership check before acknowledgement/failure persistence.
5. SQLite tests cover a long handler; PostgreSQL tests cover stale-generation renewal refusal and process crash/reclaim. A PostgreSQL long-handler renewal race is still required.
6. Retain consumer-side idempotency. Lease renewal reduces duplicate work; it does not create exactly-once delivery.

## Operational visibility acceptance

Expose, per authorized workspace and without event payloads or secrets:

- Counts by pending, processing, published, and dead-letter state.
- Oldest pending age and expired lease count.
- Retry/exhaustion counts and last safe error classification.
- Bounded pagination or sampling for actionable dead-letter inspection.
- Alert thresholds for sustained pending age, expired leases, and dead-letter growth.

Any metrics labels must avoid high-cardinality identifiers and tenant-sensitive payload values. Cross-workspace aggregation must be explicitly authorized; do not infer it from organization membership.

## Release gate

Phase 1 remains **in progress** until the failure-injection matrix and long-handler ownership tests pass against disposable PostgreSQL, the operational visibility checks pass, and the resulting CI run is green. Keep the handler registry empty until each handler has a reviewed authorization, data-classification, idempotency, timeout, cancellation, and failure contract.

No production deployment, migration, handler activation, or destructive cleanup is authorized by this plan.
