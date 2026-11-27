# Agency OS — Consolidation and Readiness Execution Ledger

**Last reconciled:** 2026-11-27  
**Release candidate:** `main` at `c5ec7b462835f592edb0db1a31564401423e3467`
**Latest merged work:** PR #65 — [System, Light and Dark dashboard themes](https://github.com/AsaifAli/agency-native-agency-os/pull/65); PR #58 remains the prior backend consolidation baseline.
**Consolidated security work:** PR #68 combines tool-session bounds and Data Protection Gateway hardening. Founder-environment suites passed on the earlier code/test head (530 Python tests passed, 20 skipped; isolated PostgreSQL 16 suite 106 passed). Independent review subsequently removed generic audit persistence of resume tokens, made machine-scope allowlists plus a 100-successful-call session ceiling mandatory at every Tool Gateway entry point, and added a regression for the worker's revoked global workspace enumerator and one-workspace maintenance claim. Those newest regressions still require rerun.
**Release posture:** **NO-GO for production** — implementation and disposable-environment tests are not production acceptance.

This document supersedes the pre-merge integration ledger below. PR #58 is the prior backend consolidation baseline and PR #65 is the latest merged dashboard change. Their old candidate-branch queues, merge blockers and workflow bootstrap failures are historical, not current merge tasks. GitHub Actions are intentionally excluded from this workstream per founder direction.

## Evidence rules

- **Implemented:** source code is present on the stated branch.
- **Tested:** an exact test command/result was reported or observed for the stated candidate. Do not generalize it to another commit or deployment.
- **Partial:** a foundation exists but acceptance criteria or dependent controls remain.
- **Awaiting founder environment:** requires local Docker/browser, live provider account, credentials, external DNS or deployment configuration.
- **Not implemented:** no accepted implementation evidence exists.
- A capability is production-ready only after backend enforcement, tenant/data controls, failure recovery, observability, retention, operational runbooks, exact-deployment verification and explicit founder approval.

## Merged baseline

- PR #58 established the backend/security baseline; its recorded results were **483 passed, 19 skipped, 2 warnings** and **105 passed, 2 warnings** in isolated PostgreSQL 16 Compose.
- PR #65 merged on 2026-11-27; merge commit `bc4eb0405fd1a07fcc75ab72828c0d76fc65f7d4`. It adds System/Light/Dark dashboard themes and repairs the frontend lockfile; `npm ci --ignore-scripts` passed, while the full lifecycle-script install remains a founder check.
- Exact-main frontend checks after PR #65: `npm ci --ignore-scripts`, lint (0 errors; 7 existing hook warnings), TypeScript and production build passed; 32 static pages generated.
- Headless browser theme checks passed for OS default, explicit overrides, persistence, live OS appearance changes and 320px layout overflow.
- PR #68 is the current draft security bundle. On earlier code/test head `04e6fdaf9960f06a783cbabe4fd7ddfcae687957`, full Python suite **530 passed, 20 skipped, 2 warnings**. After adding `tests/test_orchestration_plan_link_rls_postgres.py` to the Compose selection, founder reran the isolated PostgreSQL 16 stack: **106 passed, 2 warnings**, exit code 0; migration and app-role grant jobs completed successfully. The 20 host-suite skips are environment-gated live-PostgreSQL tests; the dedicated Compose selection runs the PostgreSQL-focused suite with isolated admin/migrator/app/worker URLs. GitHub Actions remain intentionally excluded.
- No production migration, deployment, provider activation or production data operation was performed.
- GitHub Actions remain intentionally excluded per founder direction.

## Phase ledger

| Phase | Current status | Evidence / remaining acceptance |
|---|---|---|
| 0. Architecture and consolidation | **Merged; baseline established** | Modular monolith and OS-owned state are retained. Refresh architecture/threat model and migration inventory against current main; no second control plane or queue engine. |
| 1. Database, APIs and worker infrastructure | **Implemented; tested in disposable PostgreSQL** | PostgreSQL 16 isolated suite 106 passed on the earlier PR #68 test head. Still need empty-volume and existing-volume rehearsal, role/grant/function inventory, performance budgets and deployed topology verification. |
| 2. Authentication and tenant isolation | **Partial** | OIDC/session lifecycle and exact workspace-grant authorization exist with route/PostgreSQL regression coverage. Live Authentik MFA/JWKS assurance, exhaustive BOLA review and isolation across future file/object-storage/RAG/artifact paths remain open. |
| 3. Organization and Agent Registry | **Partial** | 16 departments, workforce/position catalog, curated skills and founder-gated capability/member lifecycle exist. Provider Agent provisioning, skill assignment, immutable runtime version promotion/rollback and delegated machine identities remain incomplete. |
| 4. Revenue Engine | **Partial** | CRM, activity history, suppression records, opportunities, proposal drafts and founder pricing approval exist. Research/provenance at scale, dedupe/merge review, approved outbound dispatch, sender authorization, delivery receipts, reply/opt-out/bounce stops and attribution remain incomplete. |
| 5. Claude runtime and tool governance | **Partial / live runtime unverified** | Managed Agents adapter is opt-in and synthetic-first; current Tool Gateway foundation exists, but only health and public lead-research draft tools are registered. Full OS MCP bridge, DPG-at-dispatch, cancellation/reconciliation and live account/environment verification remain open. `WorkforceCapability.budget_minor` is stored but not reserved/settled by tool dispatch, so it is not an enforceable spend cap. Claude Agent SDK adapter is not implemented. |
| 6. Security and data protection | **Partial; mandatory blocker** | Worker capabilities, NOBYPASSRLS, append-only audit event protection and selected DPG/retention controls exist. PR #68 adds structured credential-key rejection, structured PII-field redaction, provider callback ID validation, broader token patterns, mandatory machine-scope tool allowlists and a default 100-successful-call session ceiling. Adapter policy may narrow, never widen, those controls. Generic audit events reject resume-token fields. Founder-reported verification: 530 Python tests passed (20 environment-gated skips) and 106 isolated PostgreSQL tests passed after expanding the Compose selection to include orchestration-plan link RLS. This does not close remaining security inventory, future data-path, egress/sandbox, cryptographic audit or independent-review requirements. File/RAG/connector/artifact paths are not implemented; egress/sandbox controls, independent review and cryptographic audit checkpoints remain open. |
| 7. Automation and events | **Partial** | PostgreSQL outbox and Python workers remain the chosen initial design. No production external outbox handlers are registered. Need end-to-end idempotency, replay/reconciliation, crash recovery and approved integration workflows. |
| 8. Evaluation Harness | **Partial** | Deterministic RAG, agent-workflow, safety/security and regression packs exist. Trusted runner attestation, immutable test/commit/environment manifests and release-blocking orchestration remain incomplete. |
| 9. Founder Console and approvals | **Partial** | Founder Console covers dashboard, workforce, processes, monitoring, revenue, delivery and outcomes. PR #65 adds System/Light/Dark themes and exact-main frontend checks passed. Browser critical journeys, unified work queue, drill-down, budget/exception visibility and stop controls remain. |
| 10. Delivery Engine and RAAS | **Partial** | Projects, milestones, delivery playbooks, scope approvals, time/cost records and project outcomes exist. Need KPI ingestion/evidence verification, requirement-to-test traceability, independent QA/rework, release/handover/support/SLA/renewal. |
| 11. Finance and operations | **Partial** | Service catalogue, contracts, onboarding, invoice issue evidence and payment receipt ledger exist. No payment collection or statutory accounting; cost/margin/forecast reconciliation, provider spend and overage approval remain. |
| 12. Hardening and release | **Not production-ready** | Need staging rehearsal, scans/SBOM, monitoring/alerts, backups/restore, measured RPO/RTO, runbooks, independent assessment and founder go/no-go. |

## Security controls on main and active hardening

- Worker database role is intended to be `NOBYPASSRLS`; production startup verifies the role and process role. The legacy `worker_workspace_scopes()` SECURITY DEFINER function is explicitly revoked from `PUBLIC` and `agency_os_worker` at the RLS cutover; the later maintenance path uses a 15–300 second, hash-bound, single-workspace claim and transaction-bound context. A new static migration regression asserts the revoke, bounded claim, context/release functions and ACL-preserving return-type fix; execution remains pending.
- Worker execution and maintenance scope is established by database-verified, capability-bound claim/renewal operations, not caller-forgeable machine GUCs.
- Human workspace grants are restored after the worker RLS cutover.
- Orchestration plan/delegation links are now workspace-scoped with composite FKs to both parents and forced RLS. The migration backfills from the parent plan and refuses existing orphan/cross-workspace rows.
- A model/RLS inventory test requires every mapped table except the explicitly global `users` identity directory to appear in `REQUIRED_RLS_TABLES`; `users` needs a separate global privacy/access review.
- Audit events reject UPDATE/DELETE for non-superuser application/worker roles. This is append-only protection, **not cryptographic tamper-evidence**; hash chaining or external integrity checkpoints remain future work.
- Audit payload protection on `main` rejects invalid/oversized structures and redacts supported PII/secrets. Draft PR #68 extends this to structured credential field names and structured PII keys, while preserving machine token prefixes and a resume token only inside a flat, validated resume-control object. Generic audit payloads and all unrelated metadata reject resume-token fields. Latest independent-review regressions still require focused and full reruns.
- Browser session lifecycle includes server-side revocation/rotation/expiry; agent session and tool invocation retention scrubs are bounded and workspace-scoped.
- Retention is incomplete for object artifacts, provider-side data, logs/traces and backups. Deletion/erasure must remain an explicit, approved, recoverable workflow.

## Immediate engineering sequence

1. **Exact-main stabilization:** frontend lint, typecheck and production build are complete after PR #65. Review migrations, role grants and the full RLS/function inventory; rerun backend/PostgreSQL suites on the latest PR #68 head.
2. **Isolation and DPG completion:** The consolidated security PR covers provider request/result/callback IDs, structured credential keys, structured PII fields, audit payloads, structured logs, machine-scope tool allowlists, the 100-successful-call session ceiling, and narrowly scoped resume-control metadata. Enumerate every tenant-bearing model, route, function, future file/object, cache, session, RAG and artifact path; add negative cross-workspace tests and fail-closed policy at each new boundary.
3. **OS Tool Gateway / MCP:** port a protocol-only MCP adapter against the current Tool Gateway; OS remains authority for identity, scope, policy, budgets, invocation, audit and durable state. Keep grants disabled until tests prove the boundary.
4. **Execution and outbox recovery:** prove kill/restart, leases, heartbeats, retry, DLQ, cancellation, replay and reconciliation under multiple workers.
5. **Revenue workflows:** implement synthetic prospect research/provenance and dedupe; only then build approved dispatch with sender authorization, consent/suppression and reply/opt-out/bounce stop guarantees. No live sending before explicit approval.
6. **Delivery and RAAS:** strengthen outcome evidence, scope revision, QA gates, release/handover, support and measurable client impact.
7. **Founder Console:** unify work queue and operational drill-down after backend contracts are stable; verify browser accessibility and critical journeys.
8. **Operations and production readiness:** monitoring, alerting, scans/SBOM, backup restore, RPO/RTO, runbooks, staging acceptance and independent security review.

## Founder-environment tasks — defer until code work is complete

- **Completed for PR #68 code/test head `04e6fdaf9960f06a783cbabe4fd7ddfcae687957` (founder-reported):** `python -m pytest -q` → 530 passed, 20 skipped, 2 warnings; expanded isolated PostgreSQL 16 Compose suite → 106 passed, 2 warnings, exit code 0. The Compose selection includes orchestration-plan link RLS. Host-suite skips are environment-gated; the dedicated Compose command supplies isolated PostgreSQL admin/migrator/app/worker URLs. Review any remaining security test gaps and complete independent review before merge.
- Local exact-main frontend commands (already passed after PR #65; rerun only if frontend files change):
  ```bash
  cd frontend
  npm ci
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
- Native Python workers and PostgreSQL outbox are the initial automation architecture. Redis is currently used for rate limiting; do not add business-data caching, Celery, Temporal or n8n without a demonstrated need and security/license review.
- Providers, MCP servers and automation tools are adapters; they never own critical business state or bypass OS authorization.
- Managed Agents remains beta, isolated behind an adapter and synthetic-first. Do not send confidential/client data unless provider eligibility and all applicable controls are established.
- No external communication, payment, contract, production release, destructive action or permission change without the required OS approval.
- No production migration/deployment, data deletion or compliance claim without explicit approval and evidence.


## Latest founder verification update — 2026-11-27

- On pre-fix PR head `88697b83bae5f1728cffab7c3c44707e368cd114`, the full host suite reported **538 passed, 3 failed, 20 skipped**. Two failures were resume audit events persisting `resume_token` after the generic audit exemption was removed; the resume flow now emits only `provider_session_reuse_required` in the audit payload, with a regression assertion that the token is absent. The third failure expected 404 for an unregistered tool even though the test identity lacked the invocation scope; the test now supplies the specific scope so the expected 404 tests registry absence rather than authorization denial.
- The isolated PostgreSQL suite on that same pre-fix head reported **106 passed, 1 failed**; the sole failure was the same resume audit-token issue. The fixes are committed on the PR branch; focused, full and PostgreSQL suites must be rerun on the current head before merge.
- The user's local uncommitted `.gitignore`, `frontend/next-env.d.ts` and generated `frontend/tsconfig.tsbuildinfo` were observed and not modified. The pre-existing local PostgreSQL volume remains out of scope and untouched.
