# Machine Identity and Session Security

## Scope
Machine identities and bounded sessions are the authentication foundation for the OS Tool Gateway and supported external integrations. The optional MCP transport remains disabled by default and is not enabled for production by this document.

## Identity contract
- A machine identity belongs to exactly one organization and workspace.
- Subject types are agent, worker or service. Agent identities must reference an enabled agent in the same workspace.
- Only an explicitly authorized founder can issue or revoke identities.
- Credentials are high-entropy random bearer secrets. Only SHA-256 digests are stored; raw credentials are returned once at issuance.
- Identity grants contain explicit scopes and allowed data classes. Only synthetic and public data grants are currently enabled.
- Credentials expire within 90 days and can be revoked. Revocation cancels all active sessions in the same transaction.
- Never place the raw credential in prompts, logs, audit payloads, source control or browser storage. Provision it through a secret manager.

## Session contract
- A machine identity can create a session only with `sessions:create`.
- Interactive `service` identities may mint one short-lived MCP credential for their own session only when they also hold `tools:invoke`. Agent/worker MCP credentials remain bound to the existing worker execution lifecycle.
- Interactive MCP credentials are displayed once, stored as digests, expire within the session and at most one hour, and can be revoked per session. PostgreSQL issuance/revocation uses narrowly scoped SECURITY DEFINER functions; the API role cannot SELECT, INSERT or UPDATE the credential table directly.
- Session organization/workspace/identity are derived from the authenticated identity, never caller-supplied.
- Machine identities and agent sessions are row-scoped to the authenticated machine identity as well as its organization/workspace. A Cowork/Code service identity cannot enumerate another service identity or its sessions in the same workspace; worker access remains tied to its execution/maintenance capability.
- Session lifetime is bounded to 60 seconds through 24 hours and cannot outlive the identity.
- Sessions persist purpose, data class, status and lifecycle timestamps. The worker maintenance loop expires due sessions in bounded, row-locked batches and writes an audit event for each expiry.
- Tool authorization requires the exact active session, matching scope, identity, workspace and data class. The REST Tool Gateway and MCP transport share the same code-owned registry and invocation service.
- `POST /v1/machine/sessions/{session_id}/mcp-credential` mints the interactive service credential; `POST /v1/machine/sessions/{session_id}/revoke` revokes that session and its credentials. Both require the authenticated owning service identity.

## API
- POST /v1/orgs/{org_id}/machine-identities — founder-only, creates identity and returns its secret once.
- POST /v1/orgs/{org_id}/machine-identities/{identity_id}/revoke — founder-only, revokes identity and cancels active sessions.
- POST /v1/machine/sessions — machine bearer credential required; creates a session within its fixed scope.
- POST /v1/machine/sessions/{session_id}/mcp-credential — service identity only; returns one short-lived session bearer once.
- POST /v1/machine/sessions/{session_id}/revoke — service identity only; revokes the owning session and its credentials.
- GET /v1/machine/tools and POST /v1/machine/tools/{tool_key}/invoke — machine bearer plus active session; expose only founder-granted registered tools.

## Release limitations
- Do not issue production machine credentials until PostgreSQL migration verification, secret-manager configuration, token rotation procedures, retention/deletion and artifact cleanup policies, recovery tests and end-to-end authorization tests are complete.
- No agent tool grants are enabled by default. The current scope strings are authorization vocabulary for a future gateway.
- This work does not assert compliance or production readiness.
