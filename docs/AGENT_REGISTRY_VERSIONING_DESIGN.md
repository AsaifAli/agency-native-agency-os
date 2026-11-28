# Agent Registry Versioning — Design and Acceptance

**Status:** Design approved for implementation on the single `main` branch.  
**Scope:** Workspace-scoped OS agent configuration versions and execution pinning. This does not duplicate Claude-owned specialist definitions or provider credentials.

## Current audit

- `agents` currently stores mutable `name`, `department`, `instructions`, `runtime`, `data_class` and `enabled` fields.
- `create_execution` copies `runtime` and `data_class`, but the worker later reads `Agent.instructions` from the live row. A queued execution can therefore observe a different instruction set from the one present when it was created.
- The specialist catalogue and team blueprints are separate, read-only/versioned source material. They are not workspace Agent configuration versions.
- Workforce capabilities are separate mutable permission grants with founder approval. They must remain separate from agent instructions and must be rechecked at execution time so a revoked capability cannot be resurrected by an old version.
- Provider credentials remain environment/secret-manager owned. They must never be stored in an agent version.

## Contract

### Data model

Add immutable `AgentVersion` records containing:

- tenant scope: `org_id`, `workspace_id`, `agent_id`
- monotonically increasing `version_number`
- snapshot: `name`, `department`, `instructions`, `runtime`, `data_class`, sanitized `runtime_config`
- canonical `config_sha256`, `change_reason`, `created_by`, `created_at`

Add `Agent.current_version_id` as the active-version pointer. The existing Agent fields remain a materialized compatibility projection and are updated atomically when a version is activated.

Add nullable `Execution.agent_version_id` with a tenant-scoped FK. New executions pin the active version at queue time. Existing executions are backfilled to the current version where possible; legacy nulls retain the current compatibility fallback.

Versions are append-only. Database permissions/triggers and API design must prevent update/delete of version snapshots. Rollback creates a new version by copying an older snapshot and activating the new version; it never rewinds or mutates history.

### API

- `GET /v1/orgs/{org_id}/agents/{agent_id}/versions?workspace_id=...`
  - Workspace-scoped list, ordered by version number descending.
- `POST /v1/orgs/{org_id}/agents/{agent_id}/versions?workspace_id=...`
  - Creates an immutable draft version. Founder authority required. Does not change the active pointer.
- `POST /v1/orgs/{org_id}/agents/{agent_id}/versions/{version_id}/activate?workspace_id=...&approval_id=...`
  - Requires founder authority and an approval bound to the exact version ID and checksum.
  - Consumes approval, switches active pointer, mirrors snapshot fields to Agent, and records audit in one transaction.
- `POST /v1/orgs/{org_id}/agents/{agent_id}/versions/{version_id}/rollback?workspace_id=...&approval_id=...`
  - Creates version N+1 from the selected historical snapshot and activates it atomically under the same approval model.

Input/output schemas are separate. Runtime values are allowlisted. `runtime_config` contains non-secret provider/runtime options only; API keys and credentials remain outside the database.

### Execution behavior

- At queue time, execution stores the active `agent_version_id`, runtime and data class.
- At worker start, load the pinned version by `org_id`, `workspace_id`, `agent_id` and `version_id`. Use its instructions and identity metadata rather than mutable live Agent fields.
- If the pinned version is missing or tenant-mismatched, fail closed and audit.
- Recheck current workforce capability grants at execution start. A pinned version is historical configuration, not an authorization bypass.
- Existing executions without a version ID use the legacy Agent projection and are marked as legacy in audit metadata.

## Security and transaction rules

- All reads/writes include org and workspace scope; RLS remains mandatory.
- Only founder-authorized users may create, activate or roll back configuration versions.
- Activation/rollback approval consumption and pointer change occur in one DB transaction.
- The approval payload binds operation, agent ID, version ID, version checksum and workspace.
- Version snapshots contain no secrets, raw client data or provider tokens.
- Runtime/data-class values are validated against explicit allowlists.
- Audit events record version creation, activation, rollback, prior/new version IDs and checksum.
- External provider calls never occur in version-management transactions.

## Acceptance tests

1. Existing agents receive version 1 during migration; pointer and snapshot checksum match their legacy fields.
2. New workspace agents receive version 1 idempotently.
3. Version numbers are monotonic per agent and duplicate version numbers are rejected by a unique constraint.
4. Version records cannot be updated/deleted through the application role or API.
5. Cross-org/workspace version reads, activation and rollback are rejected.
6. Draft creation does not change the active pointer.
7. Activation requires founder authority and a matching, unused approval; wrong checksum/version or reused approval fails.
8. Activation and approval consumption are atomic under injected failure.
9. Rollback creates a new version number with the selected prior snapshot and preserves every old version.
10. A queued execution continues using its pinned version after a newer version is activated.
11. Capability revocation still blocks execution even when its pinned agent version predates the revocation.
12. CI verifies Alembic has one head, migration upgrade succeeds on disposable PostgreSQL, and all API/worker tests pass.

## Explicit non-goals

- No Claude Agent SDK fallback or second agent runtime.
- No duplicate specialist prompt/skill registry; Claude-owned source material remains authoritative where documented.
- No provider credentials or secrets in AgentVersion.
- No change to global founder authority or capability approval rules.
- No automatic activation of a version after creation.
