# Claude Managed Agents adapter — initial controlled integration

## Current API contract
The adapter currently targets the Managed Agents beta API configured in settings:
- API version: `2026-10-21`
- Beta header: `managed-agents-2026-04-01`
- Session creation: `POST /v1/sessions`
- Session status: `GET /v1/sessions/{session_id}`
- Event history: `GET /v1/sessions/{session_id}/events`

Verify the current Anthropic API contract and account beta access before live use. API version/header values are configuration and must be updated only after provider documentation and adapter tests are checked.

Managed Agents is beta and is not ZDR or HIPAA BAA eligible. The OS policy is synthetic-first. Do not send confidential, regulated or other ineligible client data.

## What the adapter does
- Requires an explicit enable flag, API key, pre-created Managed Agent ID and environment ID.
- Sends the pre-created Agent ID, environment, budget, metadata and initial task event.
- Uses local Agent instructions/department and persisted OS Task as task-specific context.
- Persists the session ID to the active execution attempt after a successful create response; subsequent attempts reuse the saved session ID.
- Polls session state while worker heartbeat maintains the OS execution lease.
- Routes action-required and budget pauses to manual review; it never auto-confirms actions.
- Stores bounded completion text and external session ID in OS execution records.

## Critical tool configuration boundary
The session request references a pre-created Agent. **That Agent's configured model, tools, MCP servers and skills remain authoritative.** The adapter does not prove or enforce that those capabilities are empty. It does not send session-level tool overrides in this implementation.

Before enabling this adapter, inspect the exact Agent and Environment in Anthropic Console/API. For the current initial slice, configure the Agent with no external tools, no MCP servers and no skills that can cause side effects; use the minimum environment permissions and egress. If this cannot be verified, leave `CLAUDE_MANAGED_AGENTS_ENABLED=false`. Do not infer tool-free execution from the absence of tool fields in the session request.

Any future Agency OS MCP tools must be authenticated and scoped by the OS backend on every call. The backend must enforce tenant/workspace scope, autonomy policy, budgets, data eligibility and founder approvals. Prompts are not the security boundary.

## External configuration
Set in private `.env` or a secrets manager; never commit values:
- `CLAUDE_MANAGED_AGENTS_ENABLED=true`
- `ANTHROPIC_API_KEY`
- `CLAUDE_MANAGED_AGENT_ID`
- `CLAUDE_MANAGED_ENVIRONMENT_ID`

Optional controls:
- `CLAUDE_MANAGED_SESSION_BUDGET_CENTS=250`
- `CLAUDE_MANAGED_TIMEOUT_SECONDS=900`
- `CLAUDE_MANAGED_POLL_INTERVAL_SECONDS=2`

The Agent and Environment must already exist. The current implementation has no live provisioning workflow.

## Reliability caveat
If Anthropic creates a session but the response containing its ID is lost before the OS receives it, the OS cannot currently reconcile that ambiguous create. Do not enable unattended production execution until provider-side idempotency/reconciliation or webhook-based recovery is implemented and tested. A persisted session ID supports resume, but it does not solve the ambiguous-create window.

## Validation status
Mock adapter tests cover request shape, session persistence/resume, manual-review pauses, transient errors and data eligibility. CI does not prove live provider compatibility, actual Agent configuration, live tool isolation or production suitability.
