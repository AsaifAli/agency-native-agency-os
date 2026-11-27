# Agency OS — Consolidation and Readiness Execution Ledger

**Last reconciled:** 2026-11-27  
**Release candidate:** `main` at `4541626d6fffc904d8ee3131bb2f408efbe27acf`  
**Merged work:** PR #58 — [Consolidate Agency OS execution controls and reliability changes](https://github.com/AsaifAli/agency-native-agency-os/pull/58)  
**Release posture:** **NO-GO for production** — implementation and disposable-environment tests are not production acceptance.

This document supersedes the pre-merge integration ledger below. PR #58 is merged. Its old candidate-branch queue, PR #58 merge blocker and workflow bootstrap failure are historical, not current merge tasks. GitHub Actions are intentionally excluded from this workstream per founder direction.

## Evidence rules

- **Implemented:** source code is present on the stated branch.
- **Tested:** an exact test command/result was reported or observed for the stated candidate. Do not generalize it to another commit or deployment.
- **Partial:** a foundation exists but acceptance criteria or dependent controls remain.
- **Awaiting founder environment:** requires local Docker/browser, live provider account, credentials, external DNS or deployment configuration.
- **Not implemented:** no accepted implementation evidence exists.
- A capability is production-ready only after backend enforcement, tenant/data controls, failure recovery, observability, retention, operational runbooks, exact-deployment verification and explicit founder approval.

## Merged baseline

- PR #58 merged into `main` on 2026-11-27; merge commit `4541626d6fffc904d8ee3131bb2f408efbe27acf`.
- The merged baseline includes the consolidated worker capability boundary, workspace-grant human authorization restoration, append-only audit-event protection, retention scrubbing foundations and RAAS project outcome management.
- Backend suite on the merged candidate: **483 passed, 19 skipped, 2 warnings**.
- Isolated PostgreSQL 16 Compose suite on the merged candidate: **105 passed, 2 warnings**.
- Frontend lint/typecheck/build passed before final Founder Console UI reconciliation; a fresh run on exact merged `main` remains required.
- No production migration, deployment, provider activation or production data operation was performed.
- No GitHub Actions run is claimed for PR #58.

## Phase ledger

| Phase | Current status | Evidence / remaining acceptance |
|---|---|---|
| 0. Architecture and consolidation | **Merged; baseline established** | Modular monolith and OS-owned state are retained. Refresh architecture/threat model and migration inventory against current main; no second control plane or queue engine. |
| 1. Database, APIs and worker infrastructure | **Implemented; tested in disposable PostgreSQL** | PostgreSQL 16 isolated suite 105 passed. Still need empty-volume and existing-volume rehearsal, role/grant/function inventory, performance budgets and deployed topology verification. |
| 2. Authentication and tenant isolation | **Partial** | OIDC/session lifecycle and workspace-grant authorization exist. Live Authentik MFA/JWKS assurance, full BOLA review and isolation across files/object storage/cache/RAG/logs/artifacts remain open. |
| 3. Organization and Agent Registry | **Partial** | 16 departments, workforce/position catalog, curated skills and founder-gated capability/member lifecycle exist. Provider Agent provisioning, skill assignment, immutable runtime version promotion/rollback and delegated machine identities remain incomplete. |
| 4. Revenue Engine | **Partial** | CRM, activity history, suppression records, opportunities, proposal drafts and founder pricing approval exist. Research/provenance at scale, dedupe/merge review, approved outbound dispatch, sender authorization, delivery receipts, reply/opt-out/bounce stops and attribution remain incomplete. |
| 5. Claude runtime and tool governance | **Partial / live runtime unverified** | Managed Agents adapter is opt-in and synthetic-first; current Tool Gateway foundation exists, but only a narrow safe capability is executable. Full OS MCP bridge, scoped tool authorization, DPG-at-dispatch, budgets, cancellation/reconciliation and live account/environment verification remain open. Claude Agent SDK adapter is not implemented. |
| 6. Security and data protection | **Partial; mandatory blocker** | Worker capabilities, NOBYPASSRLS, append-only audit event protection and selected DPG/retention controls exist. Full DPG path coverage, artifact lifecycle, secret/egress/sandbox controls, independent security review and cryptographic audit checkpoints remain open. |
| 7. Automation and events | **Partial** | PostgreSQL outbox and Python workers remain the chosen initial design. No production external outbox handlers are registered. Need end-to-end idempotency, replay/reconciliation, crash recovery and approved integration workflows. |
| 8. Evaluation Harness | **Partial** | Deterministic RAG, agent-workflow, safety/security and regression packs exist. Trusted runner attestation, immutable test/commit/environment manifests and release-blocking orchestration remain incomplete. |
| 9. Founder Console and approvals | **Partial** | Founder Console covers dashboard, workforce, processes, monitoring, revenue, delivery and outcomes. Fresh exact-main frontend checks and browser journeys remain pending; unify work queue, drill-down, budget/exception visibility and stop controls. |
| 10. Delivery Engine and RAAS | **Partial** | Projects, milestones, delivery playbooks, scope approvals, time/cost records and project outcomes exist. Need KPI ingestion/evidence verification, requirement-to-test traceability, independent QA/rework, release/handover/support/SLA/renewal. |
| 11. Finance and operations | **Partial** | Service catalogue, contracts, onboarding, invoice issue evidence and payment receipt ledger exist. No payment collection or statutory accounting; cost/margin/forecast reconciliation, provider spend and overage approval remain. |
| 12. Hardening and release | **Not production-ready** | Need staging rehearsal, scans/SBOM, monitoring/alerts, backups/restore, measured RPO/RTO, runbooks, independent assessment and founder go/no-go. |

## Security work now merged

- Worker database role is intended to be `NOBYPASSRLS`; production startup verifies the role and process role.
- Worker execution and maintenance scope is established by database-verified, capability-bound claim/renewal operations, not caller-forgeable machine GUCs.
- Human workspace grants are restored after the worker RLS cutover.
- Audit events reject UPDATE/DELETE for non-superuser application/worker roles. This is append-only protection, **not cryptographic tamper-evidence**; hash chaining or external integrity checkpoints remain future work.
- Audit payload protection rejects invalid/oversized structures and redacts supported PII/secrets.
- Browser session lifecycle includes server-side revocation/rotation/expiry; agent session and tool invocation retention scrubs are bounded and workspace-scoped.
- Retention is incomplete for object artifacts, provider-side data, logs/traces and backups. Deletion/erasure must remain an explicit, approved, recoverable workflow.

## Immediate engineering sequence

1. **Exact-main stabilization:** fresh frontend lint, typecheck and production build; review migrations, role grants and the full RLS/function inventory. Reconcile any failures before adding features.
2. **Isolation and DPG completion:** enumerate every tenant-bearing model, route, function, file/object, cache, session, RAG, log and artifact path; add negative cross-workspace tests and fail-closed data classification at every external boundary.
3. **OS Tool Gateway / MCP:** port a protocol-only MCP adapter against the current Tool Gateway; OS remains authority for identity, scope, policy, budgets, invocation, audit and durable state. Keep grants disabled until tests prove the boundary.
4. **Execution and outbox recovery:** prove kill/restart, leases, heartbeats, retry, DLQ, cancellation, replay and reconciliation under multiple workers.
5. **Revenue workflows:** implement synthetic prospect research/provenance and dedupe; only then build approved dispatch with sender authorization, consent/suppression and reply/opt-out/bounce stop guarantees. No live sending before explicit approval.
6. **Delivery and RAAS:** strengthen outcome evidence, scope revision, QA gates, release/handover, support and measurable client impact.
7. **Founder Console:** unify work queue and operational drill-down after backend contracts are stable; verify browser accessibility and critical journeys.
8. **Operations and production readiness:** monitoring, alerting, scans/SBOM, backup restore, RPO/RTO, runbooks, staging acceptance and independent security review.

## Founder-environment tasks — defer until code work is complete

- Local exact-main frontend commands:
  ```bash
  cd frontend
  npm run lint
  npx tsc --noEmit
  npm run build
  ```
- Disposable PostgreSQL test stack and existing-volume upgrade/restore rehearsal.
- Browser-based Founder Console critical-flow and accessibility checks.
- Live Authentik OIDC/MFA, Claude Managed Agents, object storage, email/webhook and website-intake synthetic configuration.
- Staging deployment smoke tests, backup restore drill and measured RPO/RTO.
- Final production go/no-go. Production remains disabled until the founder explicitly approves it.

## Architecture guardrails

- PostgreSQL is the source of truth for business state, approvals, executions and audit.
- Native Python workers and PostgreSQL outbox are the initial automation architecture. Redis remains cache/throttle/coordination; do not add Celery, Temporal or n8n without a demonstrated need and security/license review.
- Providers, MCP servers and automation tools are adapters; they never own critical business state or bypass OS authorization.
- Managed Agents remains beta, isolated behind an adapter and synthetic-first. Do not send confidential/client data unless provider eligibility and all applicable controls are established.
- No external communication, payment, contract, production release, destructive action or permission change without the required OS approval.
- No production migration/deployment, data deletion or compliance claim without explicit approval and evidence.
