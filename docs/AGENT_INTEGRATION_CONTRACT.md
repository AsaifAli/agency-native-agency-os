# Agency OS Agent Integration Contract

**Status:** Implemented transport foundation and Cowork remote-MCP compatibility verified against current Anthropic documentation; live client connection and production ingress remain unverified.  
**Authority:** Agency OS is the system of record and policy enforcement point. Claude Code, Cowork and Managed Agents are untrusted clients/runtimes.

## 1. Non-negotiable boundary

All integrations use the same OS-owned identity, session, Data Protection Gateway, Tool Registry, Tool Gateway, workspace authorization, idempotency and audit path. No runtime receives database credentials, direct core-table access, shared filesystem access, Docker socket access or unrestricted provider credentials.

- **Claude Code:** engineering client. It may read approved public workspace context and submit explicitly granted public research drafts. Repository access remains governed by repository permissions and engineering review; MCP access does not grant repository access.
- **Cowork:** knowledge-work client. It may read approved public workspace context and submit explicitly granted public research drafts. Its local files and native connectors remain separate trust boundaries and must be reviewed independently.
- **Claude Managed Agents:** primary autonomous execution runtime for eligible long-running agency tasks, behind `ManagedAgentsRuntime`. The OS worker creates/resumes provider sessions, persists provider session IDs against OS executions, processes provider events, handles pause/cancel/recovery and returns terminal results. The active tool path is the worker's execution-bound `agent.custom_tool_use` callback into the OS Tool Gateway. This is Managed Agents' native tool interface. The separate Vault-backed provider-MCP route is a disabled compatibility option, not part of the active architecture; do not enable it alongside the callback path. Cowork and Claude Code use the single shared stateless MCP gateway.
- **Agency OS:** owns identity, workspace, tasks, approvals, business records, execution state, artifacts, budgets and audit.

Agents may exchange work only through OS-owned task assignments, tool results and persisted artifacts. Do not pass raw credentials, local paths or unscoped client files between runtimes.

## Managed Agents runtime integration

Managed Agents is not merely a connector to Cowork. It is the provider execution runtime for autonomous Agency OS agents when the runtime is enabled and configured. The OS Agent Registry and worker remain authoritative; Anthropic supplies the managed agent loop/session environment.

1. The OS worker claims a persisted execution under its lease and verifies the agent's runtime, workspace, data class, budget and current controls.
2. `ManagedAgentsRuntime` validates the pre-created, versioned Anthropic Agent and the configured Environment. Built-in Bash/file/browser toolsets and unreviewed provider MCP/skills/multiagent configuration are rejected; do not enable arbitrary shell or file execution until the per-execution sandbox and artifact gateway are proven.
3. The worker creates or resumes the provider session and persists its provider session ID on the OS execution before reporting it as started. Provider ambiguity stops for reconciliation rather than creating a duplicate session.
4. For the preferred custom-tool path, the provider emits `agent.custom_tool_use`; the worker validates the exact OS registry tool and invokes it using the current execution capability, workspace, DPG, approval and audit checks. It then sends `user.custom_tool_result` to resume the provider session. Provider tool definitions are checked against the OS registry on every attempt.
5. A separate Vault-backed provider-MCP transport remains feature-gated for compatibility only. It is not needed for the active Managed Agents callback path and must not be enabled alongside it. If a future provider limitation justifies switching transports, treat that as a deliberate architecture change with a separate staging review; it still must converge on the same Tool Gateway.
6. The worker persists provider events/results, checks OS pause/cancel state, waits for workflow runs to finish and marks the execution terminal only after the provider session has completed and OS persistence succeeds.

**Current status:** the runtime adapter, execution-bound custom-tool callback, persisted session lifecycle, pause/cancel/recovery and budget request have automated mock tests. The Vault-backed provider-MCP compatibility path is disabled and is not required for normal Managed Agents operation. The runtime remains feature-gated and no live Anthropic Agent, Environment, Vault or session has been exercised. Managed Agents is beta and is not ZDR/HIPAA-eligible; default to public/synthetic data until contractual and data-policy review.


## 2. Supported transport

The existing Streamable HTTP MCP server is now mounted at the generic path:

`/v1/integrations/agency/mcp/sessions/{agent_session_id}`

The prior `/v1/integrations/claude/mcp/sessions/{agent_session_id}` path remains as a compatibility alias. Both paths use the same authentication middleware and Tool Gateway. The generic transport remains disabled unless `AGENCY_MCP_ENABLED=true`, `AGENCY_MCP_PUBLIC_BASE_URL` is a public HTTPS origin and `AGENCY_MCP_ENABLED_TOOL_KEYS` contains an explicit tool allowlist. It does not require Anthropic Managed Agents or an Anthropic Vault. Provider-side Managed Agents MCP remains separately controlled by `CLAUDE_MANAGED_MCP_ENABLED` and its Vault settings. If both MCP modes are enabled together, they must share the same public base URL and server-side tool allowlist.

### MCP protocol compatibility (verified in the integration test)

The API uses the official MCP Python SDK 2.x (`mcp>=2.2,<3`; exercised locally with 2.3.0) and serves both protocol eras on the same endpoint:

- **Modern MCP 2026-07-28:** per-request protocol envelope, `server/discover`, `Mcp-Method`/`Mcp-Name` routing headers, no `initialize` handshake and no protocol `Mcp-Session-Id`. Each HTTP request can be handled independently by any API replica.
- **Compatibility MCP 2025-11-25:** the legacy initialize/list/call flow remains available for clients that have not migrated.

`stateless_http=True` is enabled. This does not remove Agency OS application state: the UUID in the URL is the durable OS `AgentSession` handle, and every request still authenticates the bearer and revalidates that session, identity, workspace, data class and tool authorization. Never treat the URL session ID as a credential. MCP transport statelessness is not permission to make business operations stateless or unaudited.

The 2026-07-28 stateless core, cacheable list results, multi-round-trip requests and Tasks extension are protocol capabilities, not replacements for the OS execution model. Short bounded tool calls remain synchronous. Long-running agency work must be created and tracked as OS executions through the transactional outbox. Native MCP Tasks will be added only when the server SDK has supported implementation and we can map task IDs to persisted OS executions without duplicating state.

Anthropic's built-in tool-search tool is documented for the Messages API, not Claude Managed Agents. Do not assume deferred MCP tool loading/tool search is available inside Managed Agents. There, the runtime will use an explicit per-agent allowlist and the OS server's authorization filtering; the server must never expose a broad catalog just because the provider can cache or search tools. Claude Code/Cowork may use client-side discovery optimizations where their MCP clients support them.

Do not conflate **Skills over MCP** with **Managed Agents native Skills**. Skills over MCP is a client/server extension for MCP clients. Managed Agents separately supports skills attached to its Agent or loaded from a mounted GitHub repository. The current `ManagedAgentsRuntime` rejects unreviewed provider `skills` configuration; no Managed Agents skills are enabled today. The next safe step is a versioned OS skill-to-provider mapping and exact allowlist, followed by a synthetic-data provider smoke test—not enabling every skill by default.

A client must support Streamable HTTP MCP and provide an HTTP bearer Authorization header. Claude Code supports remote MCP over HTTP. Cowork supports custom connectors using remote MCP; its connector can send a fixed Authorization request header. For Cowork, use a dedicated short-lived service machine identity in that header and the exact active session ID in the URL. For clients that can securely rotate per-session headers, prefer the shorter `aos_ms_...` session credential instead. The machine credential is validated against the path session and rechecked on every tool list/call; it does not grant access to another organization or workspace.

Anthropic's current connector documentation states that remote MCP calls from Cowork originate from Anthropic's cloud, not the user's computer. The API therefore must be publicly reachable over HTTPS port 443; apply the documented Anthropic IP allowlist if network filtering is used. Local MCP configuration is a separate mechanism and is not available to cloud Cowork sessions. Anthropic documents fixed request-header authentication (`static_headers`) as beta and organization-shared; do not assume it is enabled for every account or encrypted at rest. See [remote MCP connector setup](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp), [connector authentication](https://claude.com/docs/connectors/building/authentication), and [connector configuration](https://support.claude.com/en/articles/11176164-use-connectors-to-extend-claude-s-capabilities).

Anthropic's November 24, 2026 update adds Skills over MCP (public beta), Tasks and Elicitation (generally available), and a File Uploads rollout. We should adopt these as protocol/client capabilities rather than recreate them: publish reviewed OS-owned skills through Skills over MCP when the supported server SDK/client path is available; map long-running Tasks to OS execution/outbox records; use Elicitation only to collect user input, never as the approval authority; and route file uploads through the OS artifact gateway with conversation/workspace scope. The Python SDK 2.3.0 integration currently verifies modern stateless discovery/list/call; it does not yet claim native Skills, Tasks, Elicitation or MCP File Upload support.


**Cowork setup:** Add the Agency remote MCP URL through **Customize → Connectors** (or Organization settings for Team/Enterprise). Anthropic documents `static_headers` as a beta authentication mode: an organization administrator enters the fixed `Authorization: Bearer ...` request header once, and Claude sends it on every request. Use this only for a founder-only connector with a dedicated, narrowly scoped service identity. Anthropic states this credential is shared by the organization, not per user; do not enable this connector for a multi-user team until OS OAuth is implemented. If `static_headers` is unavailable in your account, do not try to paste the token into the URL or prompt—wait for the OAuth integration or use Claude Code's local helper. Connect/enable the connector per conversation in Cowork.

**Claude Code setup (macOS):** Store the dedicated service machine credential in Keychain Access as a generic password with service `agency-os-mcp` and account equal to your macOS username. The repository includes `scripts/agency_mcp_headers_macos.sh`, a `headersHelper` that reads that item and emits only the Authorization header. Configure the server at local scope (never project/shared scope) with the exact active session URL and that helper. Example JSON entry:

```json
{
  "type": "http",
  "url": "https://<public-origin>/v1/integrations/agency/mcp/sessions/<session-id>",
  "headersHelper": "/absolute/path/to/agency-native-agency-os/scripts/agency_mcp_headers_macos.sh"
}
```

Use `claude mcp add-json` or the local MCP configuration, then verify with `/mcp`. Do not put the bearer token in `.mcp.json`, `CLAUDE.md`, a prompt, or a committed settings file. The helper is local-only; it is not suitable for Claude Code cloud sessions unless the cloud environment has a separately provisioned secret store/helper.

**Cowork connector caution:** Anthropic documents `static_headers` as beta and shared at organization scope. Do not distribute one connector credential across client workspaces or expose it to a multi-user team. For multi-user/team use, implement OS OAuth with per-user consent and workspace-bound tokens before broader rollout. Anthropic's docs do not establish that fixed header values are encrypted at rest, so treat them as provider-held secrets with a narrow scope and short lifetime.

The REST alternative uses the same founder-provisioned machine identity and active OS session:

- `GET /v1/machine/tools` lists the exact tools granted to that identity.
- `POST /v1/machine/tools/{tool_key}/invoke` accepts `session_id`, typed `input` and an `Idempotency-Key` header.

The REST bearer is the machine credential, so keep its TTL short, store it in the client's secret store and revoke/replace it if exposed. Cowork's fixed-header connector can use this same machine credential; the OS still requires the session ID in the URL and validates that the session belongs to that identity. `aos_ms_...` remains available for per-session bearer configurations.

## 3. Founder-controlled bootstrap

Create a separate machine identity for each client/runtime and workspace. Do not share one identity between Code, Cowork and Managed Agents.

Example founder-approved service identity request (replace the organization/workspace identifiers and trim tool scopes to the exact job):

```json
{
  "name": "Cowork — public workspace context",
  "workspace_id": "<workspace-id>",
  "subject_type": "service",
  "subject_id": "cowork-public",
  "scopes": [
    "sessions:create",
    "tools:invoke",
    "tool:workspace.knowledge.search",
    "tool:revenue.lead.research.capture"
  ],
  "allowed_data_classes": ["public"],
  "ttl_days": 7
}
```

Send this to `POST /v1/orgs/{org_id}/machine-identities` using the founder's authenticated OS session. The raw `aos_mi_...` token is returned once. The OS validates the workspace and founder authority; do not create service identities by direct SQL.

Then create a bounded session with `POST /v1/machine/sessions`:

```json
{
  "purpose": "Cowork public workspace research",
  "data_class": "public",
  "ttl_seconds": 86400
}
```

Use the returned `id` as the `{session_id}` in the MCP URL. The `AGENCY_MCP_ENABLED_TOOL_KEYS` server allowlist must include each requested tool, and the identity's `tool:<key>` scopes are independently checked. Remove tools not needed by the connector.

1. A founder provisions an identity through `POST /v1/orgs/{org_id}/machine-identities` with `subject_type: "service"`, the exact workspace, explicit tool scopes and `allowed_data_classes: ["public"]` (or synthetic only where the tools permit it). Give each client a distinct identity and a short practical identity TTL (recommend 7 days or less for a fixed-header Cowork connector).
2. Store the returned `aos_mi_...` machine credential in that client's approved secret store. It is shown once. Never place it in a prompt, repository, project document or log. Cowork stores fixed request-header credentials encrypted according to its connector documentation; still treat the value as a secret and rotate/revoke it.
3. The client creates a bounded session through `POST /v1/machine/sessions` using its machine credential. The session is bound to the identity's organization, workspace and allowed data class.
4. For Cowork, configure the remote MCP URL with the exact session ID and add `Authorization: Bearer <machine credential>` as a fixed request header. The OS validates that this identity owns the active session in the URL and rechecks it on every list/call. For clients that support per-session header rotation, mint an `aos_ms_...` credential through `POST /v1/machine/sessions/{session_id}/mcp-credential`; it is shown once and expires within the session with a maximum one-hour TTL.
5. Revoke an individual session with `POST /v1/machine/sessions/{session_id}/revoke`; this cancels the session and revokes its session credentials. Revoke the machine identity to invalidate all of its sessions immediately.
6. When the session expires, create a new session and update the connector URL. Session credential version 1 is one-per-session; implicit rotation is not supported.

The machine credential is a bootstrap credential and must be protected more strongly than the session credential. The session credential is still a bearer secret: its one-time display does not mean one-time use. Generic MCP is enabled with `AGENCY_MCP_ENABLED`, `AGENCY_MCP_PUBLIC_BASE_URL` and `AGENCY_MCP_ENABLED_TOOL_KEYS`; no Vault is required for Code/Cowork service identities.

## 4. Authorization and tool policy

A tool is discoverable only when all of the following hold:

- The MCP server is enabled and the exact tool key is in the server-side allowlist.
- The machine identity has `tools:invoke` and `tool:<key>` scopes.
- The session data class is allowed by the tool and machine identity.
- For `agent` identities, the agent is active and has an enabled workspace capability grant for the exact tool/action/data class/scope. `worker` and `service` identities use their founder-provisioned machine scopes and never inherit agent grants.
- The tool is registered, schema-validated, and does not require approval.
- The invocation passes current session/identity, DPG, idempotency and audit checks.

MCP allows only registered `read_only` and `write_draft` tools. A `write_draft` tool may create a reviewable draft only; it cannot approve, promote, send, pay, deploy, alter permissions or perform another external side effect. Tools requiring approval remain unavailable until an OS-owned approval is consumed atomically with the protected action.

Current candidates:

| Tool | Risk | Data | Result |
|---|---|---|---|
| `system.health.read` | read_only | public/synthetic | API/database health only |
| `workspace.knowledge.search` | read_only | public | Approved, workspace-wide, non-client-linked public knowledge only |
| `revenue.lead.research.capture` | write_draft | public | Source-referenced research draft in `pending_review`; no CRM lead/contact or outreach |

The MCP environment allowlist and each machine identity's scopes are intersected. Enabling a tool globally does not grant it to every client.

## 5. Data and file exchange

- Knowledge search excludes internal, confidential, restricted, draft, retired, expired and client-linked knowledge.
- The first integration surface is public/synthetic only. Do not send commercial, confidential, regulated or client data to these runtimes until a separately reviewed eligibility policy, provider contract and client authorization permit it.
- Files must be uploaded through an OS-owned, workspace-scoped artifact workflow. Do not expose host paths, shared mounts, object-store credentials or permanent public URLs to agents. A general-purpose file/artifact upload MCP tool is not implemented by this milestone.
- All model outputs, retrieved content, file text and connector responses are untrusted data. They cannot change authorization, policy, system prompts or approval state.
- Cowork local files and native connectors are outside OS RLS. Review each connector's OAuth scopes, write permissions, retention and data destinations separately.

## 6. Events and handoffs

Synchronous MCP calls are for bounded reads and draft submissions. Long-running work remains in OS-owned executions and the transactional outbox. Handoffs must carry stable OS identifiers, not provider-local state:

- organization/workspace ID (server-derived, never trusted from model arguments)
- task and execution IDs
- session and machine identity IDs
- artifact ID and version
- event ID, schema version, correlation ID and causation ID
- idempotency key and result reference

Consumers must tolerate at-least-once delivery, reject stale/revoked sessions, deduplicate by stable intent, bound retries and reconcile unknown outcomes. A provider message or completion event is not proof that an OS artifact or business action was persisted.

## 7. Revocation, audit and failure behavior

- Revalidate identity and session at every tool call; do not rely on discovery-time authorization.
- In production, the shared Redis rate limiter must be enabled and fail closed if Redis is unavailable. Machine-bearer requests are bucketed by bearer fingerprint and client IP; MCP tool execution is additionally capped at 20 calls per session. Session-credential mode also enforces its database-backed per-minute credential counter.
- Machine identity revocation cancels its active sessions and makes session credentials unusable.
- Session credentials expire no later than their session or identity. The API returns raw tokens once and stores only token digests.
- Tool invocations persist the canonical request hash, sanitized payload/result, status and audit event. Same idempotency key with a different request is a conflict.
- Return generic authorization errors to clients. Do not disclose cross-workspace existence, provider secrets, raw payloads or internal stack traces.
- Unknown provider/network outcomes require reconciliation; never blindly retry a non-idempotent action.

## 8. Release gates and unverified items

The code changes establish the generic MCP mount, service-identity authorization, session credential issuance, public knowledge search and a narrowly scoped public research draft. They do not prove a live client connection.

Before enabling an external client:

- [ ] Configure public HTTPS routing, exact Host/Origin, DNS-rebinding protections, request limits and rate limits.
- [ ] Configure a dedicated machine identity per runtime/workspace and review exact scopes.
- [ ] Verify the client can securely store and send its configured bearer header; for Cowork, confirm the custom connector's fixed-header setup and rotate the dedicated service identity on schedule.
- [ ] Run modern `server/discover`/list/call tests with synthetic/public data from the actual client; use initialize/list/call only for clients that require the legacy protocol.
- [ ] Test wrong workspace, wrong session path, expired/revoked credential, disabled identity, missing tool scope, data-class mismatch, secret payload, prompt injection and duplicate calls.
- [ ] Confirm audit records and session revocation behavior.
- [ ] Verify Cowork connector permissions independently; do not assume MCP authorization governs native Cowork connectors. Remote Cowork connectors originate from Anthropic cloud infrastructure and require a public HTTPS endpoint.
- [ ] Keep Managed Agents on its existing worker callback path unless provider-side MCP is specifically needed and its Vault/network lifecycle has been tested.

No production activation, live Cowork connection, Anthropic Vault configuration, per-execution sandbox, commercial-data eligibility or compliance status is claimed by this document.


## Authentication limitation

OAuth 2.1 authorization-server discovery, dynamic client registration, refresh tokens and per-user consent are not implemented in this milestone. Claude Code can use the local Keychain header helper. Cowork can use Anthropic's beta organization-shared `static_headers` only for a founder-only connector; do not select OAuth mode until the OS authorization server exists. A multi-user/team rollout is blocked on OS-owned OAuth and per-user consent.
