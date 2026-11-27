# Delivery operations vertical slice (v5)

This release adds a small, OS-owned operating layer for repeatable service delivery, scope governance, time capture and project-level commercial visibility. It is not an accounting system or a complete project-management suite.

## Included capabilities

### Service playbooks
- Workspace-scoped reusable playbooks with service line, workflow, required inputs, deliverables, acceptance criteria and security checks.
- New playbooks begin in `draft`.
- Only an active `FounderAuthority` grant can activate or retire a playbook.
- Status changes increment the playbook version.
- Playbooks are operating references; they do not autonomously launch projects or assign agents.

### Scope and change control
- Scope changes record the requested work, delivery impact, estimated-hours delta, cost-budget delta, contract-value delta and schedule delta.
- A change starts in `pending_approval`.
- Acceptance requires a single-use approval with action type `scope.change.accept`, exact workspace and change-request ID.
- The protected endpoint consumes the approval and applies project deltas in the same database transaction.
- Rejected requests require active Founder Authority.
- Negative resulting budget, contract value or estimate is rejected.
- The project due date is adjusted only when one is already set.

### Time and capacity inputs
- A time entry is attached to one workspace/project and optionally a task.
- The authenticated user is the logger; the API does not allow logging time as another user.
- Duration is bounded to 1–1,440 minutes per entry.
- The hourly cost rate is snapshotted on the entry in minor currency units per hour.
- Project financial summary reports estimated hours versus recorded actual hours.
- This is lightweight project time capture, not payroll, attendance or HR timesheets. Weekly capacity planning and resource scheduling remain future work if real demand justifies them.

### Project costs and provisional margin
- Project costs are recorded with category, description, amount, currency and incurred date.
- Cost currency must match the project currency. FX conversion is deliberately not inferred.
- Summary reports contract value, spend budget, estimated hours, actual time, labor cost, other costs, actual cost, provisional gross margin and remaining budget.
- Amounts are stored in minor currency units (for INR, paise).
- The summary is a management estimate, not statutory accounting. It excludes unrecorded costs/time, tax, receivables, FX, depreciation and accounting adjustments.

### Founder exception inbox
The read-only operations inbox aggregates:
- Pending approval requests.
- Blocked tasks.
- Failed and retry-wait executions.

It does not approve requests, retry work or reassign tasks. Those actions remain explicit operations with their own authorization and audit path.

### Agent execution reliability
The agent performance endpoint reports execution counts, succeeded/failed/active counts and attempt totals by registered agent. These are reliability indicators, not a quality score. QA acceptance remains separate from business impact. Client outcomes are now tracked through the RAAS project-outcome records and source-backed measurements; source metadata is not an independent attestation, and automated impact verification remains future work.

## API surface

Base path: `/v1/orgs/{org_id}/operations`

- `GET/POST /playbooks`
- `PATCH /playbooks/{playbook_id}/status`
- `GET/POST /scope-changes`
- `POST /scope-changes/{change_id}/approve`
- `POST /scope-changes/{change_id}/reject`
- `GET/POST /time-entries`
- `GET/POST /project-costs`
- `GET /projects/{project_id}/financial-summary?workspace_id=...`
- `GET /exceptions?workspace_id=...`
- `GET /agent-performance?workspace_id=...`

All routes require an authenticated principal and organization membership. Writes require an allowed organization role. Workspace and parent records are checked within the same organization/workspace.

## Scope-change approval sequence

1. Create a change request with `POST /operations/scope-changes`.
2. Create an approval using the existing approvals endpoint:
   - `action_type`: `scope.change.accept`
   - `resource_id`: the returned scope-change ID
   - `workspace_id`: the exact workspace
   - `idempotency_key`: a unique request key
3. A founder with active Founder Authority approves it through the existing approval decision endpoint.
4. Call `POST /operations/scope-changes/{change_id}/approve` with `{ "approval_id": "..." }`.
5. The handler validates and consumes the approval, applies the scope deltas, writes audit and outbox records, then commits.

Do not update project scope or commercial values directly to bypass this path.

## Event boundary

Mutations write an outbox record in the same transaction as the business change. The dispatcher, lease management, retries, dead-letter handling and reconciliation are not implemented by this vertical slice. An outbox row is durable intent, not proof that an external action has happened.

## Remaining work

- Full outbox dispatcher and idempotent consumer framework.
- Supervisor-driven task decomposition, delegation, review, bounded retries and escalation.
- Production OIDC/JWKS/MFA and machine identities.
- Endpoint-level policy enforcement for every autonomous action.
- Complete data-protection gateway, runtime eligibility and retention/deletion lifecycle.
- PostgreSQL migration and concurrency validation in the user's environment.
- Full frontend workflows for playbooks, time entry, costs and scope-change authoring; this release adds the exception/performance overview page and APIs.
- Live email/telephony integrations, consent enforcement, webhook verification and reconciliation.
- QA acceptance metrics, client lifecycle/handover workflow and complete finance ledger.
- Production monitoring, backup/restore drills and security review.

The bundle is a stronger development foundation, not a production-ready autonomous business OS.
