# Security retention policy

This policy applies to the internal Agency OS database. It is implemented as
bounded, workspace-scoped maintenance; it does not authorize production data
deletion or override client contracts, legal holds, or founder approval gates.

## Current defaults

| Record | Retention | Action | Preserved |
|---|---:|---|---|
| Browser sessions | 30 days after expiry/revocation | Delete through the existing audited worker-only PostgreSQL function | Audit events |
| Agent sessions | 90 days after terminal state | Replace the free-text purpose with a fixed marker | Session ID, workspace, machine identity, status, data class, timestamps, execution references, audit |
| Tool invocation payloads | 180 days after completion | Replace request payload with an empty object and clear result | Invocation ID, workspace, machine identity, session reference, tool/version, idempotency key, request hash, status, error code, timestamps, audit |
| Machine identities | No automatic deletion | Retain revoked/expired identity metadata | Credential digest, prefix, scopes, revocation/expiry and usage metadata |

The 90-day and 180-day values are initial internal defaults and can be
overridden with AGENT_SESSION_METADATA_RETENTION_DAYS and
TOOL_INVOCATION_PAYLOAD_RETENTION_DAYS. Bounds are 1–3650 days.

## Replay and execution safety

Tool invocation rows are idempotency tombstones. The retention worker never
deletes them or their idempotency keys/request hashes. If a matching retry
arrives after its result payload has been purged, the gateway returns HTTP 410
with IDEMPOTENCY_RESULT_EXPIRED; it does not execute the tool again.
A request with a different hash remains an idempotency conflict.

## Execution boundary

Session and tool-payload scrubbing runs only after the worker has claimed the
exact workspace maintenance capability. Each table is processed in a separate
bounded batch with row locks and SKIP LOCKED. Changes and their minimal audit
events commit in the same transaction. The worker does not enumerate tenant
workspaces or receive a table-wide RLS bypass.

## Not yet covered

- Object-storage artifacts need an OS-owned artifact registry, workspace-bound
  authorization, lifecycle state, legal-hold support, deletion receipts and
  reconciliation before automated object deletion is enabled.
- Operational logs, traces, backups and provider-side records need explicit
  retention and deletion contracts. Their retention is not established by this
  policy.
- Machine identity deletion and workspace/client erasure require a separate
  approval-gated workflow with dependency ordering and verified recovery.
- No compliance certification or legal retention compliance is implied.

## Rollout

Apply the schema migration and run the isolated PostgreSQL suite before any
deployment. This change does not run a cleanup job against production data and
does not deploy itself.
