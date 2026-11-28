# Phase 1 — Failure-Injection Acceptance Plan

**Verified code baseline:** `main` at `6d70292596beeea86eb778a09fa04faeed06305e` (2026-11-28).
**Current posture:** lease ownership, generation fencing, long-handler renewal and synthetic crash-after-effect idempotency tests are implemented and CI-tested. Additional PostgreSQL process-crash tests now cover failure before handler start and failure after a handler exception but before retry-state persistence; those new tests are awaiting a non-cancelled CI run. The full failure-injection matrix and operational release gates remain incomplete.
**Safety:** synthetic events and disposable PostgreSQL only. Never point these tests at a development, staging, or production database containing business data.

## Verified baseline

GitHub Actions run [46168046099](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/46168046099) completed successfully on the verified code baseline. The backend suite reported **687 passed in 54.82 seconds**, including PostgreSQL 16 integration tests for claim-generation fencing, worker-process crash after a synthetic consumer effect, and long-handler lease renewal. The backend job also completed runtime-image verification, isolated PostgreSQL role bootstrap, migration graph validation, migrations to disposable PostgreSQL and Python compilation. The frontend job completed type-checking and production build.

This confirms CI success for that commit. It does not establish a worker process crash/restart test, live provider behavior, production migration safety, or production readiness.

## Known behavior and gaps

- Outbox delivery is at-least-once. A handler can complete an external side effect and the process can die before the acknowledgement commits. Consumers must deduplicate with the stable `OutboxMessage.idempotency_key`.
- The handler registry is intentionally empty; no external side-effect handler is enabled.
- Expired processing leases can be reconciled and reclaimed.
- Outbox delivery now renews active leases from an independent session while a handler runs. Renewal is conditional on processing status, worker ID, claim-generation attempt count, and an unexpired current lease.
- If renewal fails or ownership is reclaimed, the handler is not forcibly interrupted. Its eventual acknowledgement/failure is rejected by the authoritative ownership check. Any external side effect still requires consumer-side idempotency.
- PostgreSQL coverage simulates a real subprocess crash after a synthetic consumer side effect commits but before acknowledgement. The event is reclaimed and the consumer replay uses a unique idempotency key; the test asserts exactly one effect. This is a database-backed test consumer, not a live external provider. The test is included in the 687-test passing CI run.
- Additional PostgreSQL subprocess tests now inject process death after a claim commits but before the handler starts, and after a handler exception reaches the failure-persistence boundary but before retry state commits. These tests assert that the still-leased event is recovered after expiry and can be completed by a subsequent worker. Their current-head CI verification is pending; do not count them as passed yet.
- Health summaries are workspace-scoped and payload-free. Alert delivery and metrics export are not yet implemented.

## Required failure-injection matrix

Run every case against a disposable PostgreSQL database with the same role separation and RLS policies used by CI. Use a synthetic event with a stable idempotency key and a test consumer that records effects in a dedicated test table with a unique constraint on that key.

| Case | Injection point | Required assertion |
|---|---|---|
| A | Kill worker after claim commit, before handler starts | Lease expires; event is reclaimed; event can be completed by the next worker |
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
5. CI-tested: SQLite and PostgreSQL tests cover long-handler renewal; PostgreSQL tests also cover stale-generation renewal refusal and a real subprocess crash/reclaim after the synthetic effect commits.
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
