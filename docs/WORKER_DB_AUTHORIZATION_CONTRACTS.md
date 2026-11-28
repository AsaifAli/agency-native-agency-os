# Worker Database Authorization Contract Inventory

**Last reconciled:** 2026-11-28  
**Scope:** PostgreSQL worker authorization, execution leases and bounded workspace maintenance.

**Status:** The initial execution and maintenance capability cutover is implemented on consolidated PR #71. Migrations `a7c2e9f4b1d6` and `e1f4a6b8c0d2` establish PID/transaction-bound execution and workspace capabilities. Worker RLS no longer trusts caller-settable machine tenant GUCs. The legacy `worker_workspace_scopes()` function is not an authorization path and its EXECUTE privilege is revoked from `agency_os_worker`.

The worker remains `NOBYPASSRLS` and has a narrow explicit table/column privilege allowlist (SELECT on 14 named tables, INSERT on 4, UPDATE on 8; no table DELETE or sequence privileges). Row access still requires a live database-verified execution or workspace capability. Private capability tables are inaccessible to both app and worker roles. The worker is explicitly denied access to Private Operations tables until a separate execution-capability integration is designed and tested.

Live PostgreSQL 16 CI verification on the consolidated candidate passed **579 backend tests, 0 skipped, 2 warnings** in [run 46133997208](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/46133997208). This is disposable CI evidence, not a production migration rehearsal or production approval.

## Historical pre-cutover security finding

Before the capability cutover, the worker role was `NOBYPASSRLS` but RLS predicates trusted transaction-local settings including `agency_os.machine_org_id` and `agency_os.machine_workspace_id`. A compromised worker could set those values itself. The worker also held broad direct CRUD privileges. Those controls mitigated accidental unscoped ORM queries and pool leakage but did not provide an independent database authorization boundary. The migrations above replace that authorization path; do not treat this historical finding as the current implementation.

## Pre-cutover worker operation inventory (historical)

| Operation | Current implementation / data dependencies | Required replacement contract |
|---|---|---|
| Tenant discovery | `app.db:list_worker_scopes`; `agency_os_private.worker_workspace_scopes()` | Remove as authorization. Worker must not enumerate workspace IDs and replay them as scope. |
| Execution claim | `app.worker_service:claim_next_execution`; executions, execution_attempts, audit_events | Atomic global claim, derive tenant from locked eligible execution, create lease capability, return bounded execution envelope. |
| Execution input load | `app/worker/processor.py`; executions, attempts, agents, tasks | Read only through valid lease capability; return only fields required by runtime and DPG. |
| Start / heartbeat | `start_execution`, `heartbeat_execution`; execution, attempt, delegation/plan synchronization, audit | Lease-bound state transition validating execution, attempt, worker, generation, expiry and legal state. |
| Provider run attachment | `attach_external_run_id` | Lease-bound, write-once provider run attachment. |
| Control polling / provider events | `app/execution_controls.py`; execution metadata and audit | Lease-bound read/write; prevent stale lease and event replay. |
| Complete / fail / cancel / pause | `complete_execution`, `fail_execution`, control acknowledgements | Atomic lease-bound terminal transition plus dependent task/delegation/plan updates and audit. |
| Retry promotion | `promote_due_retries` | Bounded scheduler maintenance function; no general tenant scope. |
| Lease recovery | `recover_expired_execution_leases` | Bounded global recovery function with lock-order preservation and expiry recheck; invalidate old capability atomically. |
| Delegation scheduling | `queue_ready_delegations`; delegations, tasks, workforce_members, agents, executions, plans, audit | Separate scheduler capability and bounded procedure; idempotency key required. Not an ordinary execution-worker capability. |
| Machine-session expiry | `expire_due_agent_sessions`; agent_sessions, audit_events | Bounded global maintenance function; worker cannot enumerate sessions or choose tenant. |
| Outbox reconciliation | `reconcile_outbox_events`; outbox_events | Bounded global maintenance operation with internal row selection. |
| Outbox claim / ack / retry | `claim_outbox_batch`, `_acknowledge`, `_record_failure`; outbox_events | Independent outbox lease capability and generation. Ack/failure must match message, worker and lease generation. Never reuse execution capability. |
| Browser-session retention | `prune_expired_browser_sessions()` SECURITY DEFINER | Existing bounded contract is the desired pattern; retain restricted EXECUTE only. |

## Dependencies that make a partial migration unsafe

- Execution lifecycle operations call `_sync_task_delegation` and `_sync_plan_draft_execution`. Their updates and audit writes must remain atomic with execution state, either inside the same database contract or through separately validated internal procedures.
- `process_one_execution` reads Agent and Task data after claim and reads prior `ExecutionAttempt.external_run_id`. The worker needs a narrow lease-bound execution envelope, not general workspace access.
- Managed Agents tool calls use `build_machine_tool_executor`. Tool authorization is a separate boundary and must not inherit a generic execution workspace scope.
- Outbox handlers deliberately run outside database transactions. Claim and persist an outbox lease, return a bounded message, execute the handler externally, then validate the same lease generation on ack/failure. At-least-once delivery and handler idempotency remain mandatory.
- Delegation scheduling, retry promotion, lease recovery, machine-session expiry and outbox maintenance are scheduler powers, not execution powers. Keep them bounded and separately authorized; the workspace maintenance capability is not an execution capability or a substitute for the outbox message lease.
- `expire_due_agent_sessions` and other workspace maintenance now run under a separate short-lived workspace capability, one workspace at a time. Do not substitute this capability for execution or outbox authorization.
- Broad CRUD grants and caller-settable GUC authorization were the pre-cutover weaknesses. The candidate replaces broad grants with the asserted allowlist and excludes the worker role from GUC-based human/machine policy branches.

## Implemented capability model

1. `agency_os_worker` receives EXECUTE only on narrowly specified claim, lease and maintenance contracts. It has no default SELECT/INSERT/UPDATE/DELETE access to tenant tables.
2. An execution claim atomically creates a database-owned, unguessable, short-lived capability bound to execution ID, attempt ID, worker ID, lease generation and expiry. The capability is returned only for the claimed attempt. No signing key or generic capability-minting function is exposed to the worker.
3. Each follow-up transaction proves the capability through a SECURITY DEFINER verifier. The verifier establishes private transaction context inaccessible to worker SQL. Worker RLS predicates consult that private context, never caller-settable raw GUC values.
4. Expiry, recovery, cancellation, completion and lease replacement invalidate the capability atomically. A stale worker cannot heartbeat, attach provider IDs, persist control events, complete, fail or acknowledge cancellation.
5. Outbox delivery retains its own message lease/generation and idempotency contract; it is not authorized by an execution capability. Workspace maintenance uses a distinct short-lived workspace capability. Browser-session retention remains a bounded SECURITY DEFINER operation.
6. Human API identity assertions, browser-session bootstrap, machine identity and website intake are separate migration streams. Do not conflate their signing/capability contracts with worker lease capabilities.

## PostgreSQL acceptance tests and remaining release checks

The consolidated CI suite executes the human and worker PostgreSQL suites with actual dedicated `NOBYPASSRLS` logins. The current passing run is linked above. The tests assert that tables outside the explicit allowlist are denied at the SQL privilege layer and that granted tables reveal no tenant rows without a valid capability.

- With no capability, worker cannot read tenant rows from its granted tables, including executions, attempts, tasks, agents, delegations, agent_sessions, outbox_events, audit and workforce tables.
- Setting historical `agency_os.*` GUCs to another tenant's values does not grant access.
- Worker cannot read verifier secrets/private capability rows or invoke internal capability minting/verifier functions directly.
- Claim returns one execution and capability atomically; concurrent workers cannot claim the same attempt.
- Capability fails for another execution, attempt, worker ID, altered bytes, wrong generation, expired lease, recovered attempt, terminal execution, replay or another pooled connection/transaction.
- Every lifecycle transition rejects stale capabilities. Idempotency is supported only where explicitly defined.
- Scheduler/maintenance operations must remain bounded and separately authorized; outbox ack/retry must match the current message lease/generation; browser-session retention is exposed only through its restricted function contract.
- Outbox stale ack/failure cannot overwrite a newer lease; external handler execution remains outside transactions and duplicate delivery remains safe through idempotency keys.
- Cross-tenant/workspace tests cover raw SQL and ORM paths, commit, rollback, pool reuse, heartbeat threads and provider callbacks.
- Privilege tests inspect `has_table_privilege`, `has_function_privilege`, role memberships, function ownership, SECURITY DEFINER search paths and PUBLIC grants.

## Rollout and rollback gates

The initial capability cutover is implemented and verified against PostgreSQL 16 in CI. It is not yet a production migration rehearsal. The downgrade path deliberately refuses to restore vulnerable GUC-authorized worker policies; recovery from an unsafe rollback requires a reviewed database restore, not a policy downgrade.

Before production, run multi-worker concurrency, lease-expiry/recovery, crash-after-provider-call, pooled-connection reuse, outbox duplicate-delivery and reconciliation drills against a disposable staging-like database. Review the exact grant inventory and migration plan, back up the target database, and obtain explicit founder approval. The API human/machine assertion work remains a separate migration stream.

## Work sequence and status

1. Private execution capability tables and transaction-bound context: **implemented**.
2. Capability minting restrictions, forged-GUC rejection and cross-tenant tests: **implemented and passing in CI**.
3. Database-owned atomic execution claim and lease-bound access: **implemented**.
4. Start, heartbeat, provider-run attachment, control, completion and failure paths: **implemented**.
5. Retry/recovery and dependent task/delegation/plan/audit updates: **implemented; broader crash/concurrency drills remain**.
6. Workspace maintenance uses a separate short-lived capability; outbox operations retain their own lease/idempotency boundaries.
7. Worker RLS uses private verified context; explicit table/column grants replace broad CRUD. The worker cannot execute the legacy global workspace enumerator.
8. PostgreSQL 16 negative/privilege suites: **passed in CI**. Production-like concurrency, crash-recovery and reconciliation drills remain.
9. Do not drop shared human/API GUC policy branches: they still serve separate non-worker identity paths. Remove the unused legacy worker enumerator only after a compatibility review.
