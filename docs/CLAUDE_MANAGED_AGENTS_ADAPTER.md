# Claude Managed Agents adapter — initial controlled integration

## Current API contract

The adapter targets Anthropic's Managed Agents beta API:
- API version: `2026-10-21`
- Beta header: `managed-agents-2026-04-01`
- Session creation: `POST /v1/sessions`
- Session status: `GET /v1/sessions/{session_id}`
- Event history: `GET /v1/sessions/{session_id}/events`

Anthropic documents Managed Agents as beta and explicitly marks it **not ZDR eligible and not HIPAA eligible**. Do not use it for regulated/confidential workloads. The current OS policy permits only synthetic data in the execution service; commercial, confidential and regulated workloads remain blocked until separately reviewed and authorized.

## What this first adapter does

- Requires an explicit enable flag, API key, Managed Agent ID and environment ID.
- Uses the local Agent's instructions/department and the persisted OS Task as the session context.
- Sets a hard USD session budget (default 250 cents).
- Clears inherited tools, MCP servers and skills for this initial integration. It can reason and return a completion report, but it cannot call external tools or mutate OS/business state.
- Persists the Managed Agents session ID to the current execution attempt as soon as the create response is received. Retries reuse the most recently persisted session ID instead of blindly creating a new session.
- Polls session state while the existing worker heartbeat maintains the OS execution lease.
- Treats `requires_action` and budget pauses as manual review. It never auto-confirms provider tool calls.
- Stores only bounded completion text and the external session ID in execution records.

## External configuration

Set these in the private `.env` file or a secrets manager. Never commit real values.

- `CLAUDE_MANAGED_AGENTS_ENABLED=true`
- `ANTHROPIC_API_KEY`
- `CLAUDE_MANAGED_AGENT_ID`
- `CLAUDE_MANAGED_ENVIRONMENT_ID`

Optional controls:
- `CLAUDE_MANAGED_SESSION_BUDGET_CENTS=250`
- `CLAUDE_MANAGED_TIMEOUT_SECONDS=900`
- `CLAUDE_MANAGED_POLL_INTERVAL_SECONDS=2`

The base agent and environment must already exist in the Anthropic Console. Use an environment with the minimum required capabilities. This first adapter intentionally overrides tools/MCP/skills to empty lists.

## Reliability caveat

The OS persists the provider session ID immediately after a successful create response and resumes it on later attempts. If the network fails after Anthropic creates a session but before the API response containing its ID reaches the OS, the OS cannot yet reconcile that ambiguous create. Do not enable this adapter for unattended production use until provider-side idempotency/reconciliation is verified for the account/API version.

## Next controlled increment

Add a narrowly scoped Agency OS MCP server for explicitly allowlisted read/write actions. The OS must authorize every tool call using the caller's tenant/workspace scope, autonomy classification, budgets, consent and approval records. Protected actions must remain founder-gated. Never rely on the provider agent prompt as the security boundary.
