# Claude delegation strategy and Agency OS control boundary

**Decision:** Delegate reasoning, specialist analysis and bounded execution to Claude Managed Agents wherever it materially improves throughput. Keep durable agency state, authority and side-effect control in Agency OS.

**Status:** Architecture decision; implementation and live-provider validation pending. Managed Agents is beta and is not ZDR- or HIPAA-eligible. Do not send confidential, regulated or client-restricted data unless the applicable policy explicitly authorizes the runtime and the data-handling review is complete.

## 1. Responsibility split

### Claude Managed Agents owns execution

Use Claude for:
- Chief of Staff synthesis, task decomposition proposals and progress summaries.
- Department specialist reasoning: research, analysis, drafting, solution design, code generation, QA analysis and client-success preparation.
- Parallel subagents for independent research/review work.
- Dynamic workflows for multi-phase, parallelizable analysis, migrations, audits and document-heavy work.
- Advisor-model consultation for bounded high-impact reasoning where the budget permits.
- Skills for reusable domain procedures and MCP connectors for approved external systems.
- Sandboxed file/code/web work inside an explicitly configured and restricted environment.

Prefer predefined specialist agents with their own model, system instructions, tools, MCP servers and skills. Permit inline agents only for low-risk, non-side-effecting work when the OS policy allows them. Use dynamic workflows for independent workstreams, not as the default for every request. Set session budgets and timeouts before starting work.

### Agency OS owns control and durable state

The OS remains authoritative for:
- Founder identity and founder-only authority; department, workforce member and agent registry.
- Organization, client and workspace tenancy; RBAC/ABAC and exact capability grants.
- Task/delegation graph, dependencies, assignments, execution attempts, leases, retries, cancellation and reconciliation.
- Data classification, minimization, runtime eligibility and client authorization.
- Tool registry, tool/action/scope authorization, approval consumption and policy checks.
- Budgets/reservations, usage ledger, concurrency limits and cost reconciliation.
- Business records (CRM, leads, pipeline, proposals, contracts, projects, delivery and finance).
- Artifact references, audit, outbox, retention, deletion and recovery.
- Founder approval for sensitive communications, pricing, contracts, payments, permission changes, production releases and destructive actions.

Claude may propose, reason, prepare and execute only the work delegated under a persisted OS execution. It cannot create its own authority, grant itself capabilities, approve protected actions or directly mutate core OS tables.

## 2. Mapping Claude's hierarchy to the agency

| Agency OS concept | Claude execution mapping | Authority rule |
|---|---|---|
| Founder | Human principal and explicit OS Founder Authority | Never represented by a Claude agent |
| Chief of Staff | Claude coordinator agent | Proposes plans; cannot approve or grant access |
| Department head/supervisor | Predefined specialist coordinator | May coordinate only within its delegated task and roster |
| Specialist/employee | Predefined Claude specialist agent | Exact task, tools, data class and budget only |
| Subagent | Claude subagent thread | Child work must be attributable to parent OS execution |
| Parallel workstream | Dynamic workflow run | OS records parent execution and reconciles all child outcomes |
| Skill | Versioned procedure/instructions | Not an authorization grant |
| MCP server/tool | Approved integration transport | OS Tool Gateway remains policy authority for OS actions |
| Claude session/thread | Provider runtime record | OS stores provider IDs as correlated references, not source of truth |

The sixteen canonical Agency OS departments and their positions remain the organization model. Any radial/eight-cluster visualization is only a navigation view; it must not collapse departments, reporting lines or permission scopes.

## 3. Delegation lifecycle (required)

1. Founder or an authorized OS workflow creates a task with objective, acceptance criteria, workspace, data class, client authorization, deadline, budget and approval gates.
2. OS resolves the responsible workforce member, its Claude agent configuration/version, allowed specialist roster, tool grants and runtime eligibility.
3. OS persists an execution and reserves budget before provider calls. Unknown or exhausted budgets fail closed.
4. Claude decomposes work and delegates only within its pre-authorized roster/inline-agent policy. Provider-generated plans are proposals, not task assignments or authority.
5. Every child thread/run is correlated to a parent execution and persisted in an OS child-execution record before it can perform side effects. If the provider API cannot expose or reliably reconcile a child identity/outcome, that delegation mode stays disabled for side-effecting tasks.
6. Read-only analysis and artifact drafting may run autonomously within the approved data class and sandbox. External writes, outreach, client commitments, payments, contracts, production changes and destructive actions must call an OS tool that independently checks policy and consumes approval where required.
7. Tool calls pass through the shared OS Tool Gateway. Check active workforce member, exact tool/action/data-class/scope grant, workspace, session, DPG, budget, approval and idempotency on every invocation. Never trust prompt text, provider thread metadata or model-supplied IDs as authorization.
8. OS reconciles provider events with durable execution/attempt records. Handle duplicate/out-of-order events, unknown child threads, timeouts, cancellation, partial failures and provider retries idempotently.
9. Specialist output is an artifact/result attached to the OS task. A reviewer/QA agent may independently check it; OS records reviewer identity/config/version and evidence.
10. Founder approval is bound to exact artifact digest, target environment and release action. A changed artifact invalidates the approval.

## 4. Tool and MCP policy

- Prefer native Managed Agents custom tools when the OS worker can execute and persist callbacks through the shared Tool Gateway.
- Use MCP from Claude for external services or where the provider's MCP connector is the best supported transport. MCP is an adapter/protocol, not a second authorization system.
- An MCP server that can affect Agency OS data must call authenticated OS actions. It must not use direct database credentials or bypass DPG, workspace authorization, budgets, approvals, idempotency or audit.
- Give each specialist only the MCP servers/tools it needs. Do not assume inline agents can have narrower inherited MCP access; disable inline delegation when least-privilege cannot be proven.
- Do not enable arbitrary shell, broad filesystem access, unrestricted web fetch, or credentials in prompts. Sandbox egress and filesystem mounts must be constrained outside model instructions.
- Skills are instructions/context, never proof of user consent or permission.

## 5. Phased enablement

### Phase A — current safe baseline

Keep the current worker-mediated custom-tool path. Enable tool-free planning and bounded specialist reasoning. OS persists the root task, execution and founder-reviewed plan. No autonomous provider child actions.

### Phase B — read-only multiagent pilot

Add versioned Managed Agents agent definitions for research, analysis, architecture, QA/security review and documentation. Allow predefined agents and bounded dynamic workflows for synthetic/public data only. Disable inline agents initially. Persist provider session/thread/run correlation and reconcile completion. No write-capable MCP or OS mutation tools.

### Phase C — OS-correlated child executions

Add child execution records and provider event adapters. Prove every subagent/workflow child maps to a parent OS execution, budget reservation, data classification, cancellation and audit. Test duplicate/out-of-order events, missing child completion, lease expiry, partial failure and budget exhaustion.

### Phase D — narrowly scoped tools

Expose per-department Tool Gateway capabilities. Enable routine pre-authorized writes only where policy explicitly allows them. Sensitive actions remain approval-gated. Add MCP connectors after threat-model and credential review.

### Phase E — production release

Require provider compatibility tests, PostgreSQL isolation, sandbox/egress tests, budget/load tests, restore/reconciliation drills, evaluation harness pass and founder approval. Keep Managed Agents behind an adapter because it is beta and retain the self-managed Claude Agent SDK/other eligible runtime migration path.

## 6. Acceptance criteria before enabling multiagent in production

- Every provider child thread/run is linked to a durable parent and child OS execution; no orphan child work is accepted as complete.
- Per-child workspace, data class, tool grants, budget and timeout are enforced by the OS, not merely by Claude configuration.
- Provider event delivery is treated as at-least-once; idempotency, deduplication, ordering and reconciliation are tested.
- Parent cancellation reaches provider children and prevents new side effects; inability to cancel is surfaced as an incident requiring reconciliation.
- Child failures, partial outputs and costs are visible to the founder; no false parent success.
- No child can approve its own output or protected action.
- Cross-tenant tests cover APIs, tools, artifacts, sessions, cache, event callbacks and provider sandbox access.
- Evaluations verify correct delegation, non-delegation, data minimization, tool denial, stop conditions and cost ceilings.

## 7. Known provider constraints

Managed Agents is beta, not ZDR eligible and not HIPAA eligible. Provider subagents share the session sandbox/filesystem and vault credentials; separate thread context is not a security boundary. Predefined agents have their own configuration, but inline agents inherit the parent agent's tools/MCP/skills. Multiagent configuration and session budgets are copied at session creation; changing an Agent later does not retroactively change existing sessions. Provider-side child threads are limited (current docs specify up to 25 concurrent child threads per session), and every child consumes budget. Verify all details against the live API version before rollout.

## References

- https://platform.claude.com/docs/en/managed-agents/agent-setup
- https://platform.claude.com/docs/en/managed-agents/multiagent-orchestration
- https://platform.claude.com/docs/en/managed-agents/overview
- https://platform.claude.com/docs/en/managed-agents/tools
