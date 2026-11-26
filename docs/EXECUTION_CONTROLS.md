# Execution controls — implementation notes

## Current slice: cancellation request and acknowledgement

The integration branch adds:

- `POST /v1/orgs/{org_id}/executions/{execution_id}/cancel?workspace_id=...`
- Membership role gate: owner, admin or operator.
- Exact active workspace-grant check; execution lookup is scoped by organization and workspace.
- Durable cancellation intent in the existing allowlisted execution metadata, with audit events.
- Queued executions with no prior attempts become terminal immediately.
- Queued/retry-wait executions with prior attempts are sent back through worker reconciliation. If the retry budget is exhausted, the OS records `CANCEL_REQUIRES_MANUAL_REVIEW` instead of claiming a successful stop.
- Active executions are not marked cancelled merely because a request was received. The worker must own a valid lease and acknowledge the request.
- Claude Managed Agents receives `user.interrupt`; the adapter waits for the exact interrupt event to have a non-null `processed_at`, the session to be idle, and all workflow runs to have ended before the OS acknowledges cancellation.
- If an earlier provider session may exist but its ID was not durably recorded, the runtime requests manual review rather than asserting cancellation.

## Important boundaries

- This is cooperative cancellation, not an operating-system kill signal. A provider call or OS tool action already in progress may need to reach a safe boundary.
- Claude's interrupt event does not end open workflow runs. The adapter drains and verifies them; a deadline without drain becomes manual review.
- The current execution-attempt enum has no `cancelled` value. Acknowledged cancelled executions currently close the attempt as `failed` with `EXECUTION_CANCELLED`; the execution itself is `cancelled`. This should be normalized in a future migration.
- The mock runtime has no long-running external operation. Other future runtimes must implement the runtime control callback to support provider-side interruption.
- Pause/resume is not implemented in this slice. It needs explicit persisted pause state, provider checkpoint/resume semantics, and lease handoff; it must not be simulated by changing a UI status.

## Verification status

Focused service, API and runtime tests have been added on `feat/agency-os-consolidation`. They have **not yet been executed**. No GitHub Actions workflow was triggered. Do not treat this slice as production-verified until the focused SQLite tests, PostgreSQL integration tests, full backend suite, and failure/recovery scenarios pass on the exact branch head.
