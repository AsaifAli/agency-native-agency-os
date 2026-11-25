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
- Before creating or resuming a session, retrieves the provider Agent and fails closed if it is archived, has built-in toolsets, MCP servers, provider skills or multiagent features configured. Exact OS-registered custom tools are the only permitted provider tools. Their callbacks are executed by the OS worker and authorized by the shared Tool Gateway.
- Sends the pre-created Agent ID, environment, bounded budget, metadata and initial task event.
- Uses the OS Agent instructions/department and persisted OS Task as task-specific context.
- Persists the session ID to the active execution attempt after a successful create response; subsequent attempts reuse the saved session ID.
- Polls session state while worker heartbeat maintains the OS execution lease.
- Paginates event history and tracks `workflow_run.created` / `workflow_run.status_ended`. An idle session is not treated as complete while a workflow run remains open. Success requires no open workflow runs and a final `session.status_idle` with `stop_reason.type=end_turn`.
- Routes tool-confirmation, budget, refusal, retry-exhaustion and other non-completion pauses to manual review; it never auto-confirms actions.
- Stores bounded completion text and external session ID in OS execution records.

## Critical tool configuration boundary

The session request references a pre-created Agent. The adapter inspects that Agent before every new or resumed execution attempt. It rejects built-in toolsets, unknown custom tools, schema drift, MCP servers, skills and enabled multiagent features.

The only permitted provider tools are exact custom-tool definitions generated from the OS Tool Registry. The model emits an `agent.custom_tool_use` event; the worker executes the corresponding in-process OS adapter and returns a `user.custom_tool_result`. The worker processes custom-tool events while the provider session is running, not only after it becomes idle.

Every invocation is re-authorized by the OS:
- The current execution must still be running and match the agent/workspace/data class.
- The current worker attempt must still be running, owned by the same worker and hold a live lease.
- The agent's machine identity must be active, unexpired and scoped to the same organization/workspace.
- The machine identity must grant `sessions:create`, `tools:invoke`, the exact `tool:<key>` scope and the requested data class.
- The OS session must be active and bounded by the machine identity expiry.
- Input/output pass through the Data Protection Gateway and versioned Pydantic schemas.
- Tool invocation, result, idempotency and audit are persisted by the OS. Provider event IDs are namespaced by OS execution ID.
- At most 10 pending calls are processed per poll and 50 calls per execution; each provider result is bounded to 16 KB.

The provider receives only the tool result or a generic error. Raw exceptions, credentials and internal authorization details are not returned to the model. A tool that requires an approval adapter is not exposed to Managed Agents.

The initial adapter intentionally disables native provider tools, MCP servers, skills and multiagent workflows. This is a safe baseline, not the target capability ceiling. See `docs/CLAUDE_DELEGATION_AND_OS_CONTROL_BOUNDARY.md` for the phased plan to enable Claude predefined specialists, subagents, dynamic workflows, skills and MCP while preserving OS-owned tasks, permissions, budgets, approvals and audit. Do not enable provider-side child execution until child-thread correlation, per-child budgets, cancellation and reconciliation are implemented and tested.

The worker uses the OS database identity directly; it does not place a machine token or provider secret in prompts or provider event content. Prompts are not the security boundary. Explicit policy denials return a generic tool error to the agent; unexpected gateway/database failures propagate to the worker retry path instead of being presented as a successful tool response.

The current registry does **not** expose web search, web fetch, arbitrary URL retrieval, contact enrichment or prospect discovery. The lead-research capture tool stores source references supplied by the agent; those references are not independently verified by this adapter. Autonomous source discovery and source verification remain a separate milestone.

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

For an Agent that will use OS tools, configure only the exact custom-tool definitions produced by `managed_agent_custom_tool_definitions()`. The adapter compares provider-side names, descriptions and JSON schemas to the code-owned registry on every attempt. A mismatch blocks execution. Do not add built-in toolsets, MCP servers, skills or multiagent settings.

Provision a founder-approved machine identity for the agent in the intended workspace. For public research capture, the required scopes are `sessions:create`, `tools:invoke` and `tool:revenue.lead.research.capture`, with `public` as the only allowed data class. Never copy the machine credential into a prompt; the worker resolves the active identity from OS state.

## Reliability caveat

If Anthropic creates a session but the response containing its ID is lost before the OS receives it, the OS cannot currently reconcile that ambiguous create. Do not enable unattended production execution until provider-side idempotency/reconciliation or webhook-based recovery is implemented and tested. A persisted session ID supports resume, but it does not solve the ambiguous-create window.

## Validation status

Mock adapter tests cover provider Agent inspection, tool isolation rejection, request shape, session persistence/resume, workflow-run completion, manual-review pauses, transient errors and data eligibility. CI does not prove live provider compatibility, actual provider Agent/Environment settings, live sandbox isolation or production suitability.


## OS custom-tool integration status — 2026-11-25

The worker now connects Managed Agents custom-tool events to the OS-owned Tool Gateway. The HTTP machine-tool route and the worker callback share the same invocation service, so they use the same authorization, data protection, idempotency, persistence and audit rules.

This is a controlled initial integration, not full autonomy. The current registry contains a read-only health check and public lead-research draft capture. The latter creates a pending founder-review draft only; it does not create contacts, promote CRM records or send outreach. Machine identity provisioning and provider-side custom-tool configuration remain explicit setup steps. No live Anthropic call, provider provisioning, native subagent execution or production rollout is claimed.
