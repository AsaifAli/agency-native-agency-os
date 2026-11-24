# Claude Managed Agents adapter — controlled initial integration

## Verified provider contract

The adapter is configured for the current Managed Agents beta contract:
- API version: `2026-10-21`
- Required beta header: `managed-agents-2026-04-01`
- Provider Agent inspection: `GET /v1/agents/{agent_id}`
- Session creation: `POST /v1/sessions`
- Session status: `GET /v1/sessions/{session_id}`
- Session event history: `GET /v1/sessions/{session_id}/events`

Official provider references:
- https://platform.claude.com/docs/en/managed-agents/overview
- https://platform.claude.com/docs/en/managed-agents/sessions
- https://platform.claude.com/docs/en/managed-agents/workflow-runs
- https://platform.claude.com/docs/en/api/http/beta/agents/retrieve
- https://platform.claude.com/docs/en/api/beta/sessions/create

Managed Agents is beta and is not Zero Data Retention or HIPAA BAA eligible. The OS policy is synthetic-first. Do not send confidential, regulated or other ineligible client data.

## What the adapter does

- Requires an explicit enable flag, API key, pre-created Managed Agent ID and environment ID.
- Before creating a new session, retrieves the provider Agent and fails closed if it is archived, has tools, MCP servers, skills or multiagent features configured. This is a temporary safety gate until the OS MCP gateway and authorization enforcement are implemented.
- Sends the pre-created Agent ID, environment, bounded budget, metadata and initial task event.
- Uses the OS Agent instructions/department and persisted OS Task as task-specific context.
- Persists the session ID to the active execution attempt after a successful create response; subsequent attempts reuse the saved session ID.
- Polls session state while worker heartbeat maintains the OS execution lease.
- Paginates event history and tracks `workflow_run.created` / `workflow_run.status_ended`. An idle session is not treated as complete while a workflow run remains open. Success requires no open workflow runs and a final `session.status_idle` with `stop_reason.type=end_turn`.
- Routes tool-confirmation, budget, refusal, retry-exhaustion and other non-completion pauses to manual review; it never auto-confirms actions.
- Stores bounded completion text and external session ID in OS execution records.

## Critical tool configuration boundary

The session request references a pre-created Agent. That Agent's configured model, tools, MCP servers, skills and multiagent configuration are provider-side resources. The adapter now inspects the Agent before creating a new session and rejects non-empty tools, MCP servers or skills and any enabled multiagent configuration.

This gate intentionally prevents native provider subagents/workflows until the OS has a controlled tool gateway and a reliable way to reconcile every provider child action into OS-owned tasks, permissions, budgets and audit records. Do not bypass this check by changing provider configuration or prompts.

Any future Agency OS MCP tools must be authenticated and scoped by the OS backend on every call. The backend must enforce tenant/workspace scope, member identity, autonomy policy, budgets, data eligibility and founder approvals. Prompts are not the security boundary.

## External configuration

Set in private `.env` or a secrets manager; never commit values:
- `CLAUDE_MANAGED_AGENTS_ENABLED=true`
- `ANTHROPIC_API_KEY`
- `CLAUDE_MANAGED_AGENT_ID`
- `CLAUDE_MANAGED_ENVIRONMENT_ID`

Optional controls:
- `CLAUDE_MANAGED_SESSION_BUDGET_CENTS=250` (USD cents; 250 = USD 2.50)
- `CLAUDE_MANAGED_TIMEOUT_SECONDS=900`
- `CLAUDE_MANAGED_POLL_INTERVAL_SECONDS=2`

The Agent and Environment must already exist. The current implementation has no live provider provisioning workflow. Provider-side configuration must be reviewed and approved before setting the enable flag.

## Reliability caveat

If Anthropic creates a session but the response containing its ID is lost before the OS receives it, the OS cannot currently reconcile that ambiguous create. Do not enable unattended production execution until provider-side idempotency/reconciliation or webhook-based recovery is implemented and tested. A persisted session ID supports resume, but it does not solve the ambiguous-create window.

## Validation status

Mock adapter tests cover provider Agent inspection, tool isolation rejection, request shape, session persistence/resume, workflow-run completion, manual-review pauses, transient errors and data eligibility. CI does not prove live provider compatibility, actual provider Agent/Environment settings, live sandbox isolation or production suitability.
