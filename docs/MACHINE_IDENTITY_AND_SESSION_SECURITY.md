# Machine Identity and Session Security

## Scope
This increment establishes scoped machine credentials, durable execution sessions and the initial OS Tool Gateway. It now supports two code-registered tools through the Claude Managed Agents custom-tool event bridge; it does not enable provider-side MCP, built-in toolsets, client-data access or external side effects.

## Identity contract
- A machine identity belongs to exactly one organization and workspace.
- Subject types are agent, worker or service. Agent identities must reference an enabled agent in the same workspace.
- Only an explicitly authorized founder can issue or revoke identities.
- Credentials are high-entropy random bearer secrets. Only SHA-256 digests are stored; raw credentials are returned once at issuance.
- Identity grants contain explicit scopes and allowed data classes. Only synthetic and public data grants are currently enabled.
- Credentials expire within 90 days and can be revoked. Revocation cancels all active sessions in the same transaction.
- Never place the raw credential in prompts, logs, audit payloads, source control or browser storage. Provision it through a secret manager.

## Session contract
- A machine identity can create a session only with sessions:create.
- Session organization/workspace/identity are derived from the authenticated identity, never caller-supplied.
- Session lifetime is bounded to 60 seconds through 24 hours and cannot outlive the identity.
- Sessions persist purpose, data class, status and lifecycle timestamps. The worker maintenance loop expires due sessions in bounded, row-locked batches and writes an audit event for each expiry.
- Tool authorization requires the exact active session, matching scope, identity, workspace and data class.
- authorize_tool_session is an authorization primitive only. It does not invoke a tool. Tool invocation, input/output DPG, approval checks, budgets, adapter sandboxing and invocation audit are follow-on gateway work.

## API
- POST /v1/orgs/{org_id}/machine-identities — founder-only, creates identity and returns its secret once.
- POST /v1/orgs/{org_id}/machine-identities/{identity_id}/revoke — founder-only, revokes identity and cancels active sessions.
- POST /v1/machine/sessions — machine bearer credential required; creates a session within its fixed scope.

## Release limitations
- Do not issue production machine credentials until PostgreSQL migration verification, secret-manager configuration, token rotation procedures, retention/deletion and artifact cleanup policies, recovery tests and end-to-end authorization tests are complete.
- No agent tool grants are enabled by default. The current scope strings are authorization vocabulary for a future gateway.
- This work does not assert compliance or production readiness.


## Execution-bound tool sessions — PR #38 candidate

- Each Managed Agents execution lazily creates or reuses one scoped `AgentSession` on its first custom-tool event.
- `Execution.machine_session_id` persists the session association with composite org/workspace/session foreign-key enforcement and uniqueness so sessions are not shared between executions.
- Session creation audit is emitted by the shared `create_agent_session` service, including worker-created sessions; HTTP and worker paths cannot bypass the lifecycle audit.
- Provider event IDs are hashed into stable invocation idempotency keys. A worker restart after OS commit but before provider result delivery replays the existing invocation.
- Session cleanup must detach or expire execution references before any future physical session deletion because the execution/session FK is restrictive.


## Managed Agents custom tool bridge — 2026-11-25 (PR #38 candidate)

- [x] Extracted a shared in-process `invoke_registered_tool` service used by HTTP and provider custom-tool callbacks.
- [x] Added exact provider-safe custom tool names and JSON schemas generated from the OS Tool Registry.
- [x] Managed Agents validates provider Agent tools against the OS registry on create and resume; unknown tools, schema drift, built-in toolsets, MCP servers, skills and multiagent features are rejected.
- [x] Handles `agent.custom_tool_use` events while sessions are running/idle and sends `user.custom_tool_result` events only after the OS service completes.
- [x] Waits for the provider session to resume after custom-tool results; built-in permission-gated actions are not auto-confirmed.
- [x] Worker lazily creates/reuses an agent machine session, persists it on `Execution.machine_session_id`, and calls the OS gateway with exact agent/org/workspace scope.
- [x] Provider event IDs map to deterministic idempotency keys; tool results are committed before being returned to the provider.
- [x] Centralized session creation audit covers worker and HTTP creation paths; tool denials persist safe reason-code audit events after rollback.
- [x] DPG now preserves only explicitly trusted OS-generated identifier fields in tool output; arbitrary/untrusted payload strings remain PII-scanned.
- [x] Migration `q7f2b9d4c631` adds the composite scoped execution-to-session link and one-session-per-execution uniqueness.
- [x] Independent isolated-candidate validation: **236 focused tests passed** across 16 modules, Python compile check passed, and SQLite migration upgrade/downgrade/re-upgrade through `q7f2b9d4c631` passed.
- [ ] PostgreSQL 16 verification and full backend suite on exact PR #38 head remain pending. A previous full-suite attempt in the isolated candidate timed out; no full-suite pass is claimed.
- [ ] Provider Agent external configuration, machine identity issuance for each agent, real API credential setup and synthetic live end-to-end test remain external/release steps.
- [ ] Built-in web search/fetch, MCP, skills, multiagent, budgets and tools with approvals remain disabled. The research capture tool stores supplied references; it does not independently browse or verify them.
- [ ] Session retention/deletion and physical cleanup remain outstanding; the new restrictive FK requires safe detachment/reconciliation before deletion.
