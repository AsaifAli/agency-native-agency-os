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

## Post-merge hardening gates
- [x] Consolidated revenue feature migrations are merged under one Alembic head (`l2e8a0b6d549`); fresh PostgreSQL upgrade to that head was verified before publication.
- [ ] Apply and verify the follow-on tenant-integrity migration (`m3f9c2a7e514`) after its PR is reviewed and merged.
- [x] Reconciled local backend suite: 209 passed, 3 PostgreSQL-only skips; isolated PostgreSQL worker tests: 3 passed.
- [ ] Run the new PostgreSQL tenant-integrity regression test against the follow-on migration.
- [x] Reconciled local frontend lint, TypeScript check and Next.js production build passed before PR #29 publication.
- [ ] Test retainer period closeout under PostgreSQL transaction locking.
- [ ] Test organization/workspace isolation for every new endpoint.
- [ ] Confirm no send/dispatch, payment, renewal or external call side effect exists.
- [ ] Obtain successful required CI checks and code review.
- [ ] Merge only after all gates pass.

## Definition of production-grade
A feature is **production-ready** only when implementation, authorization, tenant isolation, persistence, audit, failure recovery, tests, observability, retention and operational documentation are all evidenced. A schema, UI, action taxonomy or mocked adapter alone is a foundation, not a complete capability.


## 2026-11-25 post-merge status
- PR #29 consolidated and merged the work from PRs #25, #26 and #28. Those three source PRs were closed as superseded; their commits and discussions remain available.
- Main commit: `c14b8720f3288d65d2f9add2235a31defcb54096`.
- The 209-pass SQLite suite, 3 PostgreSQL worker tests, PostgreSQL migration to `l2e8a0b6d549`, frontend lint/typecheck/build and zero-vulnerability npm audit were run against the reconciled local tree before remote publication. They are not fresh exact-commit CI evidence.
- GitHub Actions runner allocation remains blocked by account billing. Development is continuing without repeated reruns; required production verification remains open.
- Outbound messages remain internal queue records. No provider send adapter or signed provider webhook is enabled.
