# Agency OS Production Readiness Checklist

**Last reviewed:** 2026-11-25  
**Tracking branch:** `feature/engagement-models-agentic-workflows`  
**Current integration PR:** [#28](https://github.com/AsaifAli/agency-native-agency-os/pull/28)  
**Status:** Working estimate — not a certification or release approval.

## Progress snapshot

| Measure | Estimate | Meaning |
|---|---:|---|
| Internal implementation | **52%** | Share of planned internal code capability implemented or substantially scaffolded |
| Overall scope including external integrations | **49%** | Includes provider setup, credentials, legal review and production operations |
| Production verification | **20%** | Evidence from tests, CI, security review, migration rehearsal and recovery drills |
| External configuration | **5%** | Only limited setup is evidenced; most providers remain unconfigured |
| Release readiness | **Not ready** | Current PR is unmerged and its new code has not passed a fresh validation run |

Percentages are weighted engineering estimates, not automated metrics. A partially implemented feature does not count as complete. The production verification percentage is intentionally lower than implementation because code presence is not proof of safe operation.

## Workstream scorecard

| Workstream | Done | Left | Current evidence / remaining work |
|---|---:|---:|---|
| Platform, API and data foundation | 70% | 30% | Modular FastAPI/Next.js foundation, PostgreSQL models, migrations, org/workspace scoping, core CRM and project records. Remaining: complete cross-domain invariants, performance/index review, migration rehearsal and stronger API contract coverage. |
| Founder authority, workforce and Claude runtime | 40% | 60% | Workforce hierarchy, departments/teams/positions, capability grants, delegation, draft planning, mock runtime and opt-in Claude Managed Agents adapter. Remaining: production tool gateway, per-tool authorization, runtime/session lifecycle hardening, budget enforcement and provider integration verification. |
| Revenue engine | 48% | 52% | CRM, contact timeline, leads/opportunities, service catalogue, proposal/contract approval, onboarding, invoices/receivables foundations, research records and reviewed outreach drafts. Remaining: prospect discovery/enrichment, dedupe/merge workflow, consent/provenance, approved dispatch, stop conditions, campaign tracking, sales forecasting and attribution. |
| Delivery and client success | 55% | 45% | Projects, milestones, playbooks, onboarding, time/cost, scope changes, financial summaries and retainer usage-period ledger. Remaining: requirements traceability, acceptance evidence, independent QA/rework gates, release/handover, support, SLA measurement, client health and renewal/termination workflows. |
| Security and governance | 55% | 45% | Founder-only approval patterns, single-use approvals, workspace scoping, autonomy classification, synthetic-only Managed Agents policy and audit/outbox foundations. Remaining: comprehensive Data Protection Gateway, tenant isolation test matrix, scoped tool credentials, secrets/egress controls, retention/deletion and independent security review. |
| Automation and execution reliability | 50% | 50% | Persisted executions/attempts, leases, heartbeat/recovery, retries, outbox and selected event dispatch. Remaining: complete idempotency/reconciliation across integrations, dead-letter operations, cancellation, replay, worker load tests and operational alerts. |
| Founder Console | 60% | 40% | Workforce, tasks, operations, approvals, CRM, proposals, contracts, onboarding, invoices, audit/monitoring, research/outreach and retainer page foundations. Remaining: integrated lifecycle views, tool/permission controls, finance and client-health views, accessible UX and end-to-end workflow polish. |
| Verification and operations | 20% | 80% | Main has previously passed a backend suite and frontend type/build checks. Current PR #28 has not passed fresh validation. Remaining: PostgreSQL migration tests, backend/frontend CI, tenant isolation, security scans, SBOM, backup restore drill, alerting, RPO/RTO and runbooks. |
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
- [ ] Implement central Tool Registry with versioned JSON schemas and risk classification.
- [ ] Implement per-agent, per-workspace and per-session tool grants, expiry and revocation.
- [ ] Implement an OS tool gateway: authenticate actor/session, validate schema, classify data, check workspace, action policy, budget and approval, execute adapter, persist result and audit.
- [ ] Prevent provider runtime from receiving direct database credentials or unrestricted network access.
- [ ] Add session cancellation, expiry, retention, artifact cleanup and recovery.
- [ ] Add runtime adapter conformance tests and provider migration tests.

### 3. Revenue engine
- [x] Clients, contacts, contact activities, leads and opportunities.
- [x] Suppression stage and reason.
- [x] Service catalogue and proposal/contract approval foundations.
- [x] One-time and retainer terms in proposals/contracts (PR #28, unmerged).
- [x] Source-backed lead research records and founder-reviewed outreach drafts (PR #28, unmerged).
- [ ] Prospect discovery and enrichment adapters with source provenance, confidence and deduplication.
- [ ] Human-reviewed company/contact merge with audit and relationship preservation.
- [ ] Approved sender identities, consent/provenance registry, channel-specific permissions and suppression list.
- [ ] Dispatch authorization distinct from draft approval; idempotency keys and provider delivery receipts.
- [ ] Stop-on-reply, opt-out, bounce, complaint and manual stop; enforce rate limits and contact windows.
- [ ] Follow-up sequences with bounded retries and pre-authorized routine cadence only.
- [ ] Campaign, channel, conversion and revenue attribution.
- [ ] Discovery briefs, objection tracking, forecast and proposal revision/version history.

### 4. One-time and retainer delivery
- [x] Contract snapshots distinguish fixed-scope one-time work from recurring retainer terms (PR #28, unmerged).
- [x] Founder-governed retainer service periods, included hours, rollover calculation and usage snapshots (PR #28, unmerged).
- [x] Idempotent recurring invoice draft generation linked uniquely to a closed retainer period; founder approval is still required before issue (PR #28, unmerged).
- [x] Billable time entry requires an open period for active retainer projects; closed-period backdating is blocked at the API layer (PR #28, unmerged).
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

## Current PR #28 release gate
- [ ] Confirm migration graph has one head and PostgreSQL upgrade succeeds from main.
- [ ] Run backend tests, including new research/outreach and retainer period tests.
- [ ] Run frontend TypeScript check and production build.
- [ ] Test retainer period closeout under PostgreSQL transaction locking.
- [ ] Test organization/workspace isolation for every new endpoint.
- [ ] Confirm no send/dispatch, payment, renewal or external call side effect exists.
- [ ] Obtain successful required CI checks and code review.
- [ ] Merge only after all gates pass.

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
