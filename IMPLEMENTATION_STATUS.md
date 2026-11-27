# Agency OS — authoritative implementation status

**Last reconciled:** 2026-11-27  
**Source of truth:** `main` at `4541626d6fffc904d8ee3131bb2f408efbe27acf`  
**Latest consolidation:** PR #58 merged on 2026-11-27.  
**Release posture:** **NO-GO for production.** Implementation and isolated tests do not establish production readiness.

This file is the current status summary. Historical branch comparisons, test logs and superseded PR checkpoints should not be treated as current blockers. See `docs/CONSOLIDATION_EXECUTION_LEDGER.md` for the active sequence and `docs/PRODUCTION_GRADE_MASTER_CHECKLIST.md` for the full release gates.

## Verification evidence on the merged candidate

| Check | Recorded result | Qualification |
|---|---|---|
| Backend pytest suite | **483 passed, 19 skipped, 2 warnings** | Merged PR #58 candidate; skipped tests are environment-dependent and are not counted as passes. |
| Isolated PostgreSQL 16 Compose suite | **105 passed, 2 warnings** | Disposable isolated stack with dedicated roles; not a production migration/deployment rehearsal. |
| Frontend ESLint | 0 errors; 7 existing React Hook dependency warnings | Passed before final Founder Console UI reconciliation. |
| Frontend TypeScript | Passed | Passed before final Founder Console UI reconciliation. |
| Next.js production build | Passed | Passed before final Founder Console UI reconciliation. |
| Exact merged-main frontend recheck | **Awaiting founder environment** | Fresh lint, typecheck and build are required after the final UI reconciliation. |
| GitHub Actions | Not run for this consolidation | Intentionally ignored per founder direction. |

No production database migration, production deployment, external provider activation, client-data operation or compliance assessment is claimed.

## Mission and architecture

Agency OS is the founder-controlled internal operating system for an AI Solutions Agency, not a SaaS product. Its two operating engines are:

- **Revenue:** research, leads, CRM, pipeline, proposals, approved outreach and marketing operations.
- **Delivery:** discovery, solution design, engineering, QA/security, deployment, projects, support and measurable client outcomes.

The agency philosophy is **Results as a Service (RAAS)**: the client result is the product; AI is the means. RAAS does not automatically imply contingent/performance pricing. Outcome measurement, attribution, commercial model and risk allocation must be agreed explicitly.

Architecture remains a modular monolith: Next.js/React Founder Console, Python FastAPI backend, PostgreSQL source of truth, Redis for cache/throttling/coordination, and independent Python workers. PostgreSQL owns business state, permissions, approvals, executions, sessions, artifacts and audit. Providers and automation tools are adapters, not sources of truth. No second queue/orchestration engine is required at this stage.

## Implemented foundations

### Core data, identity and founder governance
- Organization/workspace-scoped clients, contacts, leads, opportunities, projects and milestones.
- Explicit Founder Authority distinct from organization-owner membership.
- Founder-only provisioning and decisions; single-use approval consumption matches action/resource/workspace and rechecks active Founder Authority.
- Protected commercial operations consume approval and mutate protected OS state in the same transaction, with audit.
- Central autonomy policy: explicitly allowlisted internal actions, founder-approval actions and manual-review default for unknown actions.
- Authentik OIDC authorization-code + PKCE foundations, pre-provisioned subject linking, HttpOnly session cookies, CSRF checks, persistent browser-session revocation/rotation and expiry. Live Authentik/JWKS/MFA assurance remains unverified.

### Tenant isolation, workers and execution reliability
- PostgreSQL RLS and role separation are implemented; application and worker roles are intended to be non-owner, least-privilege roles.
- Human workspace-grant authorization was restored in PR #58.
- Worker production startup verifies `PROCESS_ROLE=worker`, PostgreSQL and the `agency_os_worker` role with `NOBYPASSRLS`.
- Worker execution and maintenance use database-verified, capability-bound claim/renew/release operations; caller-forgeable machine GUCs do not establish worker authorization.
- Durable execution lifecycle includes persisted attempts, leases, heartbeats, bounded retries, expired-lease recovery, pause/cancel acknowledgement and workspace-scoped maintenance.
- PostgreSQL outbox foundation supports allowlisted handlers, SKIP LOCKED claims, leases, bounded attempts, acknowledgement, sanitized errors, retry, dead letter and reconciliation.
- Workspace-scoped execution history and execution trace APIs; Founder Console Processes and Monitoring views.

### Audit, privacy and retention
- Audit payloads reject invalid/oversized structures, detect secrets fail-closed and redact supported PII.
- PostgreSQL audit events reject UPDATE/DELETE by application and worker roles. This is append-only protection, **not cryptographic tamper-evidence**; hash chaining or externally anchored integrity checkpoints are not implemented.
- Browser sessions store a digest of the JWT identifier, support server-side revocation and rotation, and are pruned in bounded batches.
- Agent sessions are constrained by machine identity data-class grants and cannot outlive the identity.
- Bounded retention scrubs terminal agent-session descriptive metadata after the configured 90-day default and tool invocation payloads after the configured 180-day default. Purged idempotency results return an explicit expired-result response rather than re-executing.
- Retention/deletion is incomplete for object artifacts, uploaded files, logs/traces, backups and provider-side data. Workspace erasure and machine-identity deletion require separate approved workflows.

### AI workforce and Claude runtime
- Workforce model includes offices, functional groups, departments, teams, human/agent/supervisor/sub-agent members, 121 position records, capability grants and delegation lineage.
- Founder-only bootstrap provisions the organizational catalogue; profiles remain inactive until explicit founder-authorized capability enablement and activation.
- Delegation enforces direct-manager hierarchy, active members, enabled definitions/grants and founder exclusion.
- Curated catalog of 18 reviewed, source-pinned skills with provenance and file digests. Skills are disabled, tool-free and public/synthetic-only; per-agent assignment and provider-side skill loading are not implemented.
- Chief of Staff plan draft is bounded, tool-free and requires founder review before task materialization. Worker maintenance releases dependent tasks after prerequisites succeed and synchronizes task/delegation state.
- Managed Agents adapter is opt-in and synthetic-first; it inspects provider Agent configuration, rejects unapproved built-in tools/MCP/skills/multiagent features, persists/resumes sessions, tracks workflow runs and routes non-completion to manual review.
- Managed Agents is beta. Live account provisioning, API compatibility, environment sandbox/egress, ambiguous-create reconciliation and production eligibility are unverified. It is not eligible for ZDR or HIPAA BAA.
- Claude Agent SDK adapter is not implemented. Recursive supervisor reasoning, dynamic replanning, delegated per-agent machine identities and live client-data execution are not implemented.

### Tool Gateway
- OS-owned machine identities use one-time displayed credentials stored as digests, bounded expiry, revocation and workspace/data-class scopes.
- Agent sessions are persisted and bounded. Tool calls pass machine/session checks, data-class policy, input/output protection, typed schema validation, workforce capability checks, idempotency, durable invocation records and audit.
- Code-owned registry currently includes read-only health and public lead-research draft capture. Research capture validates bounded public HTTPS source references and stores a founder-review draft; it does not create a CRM contact/lead or send outreach.
- Tool Gateway is an authorization foundation, not a general-purpose agent tool platform. No full Streamable HTTP MCP adapter has been integrated. The old `feature/managed-agents-mcp-bridge` branch is 31 commits ahead and 486 behind current `main`; do not merge/cherry-pick it wholesale. Its migration references missing parent `p6d8e2a4f913`, and its MCP dispatcher passes `max_calls_per_session` and `allowed_tool_keys` arguments unsupported by the current gateway signature. Current main also has no MCP SDK dependency, MCP configuration, or mounted MCP route. Port the transport/auth/session concepts against current main with a reviewed dependency, new migration ancestry and matching service contract. Tool grants for broader client-data or side-effecting operations remain disabled. The workforce capability model stores `budget_minor`, but the current Tool Gateway and Managed Agents callback do not reserve or settle spend against it; it is not yet an enforceable runtime spending cap. The MCP adapter must remain a protocol façade over OS-owned authorization, budget reservation/settlement, audit and durable state.

### Revenue, Delivery and RAAS
- CRM includes client/contact/lead/opportunity records, append-only contact activity timeline, source/qualification notes and suppression reasons.
- Founder Console includes Contacts, Leads, Opportunities and Proposals workflows. Proposal drafts are linked to opportunities and pricing approval is founder-gated.
- Service catalogue is founder-governed and versioned. Contract register requires approved proposal and signed evidence before executed status. Onboarding requires executed contract, evidence-backed checklist and founder approval before project activation.
- Invoice register prevents overbilling, requires founder approval before issue evidence and maintains an append-only payment receipt ledger. No payment collection is integrated; this is not statutory accounting.
- Delivery foundations include playbooks, founder-approved scope changes, time/cost records, provisional project financial summaries, exception inbox and project outcomes.
- Project outcomes record problem, desired outcome, metric/unit, baseline, target, direction, date, measurement method and agreed acceptance criteria. Outcome measurements are append-only and source-backed as submitted metadata. Founder-only delivery acceptance is distinct from measured business impact.
- Founder Console includes Client Outcomes page.

## Current gaps and blockers

### P0 — security and data protection
- Complete a table/route/function/role inventory for RLS, grants, ownership, SECURITY DEFINER functions and pooled-connection context.
- Complete negative cross-workspace tests for every API and nested object; organization membership must not substitute for exact workspace grant.
- Prove isolation across files, object storage, browser/agent sessions, caches, search/RAG, logs, tool outputs and generated artifacts.
- Complete Data Protection Gateway classification/minimization/PII-secret detection/redaction for every ingestion, file extraction, RAG, connector, provider callback, tool, log, cache and artifact path.
- Enforce per-client policy and runtime eligibility before any provider receives data.
- Complete scoped credential rotation, egress allowlists/SSRF defenses, sandbox isolation, resource limits, malware-safe file processing and secrets-history review.
- Add cryptographic audit integrity checkpoints; current append-only trigger alone is not cryptographic tamper-evidence.
- Complete retention/deletion for business records, sessions, artifacts, logs, backups and provider-side data with approved, recoverable workflows.
- Complete independent security assessment. No compliance claim is authorized.

### P1 — runtime, Revenue and Delivery
- Implement a protocol-only OS MCP adapter against the current Tool Gateway; enforce OS policy at every tool invocation and keep grants disabled until negative tests pass.
- Add delegated machine identities, per-agent budget reservation/settlement and tool-level enforcement (the current `budget_minor` field is configuration metadata only), versioned agent runtime configuration, controlled promotion and rollback.
- Verify worker crash/restart, concurrent claims, lease expiry, retry/DLQ, cancellation races, duplicate outbox delivery and provider timeout reconciliation under multi-worker execution.
- Register only approved, idempotent outbox handlers; no production external handlers are currently enabled.
- Implement prospect research/enrichment with source provenance, dedupe/merge review, attribution and confidence.
- Implement approved outreach dispatch only after sender authorization, consent/suppression, rate limits, idempotency, delivery receipts and immediate reply/opt-out/bounce stop handling. No external message dispatch is enabled.
- Complete proposal revision/versioning and client delivery, contract/e-sign integration, invoice document delivery, payment provider reconciliation, refunds/credit notes and tax/accounting integrations as applicable.
- Complete Delivery requirement-to-test traceability, independent QA/rework metrics, production release gates, handover, support cases, SLA and renewal workflows.
- Add automatic KPI ingestion, verified impact evidence, outcome revision/scope-change workflow and client acceptance/sign-off.
- Add trusted Evaluation Harness runner attestation, immutable test/commit/environment manifests and non-bypassable release-blocking gates. Caller-supplied booleans are not trusted evidence.
- Complete provider routing/resilience, per-execution usage/cost accounting, budgets, margin/forecast and founder emergency disable controls.

### P2/P3 — Founder Console and operations
- Fresh exact-main frontend lint, TypeScript and production build after final UI reconciliation; browser-based critical-flow/accessibility tests.
- Unified founder work queue across approvals, escalations, blocked tasks, failures, client risks and budget exceptions; drill-down to source record, execution, evidence and audit.
- Metrics/logs/traces, alert routing, dashboards, cost visibility, dependency/container/SAST/secret/license scans and SBOM.
- Encrypted PostgreSQL and object-artifact backups; isolated restore drill; measured RPO/RTO and recovery runbooks.
- Separate dev/staging/production configuration and credentials; staging synthetic acceptance; controlled migration/release/rollback.
- Configure and verify Authentik, Claude, research sources, email/webhooks, object storage and website intake only with synthetic data and explicit authorization.
- Website signed lead bridge is implemented in both repositories but remains disabled until matching server-only secrets, fixed org/workspace mapping, HTTPS, external configuration and synthetic idempotency/recovery tests are complete.

## Immediate work order

1. Exact-main stabilization and frontend checks.
2. Complete tenant/RLS and Data Protection Gateway inventory and negative tests.
3. Artifact/object storage isolation and retention lifecycle.
4. OS MCP adapter over the Tool Gateway, with all grants fail-closed.
5. Worker/outbox recovery and reconciliation acceptance.
6. Revenue provenance, dedupe and governed outreach.
7. Delivery QA, handover, support and RAAS evidence.
8. Founder Console work queue and operational drill-down.
9. Monitoring, SBOM, backup/restore, RPO/RTO and runbooks.
10. Staging synthetic acceptance, independent security review and explicit founder production go/no-go.

## Founder-environment checks to run last

After code changes stabilize, run from the local checkout on exact `main`:

```bash
git fetch origin
git switch main
git pull --ff-only origin main

cd frontend
npm run lint
npx tsc --noEmit
npm run build
```

Then run the isolated PostgreSQL Compose suite and browser critical-flow tests. Live provider credentials, DNS, object storage, email/webhooks, staging deployment and backup restore require founder-environment access and will be presented as a final checklist. Production migration/deployment and destructive data actions require separate explicit approval.
