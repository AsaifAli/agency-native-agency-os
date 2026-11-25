# Agency OS — Production-Grade Master Checklist

**Purpose:** One release-gate view of the work required before the Agency OS can be called production-grade. This checklist is intentionally evidence-driven: a checkbox is complete only when implementation, tests and operational evidence exist on the release candidate.

**Status:** NO-GO / in progress. This document is a concise release gate index. The detailed workstream checklist and dated evidence remain in [PRODUCTION_READINESS_CHECKLIST.md](./PRODUCTION_READINESS_CHECKLIST.md), and security findings remain in [PRE_DEPLOY_SECURITY_AUDIT_20_POINT.md](./PRE_DEPLOY_SECURITY_AUDIT_20_POINT.md).

## Release gates

### 1. Repository, architecture and change control
- [ ] Reconcile all open PRs against the intended release branch; review diffs, migrations and overlapping changes.
- [ ] Protect release branches; require human review for security-sensitive changes.
- [ ] Verify reproducible builds, dependency lockfiles, migration ordering and rollback/recovery plans.
- [ ] Keep public website and internal Agency OS trust boundaries separate.
- [ ] Document architecture, data flows, threat model, service ownership and provider boundaries.

### 2. Identity, founder authority and authorization
- [ ] Configure production identity provider and verify live OIDC/JWKS flow.
- [ ] Enforce and verify phishing-resistant MFA / required assurance for founder and privileged users.
- [ ] Verify session rotation, revocation, expiry, logout, refresh races and retention in the deployed browser topology.
- [ ] Test every API route and nested resource for organization/workspace authorization and BOLA/IDOR.
- [ ] Implement human workspace assignments and least-privilege role grants.
- [ ] Verify founder-wide authority is distinct from organization-owner permissions.
- [ ] Ensure high-impact approvals are consumed atomically with the protected action and audited.

### 3. Tenant isolation and data protection
- [ ] Apply and verify PostgreSQL RLS on the supported PostgreSQL 16 version.
- [ ] Run cross-tenant read/write, machine workspace-scope and pooled-connection reuse tests as non-owner NOBYPASSRLS roles.
- [ ] Remove broad worker BYPASSRLS; replace with narrowly scoped queue claim/ack functions and per-execution tenant context.
- [ ] Test tenant isolation across APIs, ORM queries, workers, files, sessions, caches, retrieval and artifacts.
- [ ] Complete Data Protection Gateway coverage for uploads, extracted documents, RAG context, connector payloads and tool inputs/outputs.
- [ ] Verify classification, minimization, PII/secret redaction and runtime eligibility before data reaches providers.
- [ ] Define retention, deletion and recovery across database records, sessions, logs, backups and object storage.

### 4. Execution and worker reliability
- [ ] Verify PostgreSQL 16 migration and integration suite, including concurrent claims and expired-lease recovery.
- [ ] Test real worker process kill/restart, lease expiry, heartbeat loss, retry, cancellation and recovery.
- [ ] Run sustained load and multi-replica worker tests; measure throughput, queue age, contention and resource limits.
- [ ] Verify idempotency, deduplication, bounded retries, dead letters and reconciliation for every external adapter.
- [ ] Verify outbox delivery is at-least-once, replayable and safe under duplicate delivery.
- [ ] Persist executions, attempts, leases, results, errors and audit before reporting success.
- [ ] Keep external provider calls outside database transactions; enforce timeouts and concurrency/cost bounds.

### 5. Agent runtime and tool governance
- [ ] Keep Claude Managed Agents behind a replaceable runtime adapter; validate live provider behavior and eligibility.
- [ ] Ensure agents have no direct core-database credentials or unrestricted network access.
- [ ] Enforce per-agent, per-workspace and per-session tool grants, data classes, budgets, expiry and revocation in backend code.
- [ ] Verify parent/child execution lineage, child budgets, cancellation and provider-event reconciliation.
- [ ] Keep MCP as a protocol adapter to the OS Tool Gateway, never a parallel authorization or state system.
- [ ] Keep skills and operating loops disabled until OS-owned assignment, authorization, evaluation and recovery exist.

### 6. Revenue and delivery safety
- [ ] Verify lead provenance, deduplication, confidence and human-reviewed merge workflows.
- [ ] Require approved sender identity, consent/provenance, suppression checks, rate limits and dispatch authorization.
- [ ] Test stop-on-reply, opt-out, bounce, complaint and manual stop end to end.
- [ ] Keep pricing, contracts, payments, sensitive communications and production releases approval-gated.
- [ ] Trace delivery requirements to tests, independent QA, acceptance evidence and handover.
- [ ] Verify support severity, SLA measurement, escalation, client health and renewal/termination controls.

### 7. Infrastructure, secrets and external services
- [ ] Separate dev/staging/production credentials, databases, storage, queues and provider accounts.
- [ ] Configure TLS, trusted proxy boundaries, CORS, rate limits, DNS/egress allowlists and SSRF protections.
- [ ] Store secrets in an approved secret manager; rotate keys and verify no secrets in prompts, logs, artifacts or Git history.
- [ ] Verify object-storage access controls, encryption, signed URLs, retention and malware-safe file handling.
- [ ] Configure and test required external providers/webhooks; verify signatures, replay protection and failure reconciliation.
- [ ] Apply CPU, memory, concurrency, request-size and execution-duration limits.

### 8. Observability, recovery and operations
- [ ] Configure structured redacted logs, metrics, traces, queue/worker health and provider error visibility.
- [ ] Set alerts for auth anomalies, tenant-boundary denials, queue age, retries, dead letters, provider outages and budget thresholds.
- [ ] Create incident, credential-rotation, provider-outage, stuck-execution and data-recovery runbooks.
- [ ] Take encrypted backups and complete a restore drill; document measured RPO/RTO.
- [ ] Test migration upgrade and rollback/recovery against a production-like populated database.
- [ ] Verify retention and deletion jobs, including logs, backups and object artifacts.

### 9. Evaluation and release verification
- [ ] Run unit, API, integration, migration, security, regression and frontend build/lint suites on the exact release commit.
- [ ] Run the separate Evaluation Harness with versioned synthetic RAG, agent, safety and security cases.
- [ ] Block releases on failed evaluation or security gates.
- [ ] Generate and review an SBOM; run dependency, secret, container and static security scans.
- [ ] Complete independent security review and remediate all critical/high findings.
- [ ] Preserve command output, environment/version details and test artifacts as evidence.
- [ ] Complete a founder-led go/no-go review; no production release without explicit approval.

## Current known blockers (2026-11-26)
- [ ] PostgreSQL 16 verification; current worker integration evidence is PostgreSQL 17.
- [ ] Dedicated NOBYPASSRLS RLS test and complete role/grant verification.
- [ ] Replace worker-wide BYPASSRLS with narrowly scoped queue operations.
- [ ] Human workspace assignment model and complete nested-object authorization tests.
- [ ] Actual worker process restart, sustained load, cancellation and deployed multi-replica tests.
- [ ] Live Authentik MFA/assurance and browser/session verification.
- [ ] Claude/provider live validation, provider/webhook configuration and runtime eligibility review.
- [ ] Egress/SSRF infrastructure controls, secret-history review, backup/restore and operational alert/runbook verification.
- [ ] Independent security review and exact-release end-to-end evaluation.

## Architecture decision: worker queue
The current design uses PostgreSQL as the durable execution queue and independent Python worker processes for claiming and executing jobs. Redis remains available for cache, throttling and coordination where appropriate. Do not add Celery as a second broker/queue unless measured requirements demonstrate a concrete gap that the current persisted execution/lease/recovery model cannot meet. Any queue technology must preserve OS-owned authorization, execution state, audit, idempotency and recovery.

## Definition of done
A release gate is complete only when the control is implemented in enforceable code/infrastructure, tested under realistic failure and isolation conditions, observed operationally, documented, and evidenced against the exact release candidate. Passing unit tests or adding a checklist item is not production approval.

**Release decision: NO-GO until all applicable critical gates above are evidenced and the founder explicitly approves release.**
