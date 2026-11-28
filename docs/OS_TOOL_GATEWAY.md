# OS Tool Gateway

## Purpose

The OS Tool Gateway is the only intended path for machine identities to invoke Agency OS tools. Providers and agents do not receive database credentials, arbitrary URLs, shell access or direct core-table access.

## Current implementation

- Machine bearer authentication resolves an active, unexpired identity.
- The identity is bound to one organization and workspace.
- Every invocation supplies a persisted session created by that identity.
- Authorization checks the active identity, active session, workspace, session data class, `tools:invoke` and the exact `tool:<key>` grant.
- Identity and session rows are locked while authorizing, serializing invocation against founder revocation.
- The versioned code-owned registry defines each tool's key, version, description, risk level, allowed data classes, approval requirement, input schema and output schema.
- Input is passed through `protect_untrusted_payload` before schema validation and execution.
- Output is schema-validated and passed through the same DPG before persistence.
- Successful invocations persist a request hash, sanitized input, sanitized result, identity/session scope, idempotency key and completion timestamp.
- A unique organization/workspace idempotency key prevents duplicate execution. The request hash binds the key to the identity, session, tool version and sanitized input.
- Append-only audit records capture the tool, version, session, data class and redaction counts, not raw secrets or PII.

## Registered tool

| Key | Version | Risk | Behavior |
|---|---|---|---|
| `workspace.knowledge.search` | `1.0.0` | Read-only | Searches approved, workspace-wide public knowledge only; excludes client-linked and non-public knowledge |
| `system.health.read` | `1.0.0` | Read-only | Executes `SELECT 1` and returns API/database health; does not access client records |
| `revenue.lead.research.capture` | `1.0.0` | Write draft | Saves public-source company research for founder review; does not create a CRM lead/contact or send outreach |

The health tool proves the controlled invocation path without exposing business records. The Revenue research tool accepts only public-source evidence, writes a pending-review draft, and requires an explicit Founder Authority review followed by a separate promotion action before a CRM lead is created. It rejects contact fields and never sends outreach. Source URLs are stored as agent-supplied references; the OS does not independently fetch or verify them in this tool.

## API

- `GET /v1/machine/tools` — lists only registered tools granted to the authenticated machine identity.
- `POST /v1/machine/tools/{tool_key}/invoke` — invokes a registered tool using a machine bearer token, an active session and an `Idempotency-Key` header.

Example request body:

```json
{
  "session_id": "<session-id>",
  "input": {}
}
```

## Explicit limitations

- No arbitrary shell, SQL, filesystem, browser, URL-fetch or provider tool execution is exposed.
- MCP is an optional transport over the same gateway, disabled by default. It permits only explicitly allowlisted read-only or pending-draft tools.
- Only the limited public research-draft tool is registered for Revenue. No other Revenue/Delivery business tools are enabled yet.
- No external provider adapters or side-effecting tools are enabled.
- Tools marked as requiring approval are rejected until a transactionally consumed approval adapter exists.
- Per-tool budget reservation, concurrency quotas, execution leases, asynchronous external invocation, cancellation/reconciliation and provider webhook handling remain follow-on work.
- Tool invocation failures caused by infrastructure/database outages cannot always be persisted when the database itself is unavailable; external side-effecting tools must use durable OS execution/outbox workflows rather than this synchronous in-process path.

## Adding a business tool safely

Every future tool must have a typed input and output schema, a stable version, explicit data-class eligibility, risk classification, approval requirement, bounded payload/time/cost, a least-privilege adapter, DPG on both sides, scoped idempotency, durable result/error state, audit events and tests for cross-workspace access and denial paths. Side-effecting provider calls must be executed asynchronously through OS-owned execution/outbox records, never inside the request transaction.


See [REVENUE_AGENT_RESEARCH.md](REVENUE_AGENT_RESEARCH.md) for the draft, review and CRM promotion workflow.
