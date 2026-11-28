# Execution Usage and Recovery Audit

Date: 2026-11-28

## Scope

Source audit of execution attempts, worker leases, Managed Agents session recovery, provider usage persistence, and retry aggregation. This is an audit/design note; it does not change runtime behavior or enable new provider actions.

## Verified implementation

- Execution creation is idempotent per organization and idempotency key. The database uniqueness constraint is the final concurrency guard.
- PostgreSQL worker claims create a durable attempt and a short-lived, hash-bound worker capability in the database-controlled claim path. Provider work runs outside the database transaction.
- Worker heartbeats renew the attempt lease and the PostgreSQL worker capability. Failure to confirm renewal is surfaced rather than silently treated as healthy.
- Expired claimed/running attempts are marked `abandoned`; the execution is moved to retry wait or failed when the attempt limit is exhausted. Recovery is bounded and records audit events.
- Managed Agents persists the provider session ID before continuing. Later attempts receive the most recent persisted external run ID and resume that session. Ambiguous create/persist outcomes are sent to manual review rather than blindly creating another provider session.
- The adapter reads usage from the provider session response (or the latest `session.usage` event), normalizes bounded numeric fields, and persists usage with the attempt result when a terminal result or review-required outcome is returned.
- `fail_execution` aggregates usage present on persisted attempt results. Successful completion also aggregates usage across persisted attempts. The current unit test explicitly models each attempt's usage as an additive increment.
- The Managed Agents adapter sends a per-session provider budget in USD. This is not a workspace-wide cumulative spend limit.

## Confirmed accounting defect and correction

Anthropic's current Managed Agents documentation explicitly defines the session object's `usage` and the `session.usage` event as **cumulative usage across all turns**. It also states that the session-level figure is authoritative. See:

- https://platform.claude.com/docs/en/managed-agents/session-observability
- https://platform.claude.com/docs/en/api/typescript/beta/sessions

The previous OS aggregation summed every persisted attempt usage object. Because retries resume the same provider session, this double-counted earlier turns. The implementation now groups Managed Agents attempt observations by persisted `external_run_id` and uses the latest attempt's cumulative snapshot for each session. Distinct provider sessions are added together. Other runtimes retain additive per-attempt aggregation until their usage contract is documented.

Regression coverage now proves both behaviors: later cumulative snapshots replace earlier snapshots for the same session, and separate Managed Agents sessions are additive.

Remaining accounting work:

- Persist provider observation identity/timestamp and reconcile session snapshots idempotently if a background reconciliation job is added. The current bounded recovery pass now persists a snapshot hash and OS observation timestamp inside the abandoned attempt result; it does not yet maintain a separate append-only observation table.
- Reconcile ambiguous/abandoned sessions by fetching the authoritative session object after idle; do not infer cost deltas from cumulative snapshots. The workspace-scoped worker maintenance pass now performs this read for abandoned Managed Agents attempts belonging to retry-wait or failed executions.
- If a latest attempt has no usage because the worker died before persisting it, the last known snapshot remains a lower bound until provider reconciliation. Missing usage must never be treated as zero.

## Recovery accounting gap

A worker can die after provider work has incurred cost but before the adapter returns and persists usage. Lease recovery currently records an abandoned attempt and retries/resumes the provider session when a durable session ID exists, but it cannot recover usage merely from the abandoned attempt row. This leaves a temporary or permanent gap in OS-side usage reporting until provider-session reconciliation is implemented. The provider-side session budget still constrains that individual session, but it does not solve workspace cumulative spend accounting.

Recovery reconciliation now works as follows: A retry copies the previous same-runtime provider session ID onto the new attempt before provider work starts, so resumed cumulative usage remains grouped under one session rather than being added as a separate attempt delta. a bounded maintenance pass selects failed or abandoned Managed Agents attempts with durable provider session IDs, closes its DB read transaction, fetches the provider session object, and accepts usage only when the provider reports `idle` or `terminated` and no dynamic workflow run remains open. Anthropic documents `idle` as the normal completed-work state; `terminated` covers archived or unrecoverable sessions. The persistence transaction then locks the execution followed by the attempt and rechecks that the execution is still `retry_wait` or `failed` and the attempt is still `failed` or `abandoned` with the same session ID. A canonical SHA-256 snapshot hash, observation timestamp and audit event make persistence idempotent. The same provider session is refreshed at most once every five minutes while its execution remains retry-wait/failed, so later cumulative snapshots can replace earlier idle snapshots without double-counting. Provider read errors, open workflow runs and non-idle/missing usage are recorded as pending without persisting a zero; retries are cooled down for five minutes. The pass is capped at ten provider reads per workspace per maintenance cycle. Provider HTTP calls never run inside a DB transaction.

This closes the immediate missing-usage gap for failed/abandoned attempts when Anthropic returns a terminal session with a usage snapshot. It does not create workspace spend reservations or an append-only usage ledger. Before a workspace spend ledger is enforced, keep amounts reserved/unknown until a provider session snapshot or an authorized manual reconciliation resolves them. Do not treat missing usage as zero and do not release a reservation merely because a worker lease expired.

## Existing safety boundaries to preserve

- Keep provider calls outside database transactions.
- Keep execution/attempt state and audit owned by Agency OS; provider session IDs are correlation handles, not authorization credentials.
- Preserve single-session resume behavior and manual review on ambiguous provider create/persist outcomes.
- Do not introduce a second Claude runtime or custom sandbox solely to solve usage accounting.
- Do not compare `WorkforceCapability.budget_minor` (currently INR by default and not enforced) with provider USD usage. Currency and period policy must be explicit.
- Do not invent a workspace spend limit or lifetime/monthly period. Founder policy is still required before enforcement.

## Next engineering sequence

1. Run an authorized synthetic Managed Agents staging session to verify live usage fields and idle/terminated transitions; documentation semantics have been reviewed, but live provider compatibility remains unverified.
2. Add a versioned provider-usage observation model keyed idempotently by provider + session + provider observation/event identity; keep raw provider payloads out of logs and retain only allowlisted normalized fields.
3. Reconcile ambiguous/abandoned sessions before retrying or finalizing spend; bound pages, duration, and provider calls, and route unresolved outcomes to manual review.
4. Only then implement atomic USD-cent workspace reservations/settlement with the founder-selected period/limit policy, concurrency tests, idempotency tests, and unknown-outcome handling.

## Status

- Execution lease claim/heartbeat/recovery: implemented; covered by existing tests and CI.
- Provider session ID persistence/resume safeguards: implemented in the adapter; external provider behavior remains dependent on current Anthropic contract and account configuration.
- Per-session provider budget: implemented in the adapter; not a workspace cumulative limit.
- Managed Agents usage aggregation: implemented with latest cumulative snapshot per provider session; regression tests cover resumed and distinct sessions.
- Recovery-time provider usage reconciliation: implemented in bounded workspace-scoped maintenance; covered by unit tests for idle snapshots, non-idle deferral, open workflow-run deferral, retry cooldown, cumulative snapshot refresh, idempotency, failed/abandoned attempt recovery, execution-state fencing and same-session retry linking. CI verification is pending for the latest implementation commit.
- Separate append-only provider observation ledger: planned, not implemented.
- Workspace cumulative spend ledger and ambiguous-outcome reservation/settlement: planned, not implemented.
