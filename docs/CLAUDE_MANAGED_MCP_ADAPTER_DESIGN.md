# Claude Managed Agents MCP Adapter — Design and Acceptance Contract

**Status:** Compatibility design only; disabled by default and not part of the active Managed Agents tool path. The active path is the native execution-bound custom-tool callback into the OS Tool Gateway. Do not enable both transports. Live Anthropic provider validation and external configuration remain pending.
**Owner:** Claude runtime adapter, with the OS Tool Gateway as the only authorization and execution authority.  
**Initial data policy:** synthetic/public only. No local model, local inference or local fallback.

## 1. Architectural boundary

This document records a provider-native MCP compatibility option. It is not the active Managed Agents integration path. The active path uses `agent.custom_tool_use` callbacks; Cowork and Claude Code use the shared Agency MCP gateway. Do not enable both Managed Agents tool transports. This compatibility option still converges on the same Tool Gateway and is not a second tool registry.

- The Claude adapter owns provider-specific Agent/session configuration, MCP server registration, Anthropic Vault credentials, session lifecycle and provider event handling.
- The OS owns machine identity, AgentSession, session credentials, workspace scope, RBAC/ABAC, workforce grants, data-class eligibility, approvals, idempotency, tool execution, persisted results and audit.
- Every MCP invocation must call the existing `app.tool_gateway.invoke_registered_tool`. Do not duplicate policy checks in the MCP server or create a second tool registry.
- The MCP endpoint is a transport façade over the Tool Gateway. It cannot access core business tables directly.
- The transport permits only explicitly allowlisted `read_only` or `write_draft` tools. Draft tools must stop at a persisted review state; tools requiring approval or external side effects remain unavailable until an approval adapter can consume the approval and protected action atomically.

## 2. Provider contract and constraints

Claude Managed Agents supports remote MCP servers over Streamable HTTP. Agent configuration declares the MCP server and matching `mcp_toolset`; session creation supplies authentication through an Anthropic Vault. Credentials are matched to the declared MCP URL. The adapter must use the exact same session-specific URL in the vault credential and session override.

Relevant provider constraints:

- Create the Vault credential as `static_bearer`, bound to the exact MCP server URL.
- Attach `vault_ids` when creating the Managed Agents session. The current Update Session API marks `vault_ids` as not yet supported, so credentials cannot be attached after session creation.
- Use a session-local `agent_with_overrides` configuration to supply the MCP server URL and MCP toolset without mutating the reusable Agent definition.
- With limited networking, the MCP host must be explicitly included in the Managed Agents environment's allowed hosts. Do not enable unrestricted MCP networking.
- The current provider API does not document an idempotency key for Vault credential creation or session creation. Ambiguous outcomes must stop for reconciliation, not blindly retry.

References:
- [Managed Agents MCP connector](https://platform.claude.com/docs/en/managed-agents/mcp-connector)
- [Authenticate with Vaults](https://platform.claude.com/docs/en/managed-agents/vaults)
- [Create Vault credential](https://platform.claude.com/docs/en/api/beta/vaults/credentials/create)
- [Create Session](https://platform.claude.com/docs/en/api/beta/sessions/create)
- [Update Session](https://platform.claude.com/docs/en/api/beta/sessions/update)
- [Session operations](https://platform.claude.com/docs/en/managed-agents/session-operations)

## 3. Session-scoped authentication

A long-lived MachineIdentity bearer token alone is insufficient for MCP because each provider session must map to exactly one OS AgentSession. Use a short-lived, session-scoped bearer credential.

1. The worker, under its live execution capability, creates an OS AgentSession bound to the execution's exact org, workspace, agent MachineIdentity and allowed data class.
2. The OS generates a high-entropy session token. Only its SHA-256 digest and non-secret display prefix are stored. The raw token exists only in worker memory until it is sent over TLS to the Anthropic Vault API; it must never enter prompts, logs, traces, audit payloads or source control.
3. The credential is bound to the AgentSession and expires no later than the AgentSession or MachineIdentity. Revocation/expiry of either parent makes the credential unusable.
4. The public MCP URL is session-specific, for example `https://<configured-host>/v1/integrations/agency/mcp/sessions/<agent_session_id>`. The path identifies the OS session; the bearer token authenticates it. The path is not a secret.
5. The MCP authentication boundary validates the path session ID and bearer digest together, then establishes the exact org/workspace/machine identity context before loading any tenant data.
6. The credential lookup must use a narrowly scoped SECURITY DEFINER function that returns only minimal session context. The app role must not receive direct SELECT access to the credential table. Worker writes must be bound to the current execution capability and that execution's agent.
7. Store provider Vault credential ID and provider session ID as non-secret external references on OS-owned session/execution records. Never store the raw bearer token.

The credential table must have forced workspace RLS. Worker visibility is additionally restricted to the exact live execution ID; a worker must not enumerate other session credentials in the workspace.

## 4. Session creation and provider lifecycle

1. Validate the pre-created Managed Agents Agent. Reject unexpected built-in toolsets, skills, multiagent configuration, unapproved MCP servers and arbitrary tool overrides.
2. Create the OS AgentSession and its one-time credential hash in a committed transaction.
3. Create an Anthropic Vault credential using `static_bearer`, the raw session token, the session-specific MCP URL, and non-secret metadata containing the OS AgentSession and execution IDs.
4. Persist the returned Vault credential ID before creating the provider session. If credential creation has an ambiguous result, list credentials in the configured Vault and reconcile by exact metadata and URL. Zero or multiple matches must stop for manual review; never create another credential blindly.
5. Create the Managed Agents session with:
   - the configured Agent ID through `agent_with_overrides`;
   - one session-specific MCP server URL;
   - one matching `mcp_toolset`;
   - the configured Vault ID in `vault_ids`;
   - the existing bounded session budget and initial task event.
6. Persist the provider session ID before reporting the execution as started. If the response is ambiguous or persistence fails, mark the execution non-retryable for manual reconciliation. Do not create a second provider session.
7. On successful completion, cancellation, expiry or identity revocation, revoke the OS session credential first. Archive the corresponding provider Vault credential as cleanup; if archive fails, the OS-side revocation still prevents further tool calls and a cleanup task must be recorded.
8. A provider `session.error` for MCP connection/authentication failure must be surfaced as a typed runtime error and stop tool use until the credential/network configuration is repaired.

External calls occur outside database transactions. Persist intent and references around each external effect; use bounded retries only when the provider outcome is known. All cleanup and reconciliation must be idempotent.

## 5. MCP transport and Tool Gateway contract

- Use the official Python MCP SDK 2.x Streamable HTTP transport, mounted into the existing FastAPI process. The tested 2.3.0 SDK serves modern MCP 2026-07-28 and legacy MCP 2025-11-25 on the same endpoint. Do not add a separate service or Cloudflare Worker MCP implementation unless operational evidence requires it.
- Use the 2026-07-28 stateless request/response protocol and `stateless_http=True`; do not depend on MCP `initialize` or `Mcp-Session-Id` for modern clients. Legacy clients retain compatibility.
- The `{agent_session_id}` path is an explicit Agency OS application-session handle, not an MCP transport session. The OS `AgentSession`, MachineIdentity, credential digest, workspace and execution remain durable and are revalidated on every request. Stateless transport does not remove OS state, authorization, idempotency or audit.
- Apply exact Host and Origin allowlists, DNS-rebinding protection, HTTPS-only public URL validation, bounded request bodies, timeouts and concurrency limits.
- Tool discovery returns only tools that are simultaneously:
  - registered and enabled by OS configuration;
  - explicitly scoped to the MachineIdentity;
  - allowed by the active workforce member and capability grant for this tool/action/scope;
  - allowed for the AgentSession data class;
  - registered as `read_only` or `write_draft` and not approval-gated.
- Discovery is advisory. Invocation rechecks all authorization under the existing Tool Gateway's database locks and persists the ToolInvocation plus audit event.
- Derive the MCP idempotency key from the stable AgentSession ID, MCP request ID and tool key. Reuse of a key with a different request hash must fail closed.
- Return generic policy-denial text to the provider. Do not disclose tenant existence, internal IDs, database errors, credentials or policy implementation details.

## 6. Data protection and tenant isolation

- MachineIdentity and AgentSession allowed data classes are authoritative; MCP configuration cannot widen them.
- Initial eligibility is synthetic/public only. Commercial, confidential and regulated data remain denied until a separately reviewed runtime eligibility policy and provider contract permit them.
- Apply the Data Protection Gateway to every tool input and output using the existing Tool Gateway path.
- The session credential must be scoped to one AgentSession and one workspace. Interactive `service` identities are provisioned by the founder and use exact machine scopes; `agent` identities additionally require workforce grants. Wrong path, wrong token, expired/revoked session, revoked MachineIdentity, mismatched workspace or missing grant must all be denied.
- No arbitrary MCP URLs, caller-selected tools, user-controlled headers, custom network targets or provider-supplied tool permissions are trusted.
- No direct MCP access to PostgreSQL models, filesystem, object storage, provider secrets or worker internals.

## 7. Required tests before enabling

### Database and credential boundary
- Migration graph and full PostgreSQL 16 upgrade.
- Actual `agency_os_worker` login can create a session credential only for its current execution and exact agent/workspace.
- Worker cannot read another execution's credential hash; app role cannot SELECT the credential table.
- Credential lookup function rejects wrong token, wrong session path, wrong workspace, expired/revoked credential, inactive AgentSession and revoked/expired MachineIdentity.
- Revocation takes effect immediately; expiry and retention cleanup remove/revoke dependent credentials safely.

### MCP transport and Tool Gateway
- Host/Origin rejection, DNS-rebinding protection, request size limit, invalid bearer, malformed JSON-RPC and unsupported methods.
- Tool discovery filters data class, identity scope, workforce grants, tool risk and approval requirement.
- Invocation rechecks authorization; cross-workspace and cross-agent attempts fail.
- Duplicate request replays the persisted result; same idempotency key with changed arguments conflicts.
- Concurrency and per-session call limit are enforced by OS-owned state.

### Managed Agents provider adapter
- Mock Vault credential create/list/archive and Managed Agents session create/retrieve.
- Exact URL equality between MCP server declaration and Vault credential.
- `vault_ids` attached at session creation; no unsupported post-create vault update.
- Only approved `agent_with_overrides` fields are sent.
- Raw token is absent from logs, prompts, traces, audit and persisted OS rows.
- Ambiguous Vault credential or provider session creation never triggers blind duplicate creation.
- MCP connection/authentication errors stop the run and leave a recoverable, audited state.
- Session completion/revocation disables the OS token even if provider-side credential archival fails.

## 8. Explicitly out of scope for the first release

- Local AI, local inference, local fallback or local MCP subprocesses.
- Stdio and legacy SSE transports.
- Arbitrary user-registered MCP servers.
- Write tools, approval-bearing tools, payments, outreach sends or other external side effects.
- Provider-side multiagent delegation, Agent SDK runtime, automatic MCP credential rotation and automatic ambiguous-session reconciliation.
- Confidential/regulated data or any unsupported compliance claim.

## 9. External setup, to be completed last

- Public HTTPS API URL for the MCP endpoint.
- Anthropic Managed Agents access and API key.
- One dedicated Anthropic Vault ID for the Agency OS environment.
- Managed Agents environment limited-network allowlist containing only the Agency OS MCP host.
- Provider Agent configured for the supported model/system prompt; session-local overrides supply the MCP server and toolset.
- Staging-only smoke test with synthetic data before any production enablement.


## 10. Current implementation status

### Implemented in the consolidated branch

- Optional Streamable HTTP MCP ASGI transport mounted at `/v1/integrations/agency/mcp/sessions/{agent_session_id}`; the route is absent unless explicitly enabled. The former Claude-specific route remains a compatibility alias.
- Session-path plus high-entropy bearer authentication. Only a SHA-256 token digest is persisted; raw bearer material is returned once to the worker adapter and sent only to Anthropic Vault over HTTPS.
- PostgreSQL-backed authentication, expiry, revocation and request-rate limiting. Worker issuance is execution-capability-bound; provider Vault references are loaded and updated through worker-only SECURITY DEFINER functions. Neither API nor worker roles receive direct SELECT access to credential hashes.
- Host and Origin validation, MCP SDK DNS-rebinding protection, request-body limit and per-process concurrency limit.
- MCP discovery and invocation through the existing Tool Gateway. Discovery filters service identities by founder-granted machine scopes and agent identities by machine scopes plus workforce grants, allowed data class, explicit tool allowlist and tool risk. The server does not have a second tool registry or direct business-table access.
- Managed Agents adapter support for environment-network validation, Vault static-bearer creation, exact metadata reconciliation after ambiguous Vault creates, session-local `agent_with_overrides`, `mcp_toolset`, `mcp_servers`, `vault_ids`, and credential archive/revocation.
- Interrupted credential setup is detected through the OS-owned execution lookup. The adapter revokes/archives an orphan rather than blindly creating a second provider session.
- The route and provider integration remain disabled by default; only explicitly configured read-only or pending-draft tools can be enabled. Founder-provisioned service/worker identities may use their exact machine scopes; agent identities additionally require workforce grants.

### Not yet verified

- No live Anthropic API key, Vault, Environment, Agent or Managed Agents session has been provisioned or exercised by CI.
- No real provider-to-OS MCP initialize/list/call handshake has been smoke-tested.
- No production or staging deployment has been enabled, and no production database migration has been run.
- CI uses mocks for the Anthropic API and a disposable PostgreSQL database. It proves local contracts and authorization tests, not provider availability or deployment networking.

### Remaining engineering work

- Add a bounded cleanup/reconciliation worker for credentials left in `delete_pending` after a provider archive failure. Until then, the OS bearer is revoked immediately and provider-side archival failures require manual reconciliation.
- Add a staging smoke test against a dedicated Anthropic Vault and limited-network cloud Environment using synthetic data.
- Add multi-replica concurrency, crash-after-provider-call, lease-expiry and provider credential cleanup drills.
- Keep approval-bearing tools, client-data tools and external side effects disabled until an OS approval adapter consumes approval and action atomically and passes negative tests. The only current write-draft tool is public-source research capture, which remains `pending_review`.
- Workforce `budget_minor` is not yet a fully enforced runtime spend cap; provider spend reservation/settlement remains a separate gap.
- The initial transport concurrency semaphore is per API process; database request-rate limiting is shared. A global in-flight concurrency cap across multiple API replicas is not yet implemented.
- Modern MCP 2026-07-28 discovery/list/call is covered by a local integration test, including the absence of `Mcp-Session-Id`; actual Anthropic Managed Agents and Cowork client interoperability remains unverified until staging smoke tests. Native Skills over MCP, Tasks extension, Elicitation and MCP File Uploads are not implemented in this server yet.

### Current external setup

1. Configure a public HTTPS API origin that routes the MCP session path to the Agency OS API.
2. Create a dedicated Anthropic Vault for this environment and set `CLAUDE_MANAGED_MCP_VAULT_ID`.
3. Configure the Managed Agents Environment as `cloud` with `networking.type=limited`, `allow_mcp_servers=false`, and the exact MCP hostname in `allowed_hosts`.
4. Set `CLAUDE_MANAGED_MCP_PUBLIC_BASE_URL` and a reviewed comma-separated `CLAUDE_MANAGED_MCP_ENABLED_TOOL_KEYS` allowlist. The supported transport permits only read-only or pending-draft tools; see [Agent Integration Contract](AGENT_INTEGRATION_CONTRACT.md).
5. Keep `CLAUDE_MANAGED_MCP_ENABLED=false` until a synthetic-data staging smoke test verifies the full provider/Vault/MCP/Tool Gateway lifecycle.
