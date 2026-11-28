# Artifact Gateway and Cumulative Budget Audit

**Audit date:** 2026-11-28  
**Branch:** `integration/agency-os-consolidated-2026-11`  
**Status:** Audit complete; implementation intentionally not enabled.

This audit records the current code evidence and the implementation boundary for the next security milestone. It does not claim that uploads, object storage, malware scanning, cumulative budgets, or spend reservations are implemented.

## 1. Artifact gateway — current evidence

### Verified in source

- No FastAPI `UploadFile`/`File()` endpoint or frontend upload flow exists in the authored application source.
- The additive `Artifact` metadata ORM model and tenant RLS migration have since been implemented (see section 3/4 below). No object-storage client, signed-URL flow, quarantine persistence, malware scanner, or artifact cleanup worker exists.
- `.env.runtime.example` contains generic `OBJECT_STORAGE_ENDPOINT`, `OBJECT_STORAGE_BUCKET`, `OBJECT_STORAGE_ACCESS_KEY`, and `OBJECT_STORAGE_SECRET_KEY` placeholders. They are not wired into `app/config.py` or a storage adapter. These placeholders are not evidence of a configured provider.
- `app/data_protection.py` currently sanitizes bounded structured execution payloads and provider results. It is not a binary-document classifier, parser, malware scanner, or upload gateway.
- `app/retention.py` scrubs selected old session and tool-invocation payloads. It does not delete object-store artifacts or maintain artifact lifecycle state.
- PostgreSQL tenant RLS is generated from the explicit `ORG_TABLES` inventory in `migrations/versions/t0a1b2c3d4e5_postgresql_tenant_row_level_security.py`; every new tenant-bearing artifact table must be added to that inventory and the ORM/RLS parity tests.
- Existing security docs correctly keep arbitrary file parsing, shell execution and untrusted generated code outside the API and ordinary worker until isolated execution and safe artifact transfer are proven.

### Required design — one OS-owned gateway

The OS remains the only authorization and metadata authority. A storage provider is an opaque byte store, not a permission system or source of truth.

1. **Scope and ownership:** every artifact has immutable `org_id` and `workspace_id`, an opaque UUID, creator/service identity, purpose, classification, retention policy, and optional parent references (task, execution, attempt, conversation/thread). A thread-scoped artifact must also bind the exact thread and must not become workspace-wide implicitly.
2. **Private storage:** tenant-scoped, server-generated object keys; no user filenames in keys; bucket/container private; no public ACLs; no provider credentials or host paths exposed to agents. Never trust a client-supplied object key.
3. **Upload lifecycle:** `initiated -> quarantined -> scanning -> available` or `rejected/failed`; only `available` artifacts can be downloaded or supplied to a runtime. A failed or unavailable scanner fails closed for untrusted uploads.
4. **Bounded ingress:** enforce reverse-proxy and application body limits; stream with a hard byte ceiling; validate extension, declared MIME and magic bytes; generate a safe display filename; hash content; reject malformed encodings and unsupported formats. Do not trust `Content-Length` alone.
5. **Archive/parser safety:** initially reject archives and executable formats unless there is a specific approved need. Any future extraction must cap compressed and expanded bytes, entry count, nesting depth, path traversal, symlinks, CPU and wall time. Parsing runs outside API/ordinary worker in a constrained isolated service with default-deny egress.
6. **Malware and content policy:** scan/quarantine before availability; record scanner/version/result and fail closed on timeout/error. Classification and PII/secret detection must be content-aware and format-specific. Existing text sanitization is not sufficient evidence for binary/document safety.
7. **Download authorization:** authorize the requesting human or machine principal against the artifact's exact org/workspace/thread scope on every access. Prefer authenticated streaming through the gateway initially. If signed URLs are later used, make them short-lived, object-specific, non-listable and issue only after authorization; never persist or audit the URL/token itself.
8. **Audit and lineage:** audit upload intent, accepted/rejected scan, download, runtime attachment, version/supersession, retention and deletion using IDs, digests and reason codes; do not put file contents or signed URLs in audit payloads. Keep immutable content digest and lineage metadata.
9. **Retention and deletion:** retention is policy-driven and workspace-aware. Deletion is an explicit lifecycle with approval where client data/destructive scope requires it; delete object bytes, derived text/indexes/previews and caches, then reconcile orphaned DB/object records. Keep recoverability and backup retention explicit.
10. **Provider/runtime boundary:** agents receive opaque artifact IDs and narrowly scoped gateway operations, never object-store credentials, bucket listing, local paths or unrestricted URLs. Runtime eligibility is checked before commercial/confidential content leaves the OS; default to synthetic/public data until provider eligibility and contracts are verified.

### Implementation sequence and release gates

- **A. Contract and schema:** artifact metadata/version model, scope constraints, lifecycle states, retention fields, digest/size/media metadata, exact parent lineage, RLS and role grants. No upload endpoint yet.
- **B. Storage adapter:** provider-neutral interface and one selected private S3-compatible provider, with startup validation, server-side encryption requirements, no public access, and fake/in-memory test adapter. Do not choose a live provider from environment variable names alone.
- **C. Quarantine intake:** bounded streaming, generated object key, digest, MIME/magic validation, quarantine write, scanner result and atomic metadata/audit transitions. Keep endpoint disabled until a real scanner is configured.
- **D. Authorized retrieval:** exact workspace/thread authorization, authenticated streaming, range/response header policy, no list/bucket enumeration, negative cross-tenant tests.
- **E. Lifecycle:** cleanup/reconciliation, retention expiry, deletion approval path, derived-index cleanup, backup/restore evidence.
- **F. Runtime integration:** only after A–E pass; add artifact references to tool/runtime contracts and verify provider eligibility, thread isolation and revocation.

Do not add a local-disk fallback, public bucket, direct-to-provider client upload, general-purpose MCP file tool, or unscoped shared file mount.

## 2. Spend and budgets — current evidence

### Implemented and verified

- Claude Managed Agents receives `CLAUDE_MANAGED_SESSION_BUDGET_CENTS` as a provider-enforced per-session USD list-cost cap (`app/integrations/managed_agents.py`, `app/config.py`). This is a per-session ceiling, not an OS-wide cumulative budget.
- Normalized provider usage is validated and persisted per execution attempt. Failed attempts can retain reported usage, and execution-level aggregation sums known usage across persisted retries (`app/worker_service.py`). Unknown usage is not estimated.
- Workspace-scoped execution history and monitoring expose provider-reported usage/cost with an explicit list-price caveat.
- `Execution.max_attempts` bounds retry count; it is not a monetary budget.

### Gaps confirmed in source

- `WorkforceCapability.budget_minor` and `currency` are configured, approved and displayed, but no execution reservation, settlement, or cumulative usage check consumes them. Treat the field as configuration metadata, **not an enforced spend limit**.
- Project `budget_minor` is a delivery/commercial budget compared with recorded project costs. It is not linked to provider execution cost and does not reserve AI spend.
- There is no durable budget account/period ledger, atomic reservation, settlement record, concurrent-spend guard, or idempotent provider-cost reconciliation.
- Provider usage currently reports Anthropic list cost in USD cents. Workforce capability budgets default to INR. There is no approved FX conversion or common currency policy; these values must not be compared or summed.
- Per-session provider caps do not prevent multiple concurrent sessions/retries from exceeding a workspace or member's intended cumulative allocation.

### Required design — separate runtime spend from commercial budgets

1. Keep provider spend in its source currency and integer minor units. Do not convert currencies without an explicit rate source, timestamp, policy and audit trail.
2. Define budget scope explicitly: organization/workspace, workforce member/capability and optional time period. Decide whether capability budgets are cumulative, period-based, or per-execution before implementing enforcement.
3. Use a durable ledger with immutable reservation/settlement/release entries and idempotency keys tied to execution/attempt/provider event. Maintain a locked/atomically updated account balance or reserved/settled counters with DB constraints.
4. Reserve a conservative maximum before provider dispatch in the same transaction as the execution/attempt transition. If reservation cannot be made, do not call the provider.
5. Settle using validated provider-reported usage after each attempt, including failed attempts and retries. Release unused reservation; preserve unknown/unreported cost as unknown and retain the reservation or move to manual reconciliation rather than assuming zero.
6. Serialize concurrent reservations using row locks or a conditional atomic update. Add PostgreSQL concurrency tests proving parallel executions cannot overspend the same account.
7. Retries are separately billable attempts. Reusing an execution idempotency key must not create a second reservation; a new attempt needs a new reservation key while respecting the parent budget.
8. Handle provider timeout/ambiguous completion as an unknown external outcome: keep reservation held, reconcile from provider evidence, and never blindly issue another billable session.
9. Budget exhaustion must stop future dispatch and request safe pause/manual review; never interrupt an external provider operation based solely on a stale local estimate.
10. Expose reserved, settled, remaining, unknown and currency separately in the founder dashboard. Keep project delivery budget and AI provider spend as distinct measures.

### Next implementation gates

- First decide and document budget scope/period and the currency for each spend account. Existing INR capability metadata cannot be silently reinterpreted as USD provider spend.
- Add failing tests for concurrent reservation, duplicate reservation, retry accounting, partial/unknown usage, provider timeout reconciliation, currency mismatch and budget exhaustion.
- Implement ledger/reservation in PostgreSQL and integrate the reserve-before-dispatch/settle-after-attempt transaction boundaries.
- Add disposable PostgreSQL concurrency tests and verify audit, recovery, cancellation and outbox behavior before enabling enforcement.

## 3. Current readiness statement

| Capability | Status | Boundary |
|---|---|---|
| Structured execution payload protection | Implemented; bounded | Not a file scanner/classifier |
| Artifact metadata model and workspace RLS | Implemented; PostgreSQL CI migration/role-tested | No object bytes, storage adapter or upload route |
| File upload/download gateway | Not implemented; bounded validation primitives exist | No upload surface should be enabled |
| Private object storage | Not implemented/unconfigured | Example env placeholders only |
| Malware/quarantine pipeline | Not implemented | Fail closed; no untrusted upload parsing |
| Artifact retention/deletion/reconciliation | Not implemented | Existing session/tool scrub is not artifact cleanup |
| Managed Agents per-session spend cap | Implemented; provider-enforced | USD list cost, per session only |
| Per-attempt provider usage and retry aggregation | Implemented; CI-tested | Unknown attempts remain unknown |
| Workforce cumulative budget enforcement | Not implemented | Configured budget fields are not spend controls |
| Workspace/member cumulative reservation ledger | Not implemented | Requires explicit scope/currency decision |

No production storage credentials, provider account, scanner, object bucket, FX source, or spend-account policy was configured or tested during this audit.

## 4. Artifact ingestion primitives — 2026-11-28

Implemented in `app/artifact_gateway.py` (not wired to an HTTP route or worker):

- Bounded streaming read with a 20 MiB default cap and a hard 100 MiB configurable ceiling.
- Strict allowlist for PDF, PNG, JPEG, UTF-8 plain text and CSV; extension and declared media type must agree.
- Basic magic/signature validation for PDF and images; text must be valid UTF-8 and contain no NUL/binary control bytes.
- Rejects empty content, unsupported/archive formats, path components, control/format characters in filenames, and oversized streams.
- Computes SHA-256 while reading and returns an immutable inspected payload.
- Generates tenant/workspace/artifact-scoped opaque object keys from validated server-side identifiers; filenames are never part of storage keys.
- `require_clean_scan` accepts only an explicit clean result with scanner name and version. Missing, errored, unknown or incomplete scanner results fail closed.

Tests: `tests/test_artifact_gateway.py` covers content-type/signature mismatch, path traversal, size limits, empty/archive rejection, binary text, digest/size, opaque keys and scanner fail-closed behavior.

**Still deliberately not implemented/enabled:** provider adapter, credentials, private bucket verification, quarantine persistence, scanner integration, lifecycle transactions, upload/download endpoints, worker permissions, cleanup/reconciliation. The inspected bytes are currently bounded in memory; do not expose this helper to large or untrusted traffic until a streaming-to-private-quarantine adapter and scanner are selected and integrated. PDF/image signature checks are not malware scanning and do not make files safe for parsing or runtime execution.

## 5. External storage provider checkpoint — 2026-11-28

Cloudflare R2 was evaluated as the preferred candidate because the agency already uses Cloudflare infrastructure and R2 exposes an S3-compatible API. A read-only check against the connected Cloudflare account returned API error `10042`: **“Please enable R2 through the Cloudflare Dashboard.”** No bucket exists or was provisioned through this work; no paid service was enabled and no account settings were changed.

Official provider constraints reviewed:

- R2 supports S3-compatible clients; the endpoint is account-specific: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
- R2 Object Read & Write credentials can be scoped to specific buckets, but those object-level credentials are supported by the S3-compatible API, not Cloudflare's general REST API.
- The future adapter should use a dedicated bucket-only Object Read & Write credential stored in the server secret manager. It must not expose credentials to the browser, Cowork, Claude Code or agents. The OS remains responsible for authorization and object-key selection.

References: [R2 S3 API](https://developers.cloudflare.com/r2/get-started/s3/), [R2 authentication and token permissions](https://developers.cloudflare.com/r2/api/tokens/), [object-token API limitation](https://developers.cloudflare.com/r2/platform/troubleshooting/).

**External gate:** founder enables R2 in Cloudflare Dashboard, provisions a private bucket, and creates a bucket-scoped Object Read & Write token. Until then, no provider adapter is configured and uploads remain disabled. Do not substitute a public bucket or a local-disk fallback.

## 6. Cumulative spend policy decision — not silently assumed

The code confirms `WorkforceCapability.budget_minor` is a per-member/per-capability configuration field with `scope` values `self`, `team` or `workspace`; its default currency is INR. That `scope` describes authorization scope, not a budget period. Existing project budgets are also commercial delivery budgets. Neither is a valid provider-spend account.

A safe implementation recommendation is a **separate workspace provider-spend account denominated in USD cents**, because current Anthropic list-cost usage is USD. A future ledger should reserve the configured maximum session cost before dispatch, settle each provider attempt from validated usage, keep ambiguous outcomes reserved pending reconciliation, and use a PostgreSQL-serialized reservation so concurrent workers cannot overspend. Member/capability sublimits can be layered later without converting or reinterpreting INR capability metadata.

Before enforcement is implemented, the founder must choose whether the workspace account is a hard cumulative lifetime cap or a calendar-month cap (UTC), and set its USD-cent limit. No default limit or FX conversion is inferred. The existing per-session provider cap remains the only enforced monetary ceiling today.
