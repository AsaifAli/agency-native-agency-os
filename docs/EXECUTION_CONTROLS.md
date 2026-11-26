# Execution controls — implementation notes

## Current slice: cancellation, pause and resume

The integration branch adds:

- `POST /v1/orgs/{org_id}/executions/{execution_id}/cancel?workspace_id=...`
- `POST /v1/orgs/{org_id}/executions/{execution_id}/pause?workspace_id=...`
- `POST /v1/orgs/{org_id}/executions/{execution_id}/resume?workspace_id=...`
- Membership role gate: owner, admin or operator.
- Exact active workspace-grant check; execution lookup is scoped by organization and workspace. Explicit Founder Authority can operate the control independently of organization role, consistent with the founder exception inbox.
- Durable cancellation intent in the existing allowlisted execution metadata, with audit events.
- Queued executions with no prior attempts become terminal immediately.
- Queued/retry-wait executions with prior attempts are sent back through worker reconciliation (retry backoff is bypassed). If the retry budget is exhausted, the OS records `CANCEL_REQUIRES_MANUAL_REVIEW` instead of claiming a successful stop.
- Active executions are not marked cancelled merely because a request was received. The worker must own a valid lease and acknowledge the request.
- Claude Managed Agents receives `user.interrupt`; the adapter persists the provider event ID under the active worker lease, then waits for that exact event to have a non-null `processed_at`, the session to be idle, and all workflow runs to have ended before the OS acknowledges cancellation.
- If a worker restarts after the interrupt ID was persisted, the next attempt reuses that event ID and reconciles its status rather than sending another interrupt.
- If an earlier provider session may exist but its ID was not durably recorded, the runtime requests manual review rather than asserting cancellation.
- Pause is persisted as an execution and attempt state. A queued execution with no attempts pauses immediately; an active Managed Agents execution is paused only after the exact interrupt event is processed, the provider session is idle, and all workflow runs are drained.
- Resume is a new leased worker attempt against the prior durable provider session. The OS generates a unique resume token, embeds it in the provider message, searches provider event history before sending, and persists the provider event ID. A retry that finds the marker does not send a duplicate resume message. Repeated API resume requests are idempotent while the execution is queued or active.
- A pause before the first provider session is created resumes as a fresh session. A pause after a session ID is persisted resumes that same session.
- Active or previously attempted runtimes without safe provider interruption support reject pause. Generic runtimes must not pretend to pause mid-call; they can finish or be stopped according to their own supported semantics.
- Paused executions remain non-terminal (`finished_at` stays null). Resume is rejected when the bounded execution attempt budget is exhausted; that case requires manual review.

## Important boundaries

- This is cooperative cancellation, not an operating-system kill signal. A provider call or OS tool action already in progress may need to reach a safe boundary.
- Claude's interrupt event does not end open workflow runs. The adapter drains and verifies them; a deadline without drain becomes manual review.
- The current execution-attempt enum still has no `cancelled` value. Acknowledged cancelled executions close the attempt as `failed` with `EXECUTION_CANCELLED`; the execution itself is `cancelled`. This remains a schema normalization item.
- The pause-state migration adds PostgreSQL enum labels additively. Downgrade intentionally retains those labels because safely removing PostgreSQL enum values requires rebuilding dependent columns and may conflict with rows written after upgrade.

## Verification status

Focused service, worker, API and runtime tests have been added on `feat/agency-os-consolidation`. They have **not yet been executed**. No GitHub Actions workflow was triggered. Do not treat this slice as production-verified until the focused SQLite tests, PostgreSQL integration tests, full backend suite, and failure/recovery scenarios pass on the exact branch head.
