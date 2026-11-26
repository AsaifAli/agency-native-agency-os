# Worker Database Authorization Contract Inventory

**Date:** 2026-11-26  
**Scope:** Replace worker-forgeable PostgreSQL workspace GUCs without interrupting durable execution, recovery, or outbox delivery.

**Status:** Source inventory and target contract documented. No privilege cutover or RLS policy change has been made. This document is not evidence of implemented tenant isolation.

## Security finding

The worker role is NOBYPASSRLS, but current RLS predicates trust transaction-local custom settings including `agency_os.machine_org_id` and `agency_os.machine_workspace_id`. The worker can set those values itself. The worker also has direct CRUD privileges on many public tables. Consequently, current controls mitigate accidental unscoped ORM queries and pool leakage, but do not provide an independent database authorization boundary against arbitrary SQL under a compromised worker credential.

Removing `worker_workspace_scopes()` alone, or adding a claim function while leaving direct table access and caller-settable GUC trust, would be security theater.

## Current worker operation inventory

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
- Delegation scheduling, retry promotion, lease recovery, machine-session expiry and outbox maintenance are scheduler powers, not execution powers. They need distinct bounded contracts.
- `expire_due_agent_sessions` currently runs once per enumerated workspace; replace it with bounded global maintenance.
- Direct CRUD grants and raw GUC policies are both part of the weakness. Both must be addressed.

## Target capability model

1. `agency_os_worker` receives EXECUTE only on narrowly specified claim, lease and maintenance contracts. It has no default SELECT/INSERT/UPDATE/DELETE access to tenant tables.
2. An execution claim atomically creates a database-owned, unguessable, short-lived capability bound to execution ID, attempt ID, worker ID, lease generation and expiry. The capability is returned only for the claimed attempt. No signing key or generic capability-minting function is exposed to the worker.
3. Each follow-up transaction proves the capability through a SECURITY DEFINER verifier. The verifier establishes private transaction context inaccessible to worker SQL. Worker RLS predicates consult that private context, never caller-settable raw GUC values.
4. Expiry, recovery, cancellation, completion and lease replacement invalidate the capability atomically. A stale worker cannot heartbeat, attach provider IDs, persist control events, complete, fail or acknowledge cancellation.
5. Outbox delivery uses a different capability and lease generation. Scheduler maintenance has separate bounded operations. Browser-session retention remains isolated.
6. Human API identity assertions, browser-session bootstrap, machine identity and website intake are separate migration streams. Do not conflate their signing/capability contracts with worker lease capabilities.

## PostgreSQL acceptance tests required before privilege cutover

- With no capability, worker cannot read tenant tables including executions, attempts, tasks, agents, delegations, agent_sessions, outbox_events, audit and workforce tables.
- Setting historical `agency_os.*` GUCs to another tenant's values does not grant access.
- Worker cannot read verifier secrets/private capability rows or invoke internal capability minting/verifier functions directly.
- Claim returns one execution and capability atomically; concurrent workers cannot claim the same attempt.
- Capability fails for another execution, attempt, worker ID, altered bytes, wrong generation, expired lease, recovered attempt, terminal execution, replay or another pooled connection/transaction.
- Every lifecycle transition rejects stale capabilities. Idempotency is supported only where explicitly defined.
- Worker cannot perform scheduler, outbox or retention operations except through separately granted bounded functions.
- Outbox stale ack/failure cannot overwrite a newer lease; external handler execution remains outside transactions and duplicate delivery remains safe through idempotency keys.
- Cross-tenant/workspace tests cover raw SQL and ORM paths, commit, rollback, pool reuse, heartbeat threads and provider callbacks.
- Privilege tests inspect `has_table_privilege`, `has_function_privilege`, role memberships, function ownership, SECURITY DEFINER search paths and PUBLIC grants.

## Rollout and rollback gates

Do not revoke worker table privileges or switch RLS policies until every operation above has an implemented replacement, tests run against PostgreSQL using the actual `agency_os_worker` login, and the worker runtime uses the new contracts.

A migration that removes access first will stop the worker. A migration that leaves direct CRUD or raw GUC predicates in place is not a security fix. Preserve a tested downgrade and recoverable deployment sequence. The API human/machine assertion work remains a separate migration stream.

## Work sequence

1. Add schema for private lease capabilities and transaction-bound context; ensure worker role cannot read or write it.
2. Add tests first for capability minting restrictions, forged GUC rejection and cross-tenant denial.
3. Implement database-owned atomic claim and lease-bound read envelope.
4. Convert start, heartbeat, provider-run attachment, controls, completion and failure.
5. Convert retry/recovery and dependent task/delegation/plan/audit updates.
6. Convert delegation scheduler, machine-session expiry and outbox into separate bounded contracts.
7. Switch RLS predicates to private verified context and revoke worker direct table/sequence privileges.
8. Run full PostgreSQL negative, concurrency, crash-recovery, pool-reuse and privilege tests.
9. Only then remove `worker_workspace_scopes()` and legacy worker GUC policy branches in a reviewed migration.
