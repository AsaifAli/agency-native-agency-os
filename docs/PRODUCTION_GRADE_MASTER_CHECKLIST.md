# Agency OS — Full Production-Grade Readiness Master Checklist

**Last reconciled:** 2026-11-27 (PR #58 merged; local/live gates remain open)  
**Release posture:** **NO-GO — engineering and verification in progress**  
**Scope:** Founder-controlled internal AI agency operating system. This is not a SaaS product. The public agency website remains a separate trust boundary.

This is the master release checklist. It restores the broader P0/P1/P2 scope from the earlier Production Readiness v2 and consolidates the later security, worker, Revenue, Delivery, AI workforce and operations work. The detailed evidence log remains in `PRODUCTION_READINESS_CHECKLIST.md`; the 20-point audit remains in `PRE_DEPLOY_SECURITY_AUDIT_20_POINT.md`.

A checkbox is complete only when code/infrastructure, tests, operational evidence and documentation exist on the exact release candidate. Design notes, UI scaffolds, mocks and authored-but-unrun tests are not completion evidence.

## Release dashboard

| Gate | Current posture | Release condition |
|---|---|---|
| Architecture and data foundation | Partial | Migration, data integrity, API contracts and performance verified |
| Founder authority and identity | Partial | Live identity/MFA, session lifecycle and approval enforcement verified |
| Tenant isolation and data protection | Blocker | PostgreSQL 16 RLS and all cross-boundary tests pass |
| Workforce and agent runtime | Partial | OS-owned identities, grants, budgets, runtime isolation and recovery verified |
| Revenue engine | Partial | Provenance, dedupe, approved dispatch and stop controls end-to-end |
| Delivery engine | Partial | Traceability, independent QA, acceptance, release/handover and support |
| Durable automation and workers | Partial | PostgreSQL 16, process failure, retry, DLQ, replay and multi-replica tests |
| Security and privacy | Blocker | Threat review, egress/sandbox controls, retention, scans and independent review |
| Evaluation and SDLC | Partial | Release-blocking evaluations and exact-commit evidence |
| Operations and resilience | Blocker | Monitoring, alerting, backup restore, RPO/RTO and runbooks |
| External integrations | Mostly unverified | Provider setup and live synthetic acceptance |
| Founder go/no-go | Not approved | Explicit founder approval after all critical gates pass |

## P0 — Mandatory before any production use

### 1. Founder authority, identity and access control
- [ ] Provision the production identity provider and verify live OIDC discovery, JWKS rotation, callback validation, state, nonce and PKCE.
- [ ] Enforce phishing-resistant MFA / required ACR-AMR assurance for founder and privileged identities; test rejected low-assurance sessions.
- [ ] Verify browser-session creation, refresh rotation, replay rejection, revocation, logout, expiry and concurrent refresh behavior.
- [ ] Verify session cookie behavior in supported browsers and actual deployment topology (SameSite, Secure, HttpOnly, domain, proxy and TLS).
- [ ] Separate founder-wide authority from organization-owner, admin, employee, agent and machine identities.
- [ ] Enforce least-privilege RBAC/ABAC at every API, object, action, workspace, tool and execution boundary.
- [ ] Complete route-by-route authorization matrix and nested-object BOLA/IDOR review; structural route guards alone are insufficient.
- [ ] Add explicit human workspace membership/assignment; organization membership must not implicitly grant access to every workspace.
- [ ] Test privilege escalation, inactive users, revoked grants, expired sessions, cross-org and cross-workspace access.
- [ ] Ensure privileged permission changes, credential changes, destructive operations and production actions are approval-gated and audited.

### 2. Tenant isolation and Data Protection Gateway
- [ ] Apply all tenant RLS migrations on the supported PostgreSQL 16 version using the documented migration role.
- [ ] Verify table ownership, grants, FORCE RLS, policies, SECURITY DEFINER ownership/search path and role attributes.
- [ ] Run RLS tests as the real non-owner, NOBYPASSRLS API role; verify cross-tenant reads/writes are denied.
- [ ] Verify transaction-local tenant/user/machine context is set and cleared correctly under pooled connection reuse and rollback.
- [ ] Enforce exact machine workspace scope; test machine identity lookup and post-authentication context binding.
- [ ] Remove broad worker BYPASSRLS. Replace it with narrowly scoped queue claim/ack/recovery database functions and per-execution tenant context.
- [ ] Test tenant isolation across API, ORM, worker, queue, files, object storage, browser sessions, caches, search/RAG, logs and generated artifacts.
- [ ] Complete Data Protection Gateway (DPG) classification, minimization, PII/secret detection and redaction for uploads, extracted files, retrieval context, connector responses, tool inputs/outputs and provider callbacks.
- [ ] Enforce per-client data policy and runtime eligibility before any external provider receives data.
- [ ] Test prompt injection, indirect instructions in retrieved documents, malicious files, oversized/nested payloads and redaction collisions.
- [ ] Ensure secrets and unnecessary personal/client data never enter prompts, traces, logs, analytics or source control.

### 3. Approval and founder control plane
- [ ] Model approval as a server-enforced state machine with requester, approver, scope, target, version, expiry, evidence and decision history.
- [ ] Consume approval and perform the protected action in one database transaction; reject stale, replayed, mismatched or expired approvals.
- [ ] Gate contracts, pricing, payments, invoices being issued/sent, sensitive communications, production releases, permission changes and destructive/deletion actions.
- [ ] Ensure approval cannot be bypassed by agents, workers, MCP, webhooks, automation workflows or direct provider callbacks.
- [ ] Add founder exception inbox / Work Queue for approvals, escalations, risks, failed jobs, overdue decisions and budget exceptions.
- [ ] Provide evidence and impact preview before approval; preserve immutable audit of decision and execution outcome.
- [ ] Keep routine actions pre-authorized only within explicit scope, budget, rate and stop conditions.

### 4. Workforce, Chief of Staff and agent governance
- [ ] Complete workforce model: departments, teams, positions, human/agent members, supervisors, skills, tools, workers, workflows, tasks and sessions remain distinct concepts.
- [ ] Verify department/role coverage across Chief of Staff, Business Development, Marketing, Solutions, Engineering, QA/Security, Operations/Delivery, Client Success and Finance.
- [ ] Implement Chief of Staff planning, prioritization, assignment, delegation, escalation and progress synthesis using persisted OS tasks—not prompt-only coordination.
- [ ] Enforce delegation lineage, parent/child execution identity, bounded depth, allowed departments, scope and cancellation propagation.
- [ ] Implement Agent Registry versioning, activation, disablement, rollback, instruction/runtime selection, permissions, budgets, tools, data classes and audit.
- [ ] Require every agent action to use the OS Tool Gateway with a machine identity and scoped session grant.
- [ ] Verify per-agent, per-workspace, per-session and per-execution tool grants, expiry, revocation and risk classification.
- [ ] Implement Provider & Agent Budget Guard: reservation before execution, usage settlement after execution, hard limits, cost attribution and safe handling of unknown provider outcomes.
- [ ] Add per-agent rate/concurrency limits, circuit breakers, timeouts and provider/model fallback policy.
- [ ] Keep provider runtime without direct core DB credentials or unrestricted egress.
- [ ] Keep Claude Managed Agents behind a replaceable adapter; Managed Agents is beta and not eligible for ZDR/HIPAA BAA. Use synthetic/public data by default; require data-class and contract eligibility for commercial data.
- [ ] Keep Claude Agent SDK as the restricted/self-managed alternative where justified; preserve state and deliverables in the OS.
- [ ] Keep MCP as a thin Claude-side protocol adapter to the OS Tool Gateway, never a second authorization, state or business-logic system.
- [ ] Keep skills and operating loops disabled until OS-owned assignment/version/expiry/revocation, tool authorization, budget, evaluation and recovery are implemented.

### 5. Durable execution, queue and worker reliability
- [ ] Keep PostgreSQL as source of truth for executions, attempts, leases, results, errors, cancellation and audit.
- [ ] Verify PostgreSQL 16 migrations and integration tests, including concurrent claim, SKIP LOCKED behavior and lease expiry recovery.
- [ ] Verify independent worker service/container startup, health checks, graceful shutdown and bounded concurrency.
- [ ] Kill a worker after claim and after provider call; prove lease recovery, safe retry/reconciliation and no duplicate business effect.
- [ ] Test heartbeat loss, lease renewal races, expired lease recovery, retry scheduling, max attempts and dead-letter transitions.
- [ ] Test cancellation before claim, during execution and after external side effect; define honest terminal states for ambiguous outcomes.
- [ ] Verify pause/resume lifecycle: queued pause, provider-confirmed active pause, same-session resume, resume deduplication after worker crash, cancellation superseding pause, retry exhaustion and workspace isolation. Backend/API implementation and focused tests are present on `feat/agency-os-consolidation`; focused Python suite passed (47 tests), full SQLite-backed backend regression passed (408 tests; 8 PostgreSQL-only tests skipped), and the PostgreSQL Compose migration/test suite passed (55 tests). Live Managed Agents interruption/resumption, deployed multi-worker behavior and end-to-end UI verification remain pending.
- [ ] Implement idempotency keys and deduplication for every external action; reconcile provider outcomes after timeout rather than blindly resending.
- [ ] Complete transactional outbox delivery, versioned events, at-least-once semantics, duplicate handling, replay permissions and reconciliation.
- [ ] Test actual multi-process and multi-replica workers under sustained synthetic load; measure queue age, throughput, lock contention and resource usage.
- [ ] Add DLQ inspection/replay tools with authorization, audit and bounded replay.
- [ ] Ensure provider calls happen outside DB transactions and are bounded by timeouts, concurrency, payload and cost limits.
- [ ] Persist final result and audit before reporting success to the caller.
- [ ] Add recovery for orphaned sessions, ambiguous provider run creation, stuck executions and incomplete external callbacks.

### 6. Revenue engine — safe end-to-end operation
- [ ] Implement prospect discovery and enrichment with source provenance, timestamps, confidence and permitted-use tracking.
- [ ] Deduplicate companies, contacts and leads; provide founder-reviewed merge with audit and relationship preservation.
- [ ] Preserve lead source/history, research evidence, qualification, owner, next action and pipeline stage.
- [ ] Implement CRM lifecycle, opportunity forecasting, discovery briefs, objection tracking and proposal version history.
- [ ] Track sender identity approval, channel consent, source/consent provenance, suppression, opt-out and do-not-contact reasons.
- [ ] Separate outreach draft approval from dispatch authorization.
- [ ] Implement provider dispatch with idempotency, delivery receipts, signed webhooks and replay protection.
- [ ] Stop immediately on reply, opt-out, bounce, complaint, manual stop or suppression update; test race conditions.
- [ ] Enforce rate limits, contact windows, sender/domain health and bounded pre-authorized follow-up cadence.
- [ ] Track campaign, channel, conversion, pipeline and revenue attribution.
- [ ] Keep sensitive outreach, pricing, promises, contracts and commitments behind founder approval.
- [ ] Prove complete synthetic lead → research → review → CRM → approved outreach → reply/opt-out stop → audit workflow.

### 7. Delivery engine and client lifecycle
- [ ] Complete discovery records: goals, stakeholders, requirements, constraints, assumptions, risks and decisions.
- [ ] Implement Evidence & Acceptance Traceability from requirement → design → task → code/config → test → QA → acceptance → handover.
- [ ] Track project scope, milestones, task dependencies, owners, capacity, estimates, budgets, risks and change requests.
- [ ] Enforce scope-change approval and commercial impact review before work/billing changes.
- [ ] Add independent QA/security review, rework loop, acceptance criteria and evidence attachments.
- [ ] Gate deployments/releases on tests, security review, approvals, rollback plan and release evidence.
- [ ] Implement deployment record, environment, artifact/version, migration status, smoke tests, rollback and post-release verification.
- [ ] Complete client onboarding, status updates, delivery reporting, handover, documentation and knowledge export.
- [ ] Implement support requests, severity, response/resolution targets, escalation, SLA measurement and exclusions.
- [ ] Add client health signals based on grounded delivery, usage, support, feedback and commercial data.
- [ ] Add renewal, notice windows, price review, pause/resume, suspension and termination workflows with founder approval.
- [ ] Verify one-time project acceptance/warranty/closure and retainer period close, usage, adjustment and invoice-draft workflows.

### 8. Security engineering and privacy
- [ ] Maintain threat model, trust boundaries, abuse cases, attack trees and data-flow inventory.
- [ ] Enforce sandbox isolation, filesystem boundaries, safe archive extraction, file-type validation, malware scanning where appropriate and resource limits.
- [ ] Enforce network egress allowlists, DNS/IP validation, SSRF protections, redirect checks and provider-specific destinations at infrastructure level.
- [ ] Verify trusted proxy configuration, TLS, secure headers, CORS allowlists, CSRF, rate limiting and auth abuse protection.
- [ ] Centralize log/trace redaction; verify API, worker, proxy, platform, provider and third-party logs separately.
- [ ] Encrypt secrets at rest/in transit, rotate credentials and signing keys, scope provider tokens and remove secrets from Git history.
- [ ] Define retention, expiry, deletion and artifact cleanup for business records, browser sessions, agent sessions, executions, files, logs, backups and connected providers.
- [ ] Maintain tamper-evident audit with access controls, retention and integrity verification.
- [ ] Run dependency, container, SAST, secret, license and infrastructure scans; generate and review SBOM.
- [ ] Complete independent security assessment and remediate all critical/high findings.
- [ ] Make no SOC 2, ISO, HIPAA, GDPR or other compliance claim without applicable legal scope, contractual eligibility and independent evidence.

## P1 — Required before dependable autonomous operations

### 9. Founder Work Queue and operating cockpit
- [ ] Unified founder queue for approvals, decisions, escalations, blocked tasks, failed executions, risks, client issues and budget alerts.
- [ ] Prioritize by urgency, impact, client commitment, deadline and dependency; explain why an item needs founder attention.
- [ ] Show agent/team workload, task status, delegated work, blocked dependencies and expected completion.
- [ ] Provide pause/stop controls for agent, session, workflow, campaign, project and provider.
- [ ] Provide drill-down from KPI to underlying record, execution, evidence and audit event.
- [ ] Show spend, budget reservations, provider usage, failed calls and cost per workflow/client.
- [ ] Keep founder actions explicit and auditable; no hidden autonomous commitment.

### 10. Model routing and provider resilience
- [ ] Centralize provider/model registry, capabilities, context limits, data eligibility, latency, cost and status.
- [ ] Implement deterministic routing policy by task risk, data class, budget, latency and quality requirements.
- [ ] Add provider health checks, timeout budgets, circuit breakers, retry policy and fallback restrictions.
- [ ] Distinguish rate limit, timeout, authentication, malformed response and provider outage.
- [ ] Prevent retry storms and duplicate side effects; make fallback safe for tools and structured outputs.
- [ ] Track token usage, cost, latency, quality and provider/model version per execution.
- [ ] Provide founder controls for provider allowlists, spend ceilings, emergency disable and key rotation.

### 11. Engineering SDLC and change governance
- [ ] Protected main branch, review policy, versioned migrations and small reviewable feature branches.
- [ ] Keep tests local/targeted when CI quota is constrained; run one deliberate CI cycle when ready.
- [ ] Require unit, API, integration, migration, frontend, security and regression evidence on exact release commit.
- [ ] Require AI-generated code review, static analysis, dependency/license scan and ownership review.
- [ ] Maintain API contracts, architecture decision records, schema docs and operational docs.
- [ ] Verify migration from empty database and populated previous release; test forward recovery and rollback strategy.
- [ ] Maintain release tags, changelog, deployment artifact provenance and reproducible build evidence.
- [ ] Ensure branch/PR hygiene: work on a new branch, reconcile with current main, merge completed work to main, and avoid leaving completed changes stranded in long-lived branches.

### 12. Evaluation Harness and quality system
- [ ] Keep Evaluation Harness separate from production orchestration and use versioned APIs/datasets.
- [ ] Build synthetic evaluation sets for RAG grounding, retrieval, agent task completion, tool authorization, refusal/safety and regression.
- [ ] Add tenant-isolation, prompt-injection, data leakage, permission escalation and approval-bypass tests.
- [ ] Measure task success, factuality/grounding, latency, cost, retries and human intervention.
- [ ] Establish release thresholds and block release on failed critical evaluations.
- [ ] Store evaluation run metadata, model/prompt/tool versions and reproducible artifacts.
- [ ] Re-run regression suite after runtime, model, prompt, skill, tool schema or policy changes.

### 13. Finance, capacity and business operations
- [ ] Provider/agent budget reservation and settlement integrated with finance ledger.
- [ ] Track project budget, time/capacity, utilization, cost-to-serve, margin and forecast.
- [ ] Separate estimates, approved budgets, committed spend, actual usage and invoices.
- [ ] Reconcile invoice drafts, issued invoices, payments, refunds and provider costs with audit.
- [ ] Require approval for price changes, discounts, overages, payment actions and write-offs.
- [ ] Add cash-flow and receivables visibility without turning the OS into an accounting system replacement.
- [ ] Add staffing/capacity planning and overload alerts for human and agent contributors.

### 14. Automation integrations and workflow governance
- [ ] Keep OS as owner of state, permissions and business actions; integrations cannot write core tables directly.
- [ ] Use n8n only after license/security review for triggers, schedules, webhooks and notifications; Python workers own controlled compute/file jobs.
- [ ] Restrict workflow editors, credentials, node allowlists, egress and environment access.
- [ ] Version/test workflows, control releases, retain history and provide rollback.
- [ ] Authenticate all automation calls through OS APIs and enforce idempotency/audit.
- [ ] Test lead/CRM, approved outreach/stop, onboarding and delivery workflows with synthetic data.
- [ ] Add alerts, dead-letter handling, replay and reconciliation for integration failures.
- [ ] Do not add overlapping orchestration engines without measured justification.

## P2 — Scale, polish and continuous improvement

### 15. Performance, scale and cost efficiency
- [ ] Define SLOs for API latency, queue age, job completion, availability and provider response.
- [ ] Profile slow queries, add indexes and query budgets, paginate high-volume APIs and test realistic data volume.
- [ ] Load-test API, database pools, Redis, workers, provider adapters and file processing.
- [ ] Bound concurrency, memory, CPU, disk, file size, execution duration and spend.
- [ ] Test horizontal worker scaling and graceful capacity reduction.
- [ ] Add cache policy with tenant-safe keys, expiry and invalidation.
- [ ] Introduce additional infrastructure only when evidence demonstrates a need; start with Docker Compose and avoid Kubernetes without justification.

### 16. UX, accessibility and founder usability
- [ ] Complete coherent founder dashboard across workforce, tasks, workflows, clients, CRM, delivery, approvals, finance, monitoring and audit.
- [ ] Make status, failure, ownership, next action, spend and evidence visible.
- [ ] Add accessible navigation, keyboard support, loading/empty/error states and responsive layouts.
- [ ] Ensure destructive/high-impact controls require confirmation and show consequences.
- [ ] Verify frontend authorization mirrors backend policy without treating UI hiding as security.
- [ ] Run end-to-end browser tests for critical founder journeys. Frontend lint (0 errors; 7 pre-existing React Hook dependency warnings), TypeScript validation and Next.js production build passed before the final Founder Console UI reconciliation. A fresh run against exact merged `main` commit `4541626d6fffc904d8ee3131bb2f408efbe27acf` and browser-level critical-flow tests remain pending.

### 17. Learning and operational improvement
- [ ] Capture incidents, corrections, successful playbooks and postmortems as reviewed knowledge.
- [ ] Separate verified facts from agent-generated hypotheses and preserve source/evidence.
- [ ] Add approval-controlled promotion of lessons into skills, prompts, policies and workflows.
- [ ] Track recurring failure patterns and regression tests to prevent recurrence.
- [ ] Review agent permissions, budgets, workflow performance and data access periodically.

## P3 — Deployment, continuity and external readiness

### 18. Environments and deployment
- [ ] Separate dev/staging/production configuration, credentials, data, storage and provider accounts.
- [ ] Verify deployment topology, health/readiness checks, graceful shutdown and process supervision.
- [ ] Configure TLS, DNS, trusted proxy, CORS, rate limits, secrets and webhook endpoints.
- [ ] Verify API, frontend, scheduler, worker, PostgreSQL and Redis startup/restart behavior.
- [ ] Document controlled deployment, migration sequencing, rollback and post-deploy smoke tests.
- [ ] Perform synthetic end-to-end acceptance against staging before production.

### 19. Backup, restore and disaster recovery
- [ ] Encrypted automated PostgreSQL backups with retention and offsite copy.
- [ ] Back up object artifacts and critical configuration/metadata consistently.
- [ ] Complete restore drill into isolated environment and verify data integrity and application startup.
- [ ] Document and measure RPO/RTO; define incident roles and escalation.
- [ ] Test recovery after database loss, worker loss, provider outage, credential compromise and corrupted artifact.
- [ ] Verify deletion/retention obligations are reconciled with backup lifecycle.

### 20. External provider and legal configuration
- [ ] Authentik OIDC production client, callback, secrets, MFA policy and live assurance tests.
- [ ] Claude Managed Agents account/runtime eligibility, scoped credentials and synthetic acceptance; confirm workload data is eligible.
- [ ] Research/search sources and acceptable-use/source provenance policy.
- [ ] Email provider, verified sender/domain, inbound reply/bounce/complaint/opt-out webhooks and signing keys.
- [ ] LinkedIn integration only through permitted and approved methods; no scraping or unauthorized automation.
- [ ] Telephony provider, consent, recording, retention and jurisdiction-specific legal review before activation.
- [ ] Object storage, encryption, lifecycle, signed access and malware-safe file pipeline.
- [ ] Website intake signing secret, Turnstile and email delivery configuration verified separately from internal OS.
- [ ] Review vendor DPAs, subprocessors, data residency, retention, breach terms and provider-specific restrictions.

## Required acceptance scenarios (synthetic data first)

- [ ] Founder login with MFA → create/revoke session → prove replay rejection and audit.
- [ ] User/machine from Workspace A attempts to read/write Workspace B → denied at API and database layers.
- [ ] Worker claims job → process is killed → lease expires → recovery schedules safe retry → no duplicate business effect.
- [ ] Two or more workers claim concurrently → no duplicate active claim; outbox duplicate delivery remains idempotent.
- [ ] Provider times out after accepting request → reconciliation determines outcome before retry.
- [ ] Agent delegates to child agent → lineage, scope, budget and cancellation are enforced and persisted.
- [ ] Agent attempts ungranted tool/data/action → OS Tool Gateway denies and audits.
- [ ] Approval is replayed, expired or mismatched → protected action does not execute.
- [ ] Lead research produces duplicate/low-confidence result → provenance retained and human merge required.
- [ ] Approved outreach receives reply/opt-out/bounce → all pending follow-ups stop.
- [ ] Delivery requirement is changed → scope approval, tests, QA and acceptance trace remain linked.
- [ ] Production release fails smoke test → rollback path is exercised and audited.
- [ ] Backup is restored into isolated environment → integrity, migrations and service startup verified.
- [ ] Evaluation Harness detects a known tenant leak, prompt injection or authorization regression → release is blocked.

## Known open blockers at the 2026-11-27 checkpoint

- [x] PR #58 merged to `main` at `4541626d6fffc904d8ee3131bb2f408efbe27acf`; the consolidation branch is no longer the release candidate.
- [x] Worker database role no longer relies on broad `BYPASSRLS`; the production worker role is verified as `NOBYPASSRLS`, and worker execution/maintenance uses database-verified capability-bound scope.
- [x] Human workspace-grant authorization was restored after the worker RLS cutover; exact cross-workspace and API/files/cache/artifact coverage still needs a complete independent inventory and runtime validation.
- [x] PostgreSQL 16 isolated Compose suite: **105 passed, 2 warnings** on the merged candidate. This is disposable test-environment evidence, not a production migration rehearsal.
- [x] Backend suite: **483 passed, 19 skipped, 2 warnings** on the merged candidate. Skips include environment-dependent PostgreSQL tests; the dedicated PostgreSQL suite is reported separately.
- [ ] Fresh frontend lint, TypeScript check and production build against the exact merged `main` head after final Founder Console UI reconciliation.
- [ ] Complete independent role/grant/ownership and RLS policy review across every tenant-scoped table, SECURITY DEFINER function and deployment role; test pooled-connection context and cross-boundary API/file/object/cache/session/artifact access.
- [ ] Complete nested-object BOLA/IDOR review and verify workspace grants for every human access path.
- [ ] Complete Data Protection Gateway coverage across uploads, extraction, RAG, provider callbacks, tool dispatch, logs, caches and artifacts; prove runtime eligibility before external provider disclosure.
- [ ] Complete artifact/object-storage lifecycle, encryption, malware-safe processing, signed access and tenant isolation.
- [ ] Validate worker crash/restart, lease recovery, concurrent claims, cancellation races, outbox replay and multi-replica behavior against the intended deployment topology.
- [ ] Implement and test the OS MCP/tool adapter against the current Tool Gateway; tool grants remain disabled until every call is authorized, budgeted, data-checked and audited by the OS.
- [ ] Validate live Authentik OIDC/JWKS/MFA assurance and deployed browser/session behavior.
- [ ] Validate Claude Managed Agents account/runtime compatibility, environment sandbox/egress, provisioning reconciliation and synthetic-data eligibility; no live client-data use is approved.
- [ ] Implement governed outbound dispatch with approved sender identity, consent/suppression, idempotency, delivery receipts and immediate reply/opt-out/bounce stop handling. No external message dispatch is enabled.
- [ ] Complete Revenue provenance/deduplication/merge review, attribution and client-safe proposal delivery.
- [ ] Complete Delivery requirement-to-test traceability, independent QA/rework, release approval, handover, support/SLA and renewal workflows.
- [ ] Add trusted Evaluation Harness runner attestation, immutable test/commit/environment manifests and a release-blocking decision path; caller-supplied evidence is not proof.
- [ ] Add provider routing/resilience, per-execution cost/usage accounting, enforceable budgets and founder emergency controls.
- [ ] Add operational metrics, alert routing, dashboards, SBOM/scans, incident runbooks and periodic access review.
- [ ] Complete encrypted backup/object-artifact backup and isolated restore drill; measure and document RPO/RTO.
- [ ] Complete staging synthetic end-to-end acceptance, external provider/webhook/storage configuration and explicit founder production go/no-go.


## Worker architecture decision

PostgreSQL remains the durable execution queue and source of truth; independent Python worker processes/services claim work using persisted leases and recovery. Redis remains for cache, throttling and coordination where needed. Do not add Celery as a second queue/broker unless measured requirements prove the existing design insufficient. Any future queue must preserve OS-owned authorization, execution state, audit, idempotency, cancellation and recovery.

## Definition of production-grade

A capability is production-ready only when all of the following are true:

1. Implemented in enforceable backend code and infrastructure—not prompts or UI alone.
2. Authorized at user, workspace, agent, tool and execution boundaries.
3. Tenant-isolated and data-classified before provider or worker access.
4. Durable, idempotent, auditable and recoverable after process/provider/network failure.
5. Covered by unit, integration, negative security, migration and realistic failure tests.
6. Observable through useful logs, metrics, traces, alerts and cost controls.
7. Covered by retention, deletion, backup and restore procedures.
8. Documented with runbooks, ownership, configuration and rollback.
9. Verified against the exact release commit and deployment topology.
10. Explicitly approved by the founder for release.

**Release decision: NO-GO until all applicable P0 gates and required P1 operational gates are evidenced and the founder explicitly approves production release.**
