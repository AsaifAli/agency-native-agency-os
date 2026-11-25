# Machine Identity and Session Security

## Scope
This increment establishes scoped machine credentials and durable execution sessions. It is not yet the complete OS Tool Gateway and does not enable any external tool adapter or provider-side MCP access.

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
- Sessions persist purpose, data class, status and lifecycle timestamps.
- Tool authorization requires the exact active session, matching scope, identity, workspace and data class.
- authorize_tool_session is an authorization primitive only. It does not invoke a tool. Tool invocation, input/output DPG, approval checks, budgets, adapter sandboxing and invocation audit are follow-on gateway work.

## API
- POST /v1/orgs/{org_id}/machine-identities — founder-only, creates identity and returns its secret once.
- POST /v1/orgs/{org_id}/machine-identities/{identity_id}/revoke — founder-only, revokes identity and cancels active sessions.
- POST /v1/machine/sessions — machine bearer credential required; creates a session within its fixed scope.

## Release limitations
- Do not issue production machine credentials until PostgreSQL migration verification, secret-manager configuration, token rotation procedures, session cleanup/recovery jobs and end-to-end authorization tests are complete.
- No agent tool grants are enabled by default. The current scope strings are authorization vocabulary for a future gateway.
- This work does not assert compliance or production readiness.
