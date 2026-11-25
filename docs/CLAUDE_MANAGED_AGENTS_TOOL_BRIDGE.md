# Claude Managed Agents — OS Tool Bridge Design

**Status:** Design decision only. No provider-side tools, MCP connection, session credential, or autonomous side effect is enabled by this document.

## 1. Objective

Connect Claude Managed Agents to the Agency OS through an OS-owned Model Context Protocol (MCP) endpoint. Claude may reason and request tools; the OS remains the sole authority for identity, workspace scope, data eligibility, tool grants, approvals, budgets, persistence and audit.

This is an internal operating capability, not a public SaaS integration.

## 2. Current baseline

The current main branch contains:

- Founder-issued machine identities with digest-only long-lived credentials, workspace scope and explicit scopes/data-class grants.
- Bounded machine sessions and worker-driven expiry.
- A code-owned, versioned Tool Registry and REST Tool Gateway.
- DPG-protected tool inputs/outputs, idempotent invocation records and success audit.
- Only two registered tools: `system.health.read` and `revenue.lead.research.capture`.
- A Claude Managed Agents adapter that deliberately rejects provider-side tools, MCP servers, skills and multiagent configuration.

The existing REST gateway is not yet an MCP server. The Claude adapter does not yet pass per-session vault credentials. This design closes those two gaps without relaxing the current boundary.

## 3. Trust boundaries

1. **Claude is an untrusted execution runtime.** Prompt instructions are not authorization.
2. **The OS MCP endpoint is a narrow adapter.** It exposes only tools registered and enabled by OS policy; it never exposes SQL, ORM models, arbitrary HTTP, shell, filesystem, or provider credentials.
3. **Every tool call is re-authorized.** Check active machine identity, exact session, workspace, data class, tool scope, tool version, action policy, budget and approval state on every invocation.
4. **The provider receives a session-bound bearer token, not the machine identity's reusable credential.** Persist only a digest in the OS. Deliver the raw token to the provider vault over TLS and never put it in prompts, logs, source control or tool results.
5. **Provider-side tools remain off by default.** Do not enable Bash, arbitrary file operations, general web search/fetch, provider skills or multiagent delegation as a side effect of enabling MCP.
6. **All business state remains OS-owned.** The provider's session history is not the system of record for tasks, CRM, approvals, costs or audit.

## 4. Proposed components and contracts

### 4.1 Session-scoped MCP credential

Add an OS-owned credential record linked by composite foreign key to one `AgentSession` and its `MachineIdentity` scope. Store:

- Credential ID, org ID, workspace ID, machine identity ID and session ID.
- SHA-256 token digest and non-secret display prefix.
- Created/expiry/revocation timestamps and credential version.

Issue a high-entropy, single-session token only after the OS session is persisted. The token must expire no later than the session or machine identity and be invalidated on session close, cancel, expiry, identity revocation or administrative revoke. Never store plaintext token.

The MCP request's bearer token determines the machine identity and exact session. The model must not supply or override the session ID as a tool argument.

### 4.2 MCP transport

Expose a dedicated HTTPS Streamable HTTP MCP endpoint (for example, `/mcp/agency-os`) on the OS API service. Use a maintained MCP SDK and pin a compatible version. Keep transport stateless unless the SDK requires protocol state; business/session state remains in PostgreSQL.

Authentication middleware must validate the session-bound token before dispatch. Tool handlers use the authenticated identity/session context and the same authorization service as the REST Tool Gateway. Do not duplicate or weaken policy checks in MCP-specific code.

The endpoint must enforce request size, timeouts, concurrency limits, JSON/schema validation, safe error responses, origin/host policy and rate limits. It must not accept arbitrary callback URLs or network destinations.

### 4.3 Tool exposure

The MCP `tools/list` result is the intersection of:

- Code-registered tools.
- The machine identity's explicit `tools:invoke` and `tool:<key>` scopes.
- The active session data class.
- The agent's OS capability grants and runtime policy.
- The current tool version and enabled state.

The MCP server returns only safe names, descriptions and JSON input schemas. Every `tools/call` repeats the authorization and DPG checks. A hidden tool is also rejected if called directly.

Initial rollout must expose only:
- `system.health.read` for a read-only smoke test.
- `revenue.lead.research.capture` for public-data research drafts, with its existing strict schema and founder-review boundary.

Do not expose CRM promotion, contacts, outreach dispatch, pricing, contracts, payments, production deployment, destructive operations or permission changes through this first bridge.

### 4.4 Idempotency and durable invocation

Reuse the OS Tool Registry and invocation service rather than creating a second execution path. MCP tool calls must create the same durable invocation and audit records as REST calls.

For the initial draft-capture tool, define a deterministic idempotency strategy that survives provider retries and does not collapse distinct intentional drafts. Same key plus same canonical sanitized request replays the stored result; same key plus a different request is a conflict. In-flight duplicates must not execute concurrently. Do not infer exactly-once delivery from MCP request IDs.

Keep external provider/network calls outside database transactions. The tool bridge itself must not perform external side effects.

### 4.5 Claude Managed Agents configuration

Anthropic's current Managed Agents MCP contract separates reusable agent configuration from per-session authentication:

- The saved Agent declares an MCP server by `type`, `name` and HTTPS `url`.
- A matching `mcp_toolset` references that server.
- Toolset configuration should set `default_config.enabled=false` and explicitly enable the approved bare tool names.
- Session creation attaches the session credential through a pre-registered vault ID (`vault_ids`); credentials are matched by MCP server URL.
- The MCP server URL and credential URL must match exactly after documented URL normalization.

The adapter must not create a new provider Agent on every execution. Maintain a versioned, OS-controlled provider Agent configuration and verify its actual tools/MCP configuration before use. Do not silently accept drift in provider-side configuration.

The OS must create or select a vault, register the session-bound static bearer credential, and attach the vault to the provider session. Persist provider vault/credential IDs as external references only; never persist or log the raw bearer token. Define bounded cleanup and reconciliation for vault credentials and provider sessions after success, failure, timeout, cancellation and worker crash.

### 4.6 Runtime lifecycle

Required sequence:

1. Claim the OS execution and persist an active `AgentSession` with exact identity, workspace, purpose, data class and expiry.
2. Issue a session-bound MCP token; persist only its digest.
3. Create/register the provider vault credential for the exact MCP endpoint.
4. Create/resume the Managed Agent session with the vault reference and approved budget.
5. Persist provider session ID before any subsequent polling or event processing.
6. On each MCP call, authenticate and authorize against current OS state.
7. Persist tool invocation, sanitized result and audit before returning success to Claude.
8. Reconcile provider session status and all tool invocations before marking the OS execution complete.
9. Revoke the OS session token and clean up provider vault/credential/session according to retention policy.
10. If the worker crashes or the provider result is unknown, recover by persisted provider IDs and reconciliation; do not blindly create a replacement session or replay a write.

A timeout or lost response is an unknown outcome until reconciled. Provider session completion alone does not prove that every OS tool invocation was persisted successfully.

## 5. Approval, budget and data policy

- The MCP bridge cannot approve actions. Founder approval remains an OS-owned, single-use authorization consumed atomically with the protected action.
- Tool risk levels and approval metadata are enforced by the OS gateway, not trusted from provider tool descriptions.
- Per-session and per-tool budgets must be checked before invocation and recorded with actual usage where measurable.
- The first integration remains public/synthetic-only. Commercial data requires client authorization and runtime eligibility. Confidential and regulated data remain ineligible for Managed Agents under the current product restrictions.
- Agent-generated source content and tool arguments are untrusted. Apply DPG before validation and persistence, and sanitize provider output before returning it to the runtime.
- No secrets, full credentials, raw client payloads or unnecessary PII in logs, audit metadata or prompts.

## 6. Failure handling and observability

Persist and monitor:
- OS execution ID, machine identity ID, OS session ID, provider session ID, provider vault/credential references, correlation ID and tool invocation IDs.
- Provider status, MCP connection/auth errors, tool error code, attempt count, elapsed time, budget/cost and cleanup state.
- Retry classification, lease/heartbeat, cancellation, dead-letter and reconciliation outcome.

Use bounded retries with backoff for transient failures only. Authentication, policy, schema and data-protection failures are non-retryable until corrected. A provider session that reports an MCP connection/auth error must not be marked as successful merely because its text turn reached `end_turn`.

## 7. Required tests before enabling

### Unit and contract tests
- Session token is high entropy, digest-only, constant-time verified, session-bound, expiring and revocable.
- Wrong identity, workspace, session, data class, scope, tool version or disabled tool is rejected.
- MCP tool list is filtered and direct invocation of hidden tools is denied.
- DPG blocks secrets and redacts PII before schema validation/persistence.
- Invalid schemas, oversized inputs/outputs and malicious/untrusted tool results fail closed.
- Idempotent replay, same-key/different-payload conflict and concurrent duplicate calls.
- MCP errors never reveal tokens, provider secrets, SQL or internal exception strings.

### Integration and recovery tests
- Managed Agent session receives only the correct vault credential for its OS session.
- MCP server authentication failure and connection failure are detected from provider events and block success.
- Tool invocation persists before success is returned to Claude.
- Session expiry/revocation invalidates MCP calls immediately.
- Worker crash after vault creation, provider session creation, tool execution and provider completion is reconciled without duplicate writes.
- Provider vault/credential cleanup is retried and audited.
- Cross-workspace isolation across MCP calls, API routes, sessions and invocation records.
- PostgreSQL 16 migration/locking tests, not SQLite-only evidence.

### Release gate
Do not enable the MCP endpoint for Managed Agents until the above tests pass, the provider Agent definition is reviewed/version-pinned, the public HTTPS endpoint and network policy are configured, secret handling and cleanup are demonstrated, and a founder-approved synthetic pilot is completed. Keep the current no-provider-tools behavior until then.

## 8. Implementation sequence

1. Add session-bound token model, migration, issuance/revocation and tests.
2. Add maintained MCP SDK and stateless Streamable HTTP server with authenticated request context.
3. Refactor REST and MCP invocation through one shared gateway service; preserve existing REST behavior.
4. Add MCP transport/schema/authorization/idempotency/isolation tests.
5. Add provider vault and credential lifecycle adapter with secret-safe tests.
6. Add a versioned Claude Agent MCP configuration with explicit tool allowlist and configuration-drift checks.
7. Integrate vault references and MCP error-event handling into Managed Agents runtime.
8. Add crash recovery, cleanup reconciliation, metrics and founder monitoring.
9. Run PostgreSQL 16 migration/integration tests and a synthetic end-to-end pilot.
10. Enable only the first two low-risk tools after founder review; expand capabilities one tool at a time.

## 9. References

- [Claude Managed Agents MCP connector](https://platform.claude.com/docs/en/managed-agents/mcp-connector)
- [Claude Managed Agents vaults](https://platform.claude.com/docs/en/managed-agents/vaults)
- [Create a vault credential API](https://platform.claude.com/docs/en/api/http/beta/vaults/credentials/create)
- [Claude Managed Agents overview and data handling](https://platform.claude.com/docs/en/managed-agents/overview)

**Important:** Managed Agents is beta and is not eligible for Zero Data Retention or HIPAA BAA under the current documentation. Do not claim compliance or use ineligible data classes.
