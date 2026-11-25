# Agency OS Production Readiness Checklist

**Last reviewed:** 2026-11-25
**Tracking branch:** `main` (PR #45 merged); `security/predeploy-20-point-audit` (PR #47 open draft)
**Latest merged milestone:** [PR #45](https://github.com/AsaifAli/agency-native-agency-os/pull/45)
**Status:** PR #45 is merged. PR #47 remains an open draft. Persistent browser-session revocation and atomic rotation are published on the PR #47 branch but remain unmerged and unverified on PostgreSQL 16. PostgreSQL RLS, live identity/MFA verification and other release gates remain. Not a certification or release approval.

## Progress snapshot

| Measure | Estimate | Meaning |
|---|---:|---|
| Internal implementation | **56%** | Share of planned internal code capability implemented or substantially scaffolded |
| Overall scope including external integrations | **51%** | Includes provider setup, credentials, legal review and production operations |
| Production verification | **28%** | Evidence from tests, CI, security review, migration rehearsal and recovery drills |
| External configuration | **5%** | Only limited setup is evidenced; most providers remain unconfigured |
| Release readiness | **Not ready** | Backend suite passes on reconciled branch; PostgreSQL 16 and live Claude provider validation remain unverified |

Percentages are weighted engineering estimates, not automated metrics. A partially implemented feature does not count as complete. The production verification percentage is intentionally lower than implementation because code presence is not proof of safe operation.

## Workstream scorecard

| Workstream | Done | Left | Current evidence / remaining work |
|---|---:|---:|---|
| Platform, API and data foundation | 70% | 30% | Modular FastAPI/Next.js foundation, PostgreSQL models, migrations, org/workspace scoping, core CRM and project records. Remaining: complete cross-domain invariants, performance/index review, migration rehearsal and stronger API contract coverage. |
| Founder authority, workforce and Claude runtime | 55% | 45% | Workforce hierarchy, 16 departments, positions, delegation, draft planning, Claude adapter, worker-mediated custom tools and exact workforce capability authorization. Remaining: PostgreSQL validation, budget reservation/usage ledger, provider live validation, session ambiguous-create reconciliation and Claude-side MCP adapter runtime validation if required. |
| Revenue engine | 48% | 52% | CRM, contact timeline, leads/opportunities, service catalogue, proposal/contract approval, onboarding, invoices/receivables foundations, research records and reviewed outreach drafts. Remaining: prospect discovery/enrichment, dedupe/merge workflow, consent/provenance, approved dispatch, stop conditions, campaign tracking, sales forecasting and attribution. |
| Delivery and client success | 55% | 45% | Projects, milestones, playbooks, onboarding, time/cost, scope changes, financial summaries and retainer usage-period ledger. Remaining: requirements traceability, acceptance evidence, independent QA/rework gates, release/handover, support, SLA measurement, client health and renewal/termination workflows. |
| Security and governance | 60% | 40% | Founder-only approvals, workspace scoping, autonomy policy, machine identity/session grants, DPG redaction, exact workforce tool grants and denial audit. Remaining: PostgreSQL lock/isolation verification, secrets/egress controls, retention/deletion and independent security review. |
| Automation and execution reliability | 55% | 45% | Persisted executions/attempts, leases, heartbeat/recovery, retries, outbox and execution-scoped idempotent Claude tool callbacks. Remaining: integration-wide reconciliation, dead-letter operations, cancellation, worker load tests and operational alerts. |
| Founder Console | 60% | 40% | Workforce, tasks, operations, approvals, CRM, proposals, contracts, onboarding, invoices, audit/monitoring, research/outreach and retainer page foundations. Remaining: integrated lifecycle views, tool/permission controls, finance and client-health views, accessible UX and end-to-end workflow polish. |
| Verification and operations | 28% | 72% | Reconciled branch full backend suite: 285 passed, 4 PostgreSQL-only skipped; compileall passed. Remaining: PostgreSQL 16 migrations/concurrency, frontend lint/static generation, tenant isolation, security scans, SBOM, backup restore, alerting, RPO/RTO and runbooks. |
| External integrations and configuration | 5% | 95% | Website intake is designed to be disabled until configured. Remaining: Claude production account/runtime, approved research sources, email/LinkedIn providers, telephony, object storage, secrets, webhook endpoints, domain/DNS and external legal/provider review. |

## Detailed delivery checklist

### 1. Platform and data foundation
- [x] Modular monolith architecture and separate Founder Console / public website boundary.
- [x] PostgreSQL-backed organization and workspace-scoped business records.
- [x] Core CRM, opportunity, project and milestone records.
- [x] Alembic migration framework and model registration.
- [ ] Verify all migrations from an empty PostgreSQL database and from the current deployed revision.
- [ ] Add database-level composite tenant constraints where practical, not only application filters.
- [ ] Review all list/detail/update/delete endpoints for consistent organization and workspace authorization.
- [ ] Add pagination cursors, query limits, indexes and performance budgets to high-volume endpoints.

### 2. Founder authority and AI workforce
- [x] Founder Authority separate from organization-owner membership.
- [x] Departments, teams, positions, workforce members and reporting hierarchy.
- [x] Capability grants, data-class limits, allowed actions, tool allowlists and budgets as registry fields.
- [x] Delegation lineage and persisted orchestration-plan drafts.
- [x] Mock runtime and isolated Claude Managed Agents adapter foundation.
- [x] Implement central Tool Registry with versioned JSON schemas and risk classification.
- [x] Implement per-agent, per-workspace and per-session tool grants, expiry and revocation, including exact workforce tool/action/data-class/scope checks.
- [x] Implement shared OS Tool Gateway: authenticate machine/session, validate schema, classify data, check workspace, workforce action/tool grants, execute registered adapter, persist result and audit.
- [ ] Complete per-execution budget reservation/settlement and approval adapters for approval-gated tools.
- [ ] Prevent provider runtime from receiving direct database credentials or unrestricted network access.
- [ ] Add session cancellation, expiry, retention, artifact cleanup and recovery.
- [ ] Add runtime adapter conformance tests and provider migration tests.

### 3. Revenue engine
- [x] Clients, contacts, contact activities, leads and opportunities.
- [x] Suppression stage and reason.
- [x] Service catalogue and proposal/contract approval foundations.
- [x] One-time and retainer terms in proposals/contracts (merged via PR #29).
- [x] Source-backed lead research records and founder-reviewed outreach drafts (merged via PR #29).
- [ ] Prospect discovery and enrichment adapters with source provenance, confidence and deduplication.
- [ ] Human-reviewed company/contact merge with audit and relationship preservation.
- [ ] Approved sender identities, consent/provenance registry, channel-specific permissions and suppression list.
- [ ] Dispatch authorization distinct from draft approval; idempotency keys and provider delivery receipts.
- [ ] Stop-on-reply, opt-out, bounce, complaint and manual stop; enforce rate limits and contact windows.
- [ ] Follow-up sequences with bounded retries and pre-authorized routine cadence only.
- [ ] Campaign, channel, conversion and revenue attribution.
- [ ] Discovery briefs, objection tracking, forecast and proposal revision/version history.

### 4. One-time and retainer delivery
- [x] Contract snapshots distinguish fixed-scope one-time work from recurring retainer terms (merged via PR #29).
- [x] Founder-governed retainer service periods, included hours, rollover calculation and usage snapshots (merged via PR #29).
- [x] Idempotent recurring invoice draft generation linked uniquely to a closed retainer period; founder approval is still required before issue (merged via PR #29).
- [x] Billable time entry requires an open period for active retainer projects; closed-period backdating is blocked at the API layer (merged via PR #29).
- [ ] Add concurrency and PostgreSQL locking tests for period close versus time entry creation.
- [ ] Add adjustment/correction workflow for erroneous time entries without mutating closed snapshots.
- [ ] Add founder approval for overage billability, rate and scope before any additional charge.
- [x] Generate recurring invoice drafts idempotently from closed periods and executed contract schedules; founder approval before issue.
- [ ] Add automated schedule runner, due-date policy and invoice reconciliation for missed/failed periods.
- [ ] Add SLA/response measurement with business calendars, exclusions and evidence.
- [ ] Add renewal decision queue, notice windows, price review and founder-approved renewal/termination.
- [ ] Add retainer pause/resume, service suspension and final handover/knowledge export.
- [ ] Complete one-time acceptance, warranty/support window and closure/handover lifecycle.

### 5. Delivery quality and client success
- [ ] Discovery records, requirements, decisions, assumptions and acceptance criteria with traceability to tests.
- [ ] Task and milestone dependencies, risks, change control and delivery forecasting.
- [ ] Independent QA/security review, rework loop and release-readiness evidence.
- [ ] Founder-approved production release and rollback evidence.
- [ ] Support requests, severity, response targets, escalation and resolution evidence.
- [ ] Client health scoring from grounded delivery, usage, feedback, support and commercial signals.
- [ ] Client update drafts and renewal recommendations; sensitive communications remain approval-gated.

### 6. Security, governance and privacy
- [ ] Data Protection Gateway for classification, minimization, PII detection/redaction and runtime eligibility.
- [ ] RBAC/ABAC and cross-workspace isolation tests for API, files, workers, sessions, caches and artifacts.
- [ ] Scoped credentials, secret rotation, egress allowlists, sandbox isolation and resource limits.
- [ ] Tamper-evident audit retention and access review.
- [ ] Approval consumption and protected action in one database transaction for all high-impact actions.
- [ ] Retention/deletion lifecycle for records, sessions, logs, backups and object artifacts.
- [ ] Threat model, abuse cases, dependency scanning, SBOM and independent security assessment.
- [ ] No compliance claim until eligibility, contracts, controls and independent evidence are verified.

### 7. Automation and operations
- [x] Durable execution records, attempts, leases, heartbeat and retry/recovery foundation.
- [x] Transactional outbox foundation with versioned events.
- [ ] Complete idempotency, deduplication, bounded retries, dead letters and reconciliation for every external adapter.
- [ ] Worker concurrency, lease-expiry, cancellation and crash-recovery tests.
- [ ] Event replay tooling with permission checks and audit.
- [ ] Metrics, logs, traces, cost budgets, alert routing and operational dashboards.
- [ ] Encrypted backups and a tested restore procedure; document RPO/RTO.
- [ ] Separate dev/staging/production configuration and controlled release process.
- [ ] Production runbooks for incident response, credential rotation, provider outage and data recovery.

### 8. External configuration — later phase
- [ ] Claude account, Managed Agents eligibility review, credentials and controlled tool/session setup.
- [ ] Research provider and source policy.
- [ ] Email provider, verified sender/domain, inbound reply/bounce/opt-out webhooks.
- [ ] LinkedIn workflow only through permitted/approved integration methods.
- [ ] Telephony provider, inbound/outbound policies, consent, recording policy and jurisdictional legal review.
- [ ] Object storage, encryption, retention and artifact access.
- [ ] Production secrets, webhook signing keys, domain/DNS and deployment configuration.
- [ ] Website signed-intake external secret/configuration and end-to-end verification.

## GitHub Actions quota strategy
- [x] Avoid repeated workflow reruns while quota is near exhaustion.
- [x] Review source, migration chain, route contracts and test fixtures before asking CI to run again.
- [ ] Consolidate the current PR changes and run local/static checks where available.
- [ ] Use one deliberate CI validation cycle when the branch is ready; do not merge if required jobs fail.
- [ ] If Actions quota is exhausted, use an approved local or alternate CI environment and preserve the exact logs/artifacts as evidence.

## Historical PR #28 / integration PR #29 — merged
- [x] Confirmed PR #28 was closed unmerged and its overlapping Revenue/Delivery work was reconciled through PR #29.
- [x] Confirmed PR #29 merged to main with the unified Alembic merge revision l2e8a0b6d549.
- [x] Confirmed the merged scope includes consent-governed outbound email preparation, source-backed research drafts, proposal catalogue snapshots, one-time/retainer terms, governed retainer periods and idempotent recurring invoice drafts.
- [x] Preserved the safety boundary: outbound email dispatch, contract signing, invoice sending, payment collection and automatic renewal remain disabled.
- [ ] Remaining PostgreSQL 16 tenant isolation/locking and external-provider dispatch gates are tracked in the active sections above; PR #29's validation is historical local evidence, not a fresh run against the exact remote commit.

## Definition of production-grade
A feature is **production-ready** only when implementation, authorization, tenant isolation, persistence, audit, failure recovery, tests, observability, retention and operational documentation are all evidenced. A schema, UI, action taxonomy or mocked adapter alone is a foundation, not a complete capability.


### 9. Governed agent skills and operating loops — reference integration
- [x] Audited FounderOS and AI-Native OS repository structures, selected skills, flows, loops, advisor patterns and dual-license model.
- [x] Added four independently authored, pinned-provenance skills: agentic build loop, operating loop design, connector security review and operational learning capture.
- [x] Kept all new skills disabled, public/synthetic-only and tool-free; no provider-side skills or runtime grants are enabled.
- [x] Documented candidate Revenue, Delivery, founder-review and permission-review loops with explicit gates and hard stops.
- [ ] Implement OS-owned skill assignment/version/expiry/revocation records with founder authorization and audit.
- [ ] Implement OS Tool Gateway and machine identities before any skill can call tools.
- [ ] Implement durable loop definitions, schedule/event triggers, budgets, recovery and independent evaluation before enabling loops.
- [ ] Pilot one read-only public/synthetic loop under supervised manual operation before scheduling.


## Consolidation sprint — 2026-11-25
- [x] Merge governed agent operating-model reference integration (PR #31) into main: `f8fc318cfece0dafb64a846d93fe7d78e64c5593`. The four new skills remain disabled, tool-free and public/synthetic-only; loops remain design artifacts, not active automation.
- [x] Harden PR #33 DPG metadata boundary: total serialized-size limit, string-only sanitized keys, redaction-key collision rejection, non-finite number rejection, and adversarial regression tests.
- [ ] Execute the expanded DPG unit tests and full backend suite on an available runner.
- [ ] Execute PR #33 tenant migration, preflight-abort fixture, cross-tenant insert tests, and upgrade/downgrade rehearsal on isolated PostgreSQL 16.
- [ ] Review ORM/migration parity and all existing production data before any populated-database migration.
- [ ] Complete tenant isolation audit beyond outreach tables (APIs, workers, files, sessions, caches and database row-level controls).
- [ ] Implement machine identities, session lifecycle, and OS Tool Gateway before enabling agent tool grants.
- [ ] Extend DPG to uploads, extracted documents, retrieval/RAG context, connector responses and tool inputs/outputs; add per-client policy/runtime eligibility.
- [ ] Implement durable OS-owned operating-loop execution, scheduler/event triggers, idempotent recovery, independent checks and founder approval gates.
- [ ] Complete signed provider webhooks, dispatch adapter, reply/opt-out/bounce reconciliation and end-to-end stop-condition tests before real outreach.
- [ ] Complete delivery QA/handover, support/SLA/renewal, finance reconciliation, backup restore, SBOM, monitoring/alerts and independent security review.
- [ ] Complete external configuration and synthetic end-to-end deployment verification for the website bridge and provider integrations.

**Release boundary:** PR #33 is open and unverified; PR #30 and PR #32 were closed as superseded; PR #33 is the current security candidate. GitHub Actions runner allocation is blocked by account billing; no Actions reruns were started. No claim of production readiness, live autonomous dispatch, or compliance is made.


- PR #30 was closed as superseded (not merged); PR #33 carries the tenant/DPG work on the current main head. Its branch is 10 commits ahead and 0 behind at the latest comparison; test and migration execution remain outstanding.
- Progress percentages remain at the last evidence-backed snapshot (52% internal implementation, 49% overall including integrations, 20% production verification, 5% external configuration). They are not increased for unmerged or unexecuted work.


## Development validation policy
- GitHub Actions is supplementary CI, not a prerequisite for implementation or independent testing.
- Run focused unit tests and backend suites in an available development environment; run database migration and tenant-isolation tests against disposable PostgreSQL before merge.
- Record exact commands, environment and results. Never mark tests complete from authored test files alone.
- PR #33 adds a second hardening pass: provider output identifiers and prior external run IDs are rejected if they contain PII/secrets; the provider run-ID persistence callback is wrapped so raw IDs cannot bypass the DPG; complete execution payload size is bounded before regex sanitization.


## PR #33 independent validation update — 2026-11-25
- [x] DPG and worker-service focused tests: 81 passed in an isolated local validation copy with PR #33 DPG/worker code and tests applied.
- [x] Execution API regression tests: 5 passed.
- [x] Action-policy tests: 11 passed.
- [x] Approval tests: 5 passed.
- [x] Execution-service tests: 12 passed.
- [x] Outreach API tests: 3 passed.
- [x] Python compile check: `python -m compileall -q app tests` passed.
- [x] SQLite migration rehearsal from `l2e8a0b6d549`: upgrade, downgrade, and re-upgrade to `m3f9c2a7e514` passed.
- [x] Preflight-abort fixture: existing cross-tenant contact/client mismatch stopped the migration before revision advancement.
- [x] All 16 deliberate cross-scope insert attempts were rejected by the migration-applied SQLite schema.
- [ ] PostgreSQL 16 migration and tenant-insert suite remains pending; SQLite is useful evidence but does not replace PostgreSQL validation.
- [ ] Full backend suite on the exact remote PR head remains pending.

**Validation note:** the local validation copy used the PR's current DPG, worker processor, focused regression tests and migration against the reconciled candidate base. Results are not claimed as CI results or as a full exact-head test run. PR #33 was merged to main as `09d23d90b258c55331367f94096bc6906cdce249`. CI is supplementary, not a development blocker.


**Merge status:** PR #33 is merged. The migration is in main but is not approved for application to populated production data until the isolated PostgreSQL 16 migration and mismatch-preflight tests pass.


## Latest implementation update — 2026-11-25 (PR #34 candidate)

- [x] PR #33 tenant-integrity and DPG hardening is merged to main as `09d23d90b258c55331367f94096bc6906cdce249`. Its outreach/CRM constraints and execution DPG coverage are implemented; PostgreSQL 16 and exact-main full-suite verification remain pending.
- [x] Added workspace-scoped machine identity records for agent, worker and service subjects, with founder-only issuance/revocation, high-entropy one-time credentials, SHA-256 digest storage, expiry, explicit scopes and synthetic/public-only data grants.
- [x] Added durable agent session records bound by composite organization/workspace/identity foreign key; session TTL is bounded to 60 seconds–24 hours and cannot outlive the identity.
- [x] Added machine bearer authentication, founder revocation that cancels active sessions, and a fail-closed tool/session authorization primitive. Identity and session rows are locked during session creation and tool authorization to serialize with revocation.
- [x] Added API and service regression coverage for one-time secret handling, invalid/expired/revoked credentials, founder-only issuance, data-class denial, session expiry bounds, tool scope enforcement and revocation cancellation.
- [x] Added migration `n4a7c2e91b60` after `m3f9c2a7e514`; SQLite parent-schema upgrade, downgrade and re-upgrade rehearsal passed.
- [x] Independent focused validation in the isolated reconciled candidate: 68 tests passed across machine identity (12), API (5), workforce (20), approvals (5), action policy (11), execution service (12) and outreach API (3). Python compile check passed after final lock hardening.
- [ ] PostgreSQL 16 migration and foreign-key enforcement verification for `n4a7c2e91b60`.
- [ ] Full backend suite on exact PR #34 head; local candidate validation is not the exact remote branch.
- [ ] Implement actual Tool Registry and invocation records, input/output DPG at dispatch, approval and budget enforcement, sandboxed adapters, durable invocation outcomes and audit. The current `authorize_tool_session` function does not execute tools.
- [ ] Implement scheduled session expiry/retention cleanup, artifact cleanup, cancellation propagation and recovery.
- [ ] Do not provision production credentials or enable real agent tool access until the remaining gateway and PostgreSQL release gates pass.

**Estimate policy:** The percentages above remain the previous evidence-backed snapshot and have not been recalculated for this candidate. This PR is implementation work, not a production-readiness or deployment approval.


**Full-suite validation boundary:** A full `pytest -q tests` attempt in the isolated candidate timed out after reaching approximately 56% progress. Do not claim a full-suite pass. The focused test modules above completed in separate invocations and passed.


## OS Tool Gateway update — 2026-11-25 (PR #35 merged)

- [x] Added a versioned, code-owned Tool Registry with typed input/output contracts, risk level, allowed data classes and approval metadata.
- [x] Added a machine-authenticated Tool Gateway. It requires the exact active identity/session, workspace scope, data-class eligibility, `tools:invoke` and exact per-tool grant.
- [x] Added DPG protection for decoded tool input and typed tool output; raw secret-like input is rejected before adapter execution.
- [x] Added durable `ToolInvocation` records with sanitized input/result, request hash, idempotency key, session/identity scope and completion timestamp.
- [x] Added organization/workspace-scoped unique idempotency and request binding to identity, session, tool version and sanitized input.
- [x] Added success audit records with tool/version/session/data class and redaction counts only.
- [x] Registered one deliberately narrow read-only tool: `system.health.read` (database `SELECT 1`; no client records or external side effects).
- [x] Added API tests for registry filtering, successful invocation, durable persistence/audit, idempotent replay, cross-session idempotency conflict, missing grants, unknown tools, schema rejection and secret blocking.
- [x] Added migration `o5c3d9e1f742`; SQLite rehearsal from `m3f9c2a7e514` through `n4a7c2e91b60` to `o5c3d9e1f742`, downgrade to `n4a7c2e91b60`, and re-upgrade passed.
- [x] Alembic reports one head: `o5c3d9e1f742`; Python compile check passed.
- [x] Independent focused validation in the isolated candidate: 17 machine identity/session/tool gateway tests, 5 API tests, 20 workforce tests, 5 approval tests, 11 action-policy tests, 12 execution-service tests and 3 outreach API tests passed in separate invocations (**73 total**).
- [ ] PostgreSQL 16 migration and composite foreign-key verification for both new migrations.
- [ ] Full backend suite on the exact remote PR #35 head. A previous full-suite attempt in the isolated candidate timed out around 56%; no full-suite pass is claimed.
- [ ] Expand the registry with approved Revenue/Delivery tools only after per-tool data policies, approval consumption, budgets, async execution/outbox, cancellation/reconciliation and end-to-end isolation tests exist.
- [ ] Add session expiry scheduler, retention/deletion, artifact cleanup and operational recovery.

**Current gateway boundary:** only `system.health.read` is executable. This PR does not enable client-data tools, provider-side MCP, arbitrary shell/network access, outbound communications, payments or other side effects. It is a secure invocation foundation, not yet the complete autonomous Revenue/Delivery toolset.


## Session lifecycle worker update — 2026-11-25

- [x] Added `expire_due_agent_sessions`: bounded batch size (1–1000), due-time filtering, deterministic ordering, row locking with `SKIP LOCKED`, status transition to expired, end timestamp and per-session audit event.
- [x] Integrated expiry sweeps into the existing worker maintenance interval in a separate committed transaction; the existing execution and outbox maintenance transactions remain separate.
- [x] Added worker-runner tests for the separate expiry transaction and service/API tests for audited session expiry.
- [x] Latest isolated-candidate focused validation totals **136 passed**: machine identity/tool gateway 18, worker runner 7, worker service 55, API 5, workforce 20, approvals 5, action policy 11, execution service 12 and outreach API 3. Modules were run in separate pytest invocations.
- [x] Python compile check passed; Alembic reports one head `o5c3d9e1f742`.
- [ ] Session retention/deletion, artifact cleanup, recovery of interrupted long-running tool sessions and PostgreSQL 16 row-lock/FK verification remain outstanding.
- [ ] Full backend suite on exact remote PR #35 head remains unverified; a previous full-suite attempt in the isolated candidate timed out around 56%.


## Main branch merge confirmation — 2026-11-25

- [x] PR #34 merged to main with merge commit `0434b62d580db051b597863f9f14b53848d1752b`: founder-governed machine identities, one-time credentials, workspace-bound sessions, session purpose DPG and authorization primitives.
- [x] PR #35 merged to main with squash commit `e1369ef928378c132391d4883d485c525849441d`: typed allowlisted Tool Registry, scoped idempotent Tool Gateway, durable invocation records, DPG input/output, success audit and worker-driven session expiry.
- [x] Current main contains the new Alembic head `o5c3d9e1f742` (PR #34 revision `n4a7c2e91b60` followed by PR #35 revision `o5c3d9e1f742`).
- [x] Independent focused validation on the isolated reconciled candidate: 136 tests passed across nine modules; compile check and SQLite migration upgrade/downgrade/re-upgrade passed. These are not tests on the exact remote main checkout.
- [ ] PostgreSQL 16 migration and composite FK/row-lock verification remains outstanding. Do not apply these migrations to populated production databases until verified.
- [ ] Full backend suite on exact main remains unverified; the isolated candidate full-suite attempt timed out around 56%. No full-suite pass is claimed.
- [ ] Only `system.health.read` is executable in the Tool Registry. Revenue/Delivery business tools, approvals, budgets, sandboxed provider adapters and async external side effects remain unimplemented.
- [ ] Session retention/deletion, artifact cleanup, backup/restore and operational recovery remain outstanding.
- [ ] No production deployment or external provider configuration was performed by these merges.


## Revenue agent research capture — 2026-11-25 (PR #36 candidate)

- [x] Added a public-data-only `revenue.lead.research.capture` tool with typed schema, source references, fit/confidence scores, buying signals and risks.
- [x] Rejects arbitrary extra/contact fields, duplicate source references, non-HTTPS URLs, embedded credentials, local/private hosts, private/reserved IPs and invalid ports. The tool stores supplied source references; it does not fetch or verify them.
- [x] Applies DPG to the decoded input before validation and persistence; PII patterns are redacted and secret-like values are blocked.
- [x] Persists `LeadResearchDraft` records with workspace and machine-identity composite scope, idempotency key and pending-review status. Agent capture does not create CRM contacts or leads.
- [x] Added Founder Authority-only list, approve/reject and explicit promote routes. Rejected drafts cannot be promoted; only approved drafts can be promoted; repeat promotion returns the existing lead.
- [x] Promotion creates the CRM `Lead` and `LeadResearchRecord` in one transaction, attributes the CRM write to the approving founder and audits the transition.
- [x] Added migration `p6d8e2a4f913` with scoped foreign keys, idempotency uniqueness and score/status checks.
- [x] Added tests for research capture, source validation, DPG redaction, contact-field rejection, founder-only review, reject gate and idempotent promotion.
- [x] Independent focused validation in the isolated candidate: **196 tests passed** across 15 modules (machine/revenue research 25, worker runner 7, worker service 55, API 5, workforce 20, approvals 5, action policy 11, execution 12, outreach 3, operations 28, outbox 7, Revenue/Delivery 6, telephony 5, website intake 4, evaluation 1).
- [x] Python compile check passed; Alembic reports one head `p6d8e2a4f913`; SQLite upgrade/downgrade/re-upgrade rehearsal through all three new migrations passed.
- [ ] PostgreSQL 16 verification and full backend suite on exact PR #36 head remain pending. A previous full-suite attempt in the isolated candidate timed out around 56%; no full-suite pass is claimed.
- [ ] Founder UI for reviewing/promoting drafts, actual public-source discovery connectors, cross-source company deduplication and additional Revenue/Delivery tools remain outstanding.
- [ ] Commercial/client data grants, outbound communication, pricing, contracts, payments and other side-effecting tools remain blocked pending client policy, approvals, budgets, consent/suppression and asynchronous recovery controls.

**Revenue capability boundary:** this is the first operational agent write tool, but it captures public research as a review draft. It does not itself browse the web, verify source truth, add contacts, send outreach or autonomously promote CRM records.


## Revenue agent research merge confirmation — 2026-11-25

- [x] PR #36 merged to main as squash commit `844d2d6b14f537b53d05f5e56aaba69b248329c0`.
- [x] Main now includes the public-only Revenue research capture tool, DPG-protected source-backed drafts, founder-only review/rejection and explicit idempotent CRM promotion.
- [x] Alembic head is now `p6d8e2a4f913`, following `n4a7c2e91b60` and `o5c3d9e1f742`.
- [x] Independent isolated-candidate validation: 196 focused tests passed across 15 modules; Python compile check passed; SQLite upgrade/downgrade/re-upgrade through all three new migrations passed.
- [ ] PostgreSQL 16 verification, full backend suite on exact main, and production migration review remain pending.
- [ ] Founder UI for draft review/promotion and actual public-source research connectors remain outstanding. The tool stores source references supplied by an agent and does not independently verify them.
- [ ] Further Revenue/Delivery tools, client-data eligibility, approval/budget integration, external adapters, retention/deletion and recovery remain outstanding.
- [ ] No production deployment or external outreach was performed.


## Current continuation checkpoint — 2026-11-25

### Founder research review UI — PR #39 (rebased successor to PR #37)
- [x] PR #37 adds the Founder Console `/research-drafts` page, workspace/status filters, evidence/source display, approve/reject notes and explicit CRM promotion.
- [x] The UI keeps approval and CRM promotion as separate founder actions; it does not create contacts or send outreach.
- [ ] Frontend dependency installation, TypeScript check and production build remain unverified.
- [ ] Prior PR #37 Actions run (run `45630633706`) did not execute job steps; both jobs are marked failed and the account billing/spending-limit block must be resolved before CI can provide evidence.
- [x] PR #39 merged to `main` after fixing the two actionable async UI review findings. PR #37 remains closed as superseded.
- [ ] Full frontend lint, TypeScript check and production build are still unverified; the corrected PR head had no workflow run, and the previous Actions attempt was blocked by account billing/spending limits. Treat the UI as merged but not fully build-verified.

### Claude Managed Agents tool bridge — custom-tool path design
- [x] Audited the current Tool Registry, REST gateway, machine identity/session model and Managed Agents adapter.
- [x] Documented the OS-worker-mediated Managed Agents custom-tool path and retained the MCP connector as a deferred alternative.
- [ ] Add session-bound bearer credentials (digest-only persistence, expiry/revocation, exact session scope).
- [ ] Refactor the current REST Tool Gateway into one shared invocation service for REST and Managed Agents custom-tool callbacks.
- [ ] Add execution/session-bound custom-tool dispatch in the worker; keep provider tool definitions exact and version-pinned.
- [ ] Enforce WorkforceCapability grants, machine identity scopes, data class, action policy and budget on every callback.
- [ ] Add idempotent replay across provider retries and OS session renewal; reconcile missing tool results and worker crashes.
- [ ] Complete unit, PostgreSQL 16, cross-workspace isolation, duplicate-call, stale-lease, revocation, crash-recovery and synthetic end-to-end tests before enabling.
- [ ] First pilot is limited to `system.health.read` and public-only `revenue.lead.research.capture`; no CRM promotion, contacts, outbound dispatch, payments or production actions.

**Current verified boundary:** The main branch has a REST Tool Gateway; the Managed Agents adapter still rejects provider custom tools and MCP servers. No provider tools have been enabled and no runtime code or production configuration has changed. The first implementation candidate is worker-mediated custom tools; MCP endpoint/vault work is deferred.


## Founder research review UI — 2026-11-25 (merged PR #39)

- [x] Added `/research-drafts` to the Founder Console and sidebar navigation in PR #39.
- [x] Added workspace/status filtering, evidence and source-reference display, fit/confidence scores, review notes, approve/reject actions and explicit CRM promotion for approved drafts.
- [x] UI explains that source URLs are agent-supplied and unverified, and that no contact or outreach action occurs.
- [x] TSX syntax parsing passed for the new page and updated sidebar.
- [ ] Full Next.js lint, typecheck and production build remain unverified. The isolated environment has no frontend dependencies; `npm install` timed out, so no build success is claimed.
- [x] PR #39 merged to `main` after review-finding fixes.
- [ ] Full frontend dependency install, lint, TypeScript check and Next build remain pending; no successful full build is claimed.


## Stabilization branch reconciliation — 2026-11-25

- [x] Fetched and compared `origin/feature/agency-os-v5-stabilization` against current `main` at `20f57af4bff2409ea9721da3168f742cbc3da279`.
- [x] Confirmed the branch has 32 commits on its side of the merge-base comparison, but its direct tree comparison against main would change 269 files with approximately 7,292 insertions and 18,811 deletions. This is not a safe merge candidate.
- [x] Confirmed the signed website lead-intake route and its tests are already present on main with identical Git blob SHAs; the workforce console page is also identical.
- [x] Confirmed main contains a more extensive workforce API implementation, including founder-governed capability activation/pause, runtime/data-class checks, delegation and orchestration-plan support. The branch's older route/model/test versions must not replace it.
- [x] Confirmed main registers both website-intake and workforce routers. The current workforce API also explicitly blocks tool grants until an OS-managed runtime tool bridge exists.
- [x] Decision: do not merge or rebase the stabilization branch wholesale and do not cherry-pick its historical commits without a fresh per-feature comparison. High-value workforce/intake capabilities are already present or superseded on main.
- [ ] Keep the old branch as a reference until a separate, commit-by-commit audit is complete; no branch deletion, force-push or destructive cleanup was performed.
- [ ] Continue implementation from current main. The custom-tool callback bridge remains a design-only milestone; worker dispatch, workforce capability enforcement, retry-safe replay and contract/isolation/recovery tests are still outstanding. MCP endpoint/token/vault work is deferred.

**Validation boundary:** this was a Git-tree/source comparison through GitHub. No local tests, frontend build, PostgreSQL migration rehearsal or CI run was performed as part of this branch audit.


## Managed Agents tool transport decision review — 2026-11-25

- [x] Reviewed the unmerged `feature/managed-agent-os-tool-execution` implementation against current main and Anthropic's documented custom-tool event flow.
- [x] Recorded the preferred first integration: OS-worker-executed Managed Agents custom tools, with no public MCP endpoint or provider-held OS bearer token.
- [x] Selected worker-mediated Managed Agents custom-tool callbacks as the first native Claude tool transport.
- [x] Selected a thin Claude-side MCP protocol adapter only when the Claude experience requires MCP; it must call the same OS Tool Gateway and must not own permissions or business state.
- [x] Ported the shared invocation service and execution-scoped custom-tool callback onto a branch reconciled with current main.
- [x] Enforced exact enabled WorkforceCapability grants (tool key, required action, data class and minimum scope) in addition to machine identity/session scopes.
- [x] Added stable execution-scoped idempotency so provider retries survive OS session renewal while live session authorization is rechecked before replay.
- [x] Added paused-member and disabled-grant denial tests, session-renewal replay coverage, DPG internal-ID allowlist tests and workforce grant activation/scope tests.
- [ ] PostgreSQL 16 locking/migration, populated-schema upgrade/downgrade and production recovery validation remain release gates.
- [ ] Keep provider tools disabled until live provider compatibility, ambiguous session-create reconciliation and founder-approved synthetic pilot are complete.

**Evidence boundary:** the reconciled branch full backend suite passed 285 tests, with 4 PostgreSQL-only tests skipped because `AGENCY_OS_TEST_DATABASE_URL` was not configured. `q7f2b9d4c631` is the sole Alembic head. A SQLite full-history migration rehearsal stopped at the pre-existing `eb75d47bfc63` migration, which uses an ALTER constraint operation unsupported by SQLite; this did not validate or invalidate the new PostgreSQL migration. No PostgreSQL 16 or live Managed Agents session was available, and no provider tool is enabled in production.

### PR #45 reconciled implementation notes (merged to main)

## 2026-11-25 — Managed Agents OS custom-tool execution

- [x] Shared OS tool invocation service is implemented on `feature/managed-agent-os-tool-execution` and reused by the HTTP gateway and worker callback.
- [x] Worker callback binds tool use to the current execution, worker attempt and unexpired lease.
- [x] Provider Agent is revalidated on new and resumed attempts; only exact OS-registry custom-tool definitions are allowed.
- [x] Tool calls use OS machine identity/session grants, DPG, schema validation, idempotency, persisted invocation results and audit.
- [x] Custom tool call/result handling is bounded; native provider tools, MCP, skills and multiagent features remain disabled.
- [x] Reconciled PR branch with current `main` and resolved the two source conflicts without dropping the main-branch research review UI or tests.
- [x] PR #45 merged to `main` (confirmed in GitHub).
- [x] Exact reconciled branch focused validation passed 154 tests; full backend suite passed 285 tests with 4 PostgreSQL-only skips.
- [x] Corrected a main-branch `LeadResearchDraft.promoted_lead_id` ORM/migration mismatch exposed during test collection.
- [x] Added tool-level workforce capability enforcement and stable execution idempotency across session renewal.
- [x] Alembic graph reports `q7f2b9d4c631` as the single head.
- [ ] Verify migration `q7f2b9d4c631` on PostgreSQL 16, including upgrade/downgrade and populated-schema checks.
- [ ] Configure the exact custom-tool definitions on the pre-created Claude Managed Agent and provision an agent machine identity with least-privilege scopes.
- [ ] Run synthetic end-to-end tests against the live Managed Agents provider; verify execution, tool authorization, persistence, replay, denial audit and recovery.
- [ ] Complete provider session ambiguous-create reconciliation and production recovery before unattended rollout.

**Evidence boundary:** 285 backend tests passed on the reconciled cloud branch; 4 PostgreSQL integration/concurrency tests were skipped without a configured PostgreSQL test database. `compileall` passed. Frontend Next.js compilation and TypeScript validation passed, but static page generation terminated with an environment `EAGAIN` process-spawn error. ESLint could not run because the repository has no ESLint v9 flat config. PostgreSQL 16, live provider compatibility and production configuration remain unverified.


Additional review controls: identity/session locks follow revocation lock order; policy denials are generic to the model while unexpected gateway/database failures enter worker retry; internal-ID PII exemptions are limited to explicit draft/lead/research-record fields. The current tools do not yet perform autonomous web search, web fetch or prospect discovery; supplied research references remain unverified.


## 2026-11-25 — Department map and Claude workforce boundary

- [x] Confirmed the canonical organization registry contains 16 departments, 5 group heads, 22+ teams and 80+ positions; workforce bootstrap tests assert the 16-department structure.
- [x] Documented the SkillTree's eight radial labels as presentation clusters over the 16 canonical departments; the visual clusters do not merge department responsibilities or permission scopes.
- [x] Documented Claude as the workforce interaction/runtime layer and Agency OS as the authority for identity, grants, business records, budgets, approvals and audit.
- [x] Documented MCP as a thin Claude-side protocol adapter when required; it must call the OS Tool Gateway and cannot become a second authorization or execution system.
- [ ] Reconcile the external SkillTree/brain report once its Google Doc content is supplied in an inspectable file. The supplied Google Docs URL could not be opened through an available Drive connector in this environment.


## 2026-11-25 — 20-point pre-deploy security audit

- [x] Audited all 20 controls against the reconciled branch; detailed findings, file/line evidence, severities and required patches are in `docs/PRE_DEPLOY_SECURITY_AUDIT_20_POINT.md`.
- [x] Updated Next.js and matching ESLint config to 15.5.29; pinned PostCSS 8.5.33 and Sharp 0.35.5; committed npm lockfile; `npm audit` reports zero vulnerabilities.
- [x] Moved pytest out of runtime requirements into `requirements-dev.txt` and upgraded to pytest 9.0.3; `pip-audit` reports no known vulnerabilities in runtime or development requirements.
- [x] Explicitly disabled production browser source maps in `frontend/next.config.ts`.
- [ ] Production authentication/session lifecycle, MFA, localStorage removal, PostgreSQL RLS, general rate limiting, safe production defaults, route-wide authorization matrix, full SSRF egress controls and centralized log scrubbing remain release blockers.
- [ ] Complete PostgreSQL 16 test suite, ESLint flat config and full frontend production build; perform independent security review and secret-history scan.

**Security release decision: NO-GO.** Dependency vulnerabilities found by this audit were patched, but the critical identity, RLS and verification gaps remain. See `docs/PRE_DEPLOY_SECURITY_AUDIT_20_POINT.md` for all 20 controls and evidence boundaries.


## 2026-11-25 — Security hardening continuation

- [x] Production startup validation now fails closed for dev auth, mock runtime, weak JWT/database passwords, SQLite, non-TLS Redis, wildcard/non-HTTPS CORS, disabled rate limiting and untrusted Claude API base URLs.
- [x] Added Redis-backed per-minute request throttling for auth, expensive and general API routes; production returns 503 if Redis is unavailable and 429 with Retry-After when limited.
- [x] Removed localStorage/sessionStorage bearer-token persistence; development override is memory-only and hidden in production.
- [x] Removed insecure Docker Compose database-password fallback; POSTGRES_PASSWORD is required.
- [x] Added ESLint 9 flat config; lint completes with 0 errors (7 existing hook dependency warnings).
- [x] Production frontend build passes and generates all 31 static pages; build worker count constrained to one to avoid EAGAIN in cloud environments.
- [x] Backend full suite: 296 passed, 4 PostgreSQL-only tests skipped.
- [ ] Production identity provider/session lifecycle and MFA still not implemented; no password auth should be added without selecting the identity architecture.
- [ ] PostgreSQL 16 RLS and non-owner runtime role still not implemented or verified.
- [ ] Redis integration/load tests, trusted-proxy setup, SSRF egress controls, complete route authorization review, log redaction, secret-history scan and deployment/restore review remain.

**Security release decision remains NO-GO** until identity/MFA and PostgreSQL RLS are implemented and verified. Full evidence is in `docs/PRE_DEPLOY_SECURITY_AUDIT_20_POINT.md`.


## 2026-11-25 — Authentik OIDC integration

- [x] Added Authentik OIDC relying-party adapter using Authlib discovery and Authorization Code flow with PKCE S256, state and nonce handling.
- [x] Production config requires issuer, client ID/secret, independent OIDC state secret, HTTPS callback and frontend URLs.
- [x] Only verified email + issuer + subject may bind to an already provisioned active Agency OS user; no JIT users, memberships or role grants.
- [x] Added unique issuer-subject mapping and Alembic migration `r8a2c4e6f901`.
- [x] Added HttpOnly browser session cookie, short expiry, logout, current identity and no-store CSRF bootstrap endpoint.
- [x] Added double-submit CSRF and allowlisted Origin enforcement for cookie-authenticated unsafe methods; bearer service calls remain unaffected.
- [x] Frontend uses credentialed requests and keeps CSRF material in memory only; Authentik login/logout actions added to settings.
- [x] OIDC identity and CSRF unit tests pass; full backend suite 320 passed, 4 PostgreSQL-only skipped.
- [ ] Provision Authentik provider/client and configure secrets/callback in deployment. No live OIDC flow has been run.
- [ ] Enforce/verify `acr`/`amr` MFA assurance for founder/admin; configure phishing-resistant MFA in Authentik.
- [x] Add a persistent browser-session/token revocation ledger in the follow-up candidate below; production browser/Safari same-site verification remains pending.
- [ ] PostgreSQL 16 RLS/non-owner runtime role and integration tests remain a critical release blocker.

**Release decision remains NO-GO** pending live Authentik/MFA assurance and PostgreSQL RLS verification.

- [x] Replaced Starlette's signed-only OIDC state cookie with AES-GCM authenticated encryption for the PKCE verifier and nonce; tests prove round-trip and reject tampered state cookies.


## 2026-11-25 — Continuation source review

- [x] Rechecked PR #47 metadata and exact changed-file set; PR #47 remains open and draft. No merge or Actions run was triggered.
- [x] Re-reviewed OIDC session, CSRF, rate-limit and migration source. The current browser session is a stateless short-lived JWT; logout clears cookies but does not revoke a copied token before expiry.
- [x] Added a PR review comment documenting the required persisted session/JTI revocation and rotation lifecycle, PostgreSQL 16 RLS/runtime-role requirements, Claude parent/child execution controls and live Authentik assurance verification.
- [x] Implement and test the server-side session ledger in the follow-up candidate below; logout revokes server-side and replay fails immediately in isolated API tests.
- [ ] Implement and verify PostgreSQL 16 RLS with a non-owner/non-BYPASSRLS application role, transaction-local tenant context and pooled-connection isolation tests.
- [ ] Implement durable Claude child-execution correlation, per-child budgets and exact grants, cancellation and provider-event reconciliation before enabling multiagent or side-effecting workflows.
- [ ] Complete live Authentik OIDC/JWKS/ACR and browser cookie verification.
- [ ] Complete remaining route authorization, SSRF egress, log redaction, secret-history and backup/restore gates.

**Evidence boundary:** GitHub source review and PR metadata were available. The cloud development workspace could not establish TLS to GitHub, so no source code was modified and no tests were rerun during this continuation. Existing test counts above are historical branch evidence, not fresh verification.


## Repository history reconciliation — 2026-11-25

- [x] Verified PR #28 is closed without merge; do not treat it as the integration commit.
- [x] Verified PR #29 is merged and reconciles the Revenue/Delivery work previously split across PRs #25, #26 and #28.
- [x] Compared the four proposal/research/retainer migration blobs on PR #28's branch with main; all four are byte-identical on main.
- [x] Compared the Retainer Operations and Research/Outreach UI paths; the Retainer page is identical and the Outreach page has since evolved on main.
- [x] Corrected this checklist's historical references to identify PR #29 as the merged integration and PR #45 as the merged Claude custom-tool milestone.


## 2026-11-25 — Persistent browser-session revocation candidate

- [x] Added `browser_sessions` with a unique SHA-256 digest of JWT `jti`, user binding, expiry, revocation timestamp and indexed lookup/expiry fields; the raw token and raw `jti` are not persisted.
- [x] OIDC callback creates the browser session record and creation audit events before returning the HttpOnly cookie.
- [x] Cookie and signed bearer presentations of browser JWTs now require a live persistent session record, active user and matching subject; dev-only `dev:` bearer tokens retain their existing non-production path.
- [x] Logout revokes only the current session, records per-organization audit events in the same database transaction and remains idempotent; copied cookie and bearer-token replay are rejected.
- [x] Added `POST /v1/auth/refresh` to atomically lock/revoke the old session, issue a replacement, record the replacement ID in audit and commit before returning the new HttpOnly cookie.
- [x] TDD regression suite: **11 focused browser-session tests passed**, including API logout/replay, bearer replay, inactive user, persistent expiry, digest-only storage, repeated revocation and refresh rotation.
- [x] Full backend suite on this worktree: **332 passed, 4 PostgreSQL-only skipped**.
- [x] New Alembic revision `s9b5d7f1a204` is the single migration head; isolated upgrade from `r8a2c4e6f901` to the new revision passed on SQLite and verified table columns/indexes.
- [ ] Full historical SQLite migration rehearsal still stops at pre-existing revision `eb75d47bfc63` (unsupported SQLite ALTER constraint operation); this does not verify the new migration on PostgreSQL. Run PostgreSQL 16 populated-schema upgrade/downgrade before merge.
- [ ] Wire proactive refresh into the frontend client and verify it under the actual browser topology; PostgreSQL row-lock concurrency testing for simultaneous refresh remains outstanding.
- [ ] Scheduled retention/deletion, artifact cleanup, Safari same-site cookie verification, Authentik live MFA/ACR verification and PostgreSQL 16 RLS remain outstanding.



## 2026-11-25 — Route authorization inventory guard

- [x] Added `tests/test_route_auth_inventory.py`: every registered FastAPI API route must depend on the authenticated human principal or machine principal, unless it is in the explicit public/cookie-session allowlist.
- [x] Explicit public exceptions are limited to OIDC login/callback/CSRF bootstrap, development-only token issuance, health and signed website intake. Logout and refresh are separately allowlisted only as cookie-session handlers and require the installed double-submit CSRF middleware.
- [x] The route inventory guard passes; it is included in the full backend result of **332 passed, 4 PostgreSQL-only skipped**.
- [ ] This structural guard does not prove resource-level authorization. Complete the semantic route-by-route organization/workspace/role matrix and negative cross-tenant tests before production.

**Evidence boundary:** source was cloned from public branch `security/predeploy-20-point-audit` at `730b10fb00206afbd02f6f49e17ad3ba8e431a95`. Tests ran in Upstash Box `certain-whale-42014` on Python 3.13.18. Changes were published to the existing draft PR #47 branch; PR #47 remains open/draft and unmerged. No GitHub Actions workflow was triggered.
