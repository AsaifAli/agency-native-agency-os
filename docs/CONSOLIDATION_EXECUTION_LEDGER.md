# Consolidation Execution Ledger

**Target:** PR #58, `integration/consolidated-agency-os-2026-11-26` → `main`  
**Policy:** one integration branch; no additional branches unless unavoidable. PostgreSQL remains the source of truth. Do not merge a feature solely because it is ahead of main.

This ledger separates repository evidence from local-runtime verification. Statuses are deliberately conservative.

## Status definitions

- **Implemented (reviewed):** code exists on the integration branch and its relevant files have been inspected.
- **Partially implemented:** a foundation exists, but acceptance criteria or dependent controls remain.
- **Ready for integration review:** a candidate branch contains potentially useful work; it has not been merged into this integration branch.
- **Blocked:** a known dependency or defect prevents safe completion.
- **Awaiting local verification:** requires Docker/PostgreSQL, a live worker process, browser, provider credentials, or deployment access unavailable through repository inspection.
- **Not started:** no implementation evidence has been reviewed.

## Phase ledger

| Phase | Scope | Current evidence | Status | Required proof |
|---|---|---|---|---|
| 0. Audit and architecture | Scope, boundaries, threat model, migration map, acceptance criteria | Existing README, operating capability map, feature adoption plan and PR #58 scope | Partially implemented | Reconcile every candidate branch; confirm final migration graph and data ownership |
| 1. Database, APIs and infrastructure | PostgreSQL source of truth, role separation, migrations, API contracts, Docker Compose | PostgreSQL test Compose and role bootstrap exist; PR adds execution-control migration and several domain migrations | Blocked on full PostgreSQL upgrade test | Fresh-volume and existing-volume migration, downgrade/restore policy, schema inventory |
| 2. Authentication and tenant isolation | Authenticated actor context, exact workspace grants, RLS, founder authority | PR base contains workspace auth work; candidate authorization and full-RLS branches add broader route/RLS inventory | Ready for integration review | Cross-tenant API/file/worker/cache tests; spoofed actor/workspace rejection; non-superuser and BYPASSRLS checks |
| 3. Organization and Agent Registry | Departments, teams, positions, agents, skills, permissions, budgets, versions | Workforce catalogue and founder plan-draft foundations exist; capability map intentionally avoids inventing missing teams/skills | Partially implemented | Registry lifecycle, immutable version/evidence, least-privilege assignment, rollback tests |
| 4. Revenue Engine | Research, leads, CRM, opportunities, proposals, outreach, approvals | Integration branch contains parts of Revenue/Delivery; revenue/outreach branches contain additional candidate models, routes, pages and migrations | Partially implemented | Deduplication, provenance, consent/suppression, sender authorization, reply/opt-out/bounce stop tests, pricing/contract approval |
| 5. Claude runtime adapters | Managed Agents adapter, tool policy, MCP bridge, machine identity | Managed Agents adapter exists; custom-tool, Tool Gateway and MCP branches contain overlapping candidate implementations | Partially implemented | OS-owned authorization on every tool call; provider cannot bypass policy; runtime cancellation/recovery; synthetic-data eligibility |
| 6. Security and controlled workers | DPG, scoped credentials, leases, heartbeats, retries, cancellation, recovery, audit | Worker lease and execution-control foundations exist; DPG, machine identity and process-crash test branches need selective reconciliation | Partially implemented | PII/data-class tests, lease expiry, worker kill/restart, cancellation races, bounded retry, dead-letter and reconciliation |
| 7. Automation and events | Outbox, idempotency, retries, dead letters, external integrations | Outbox reliability foundations and delivery migration tests exist in the integration branch | Partially implemented | Duplicate delivery, crash between commit/dispatch, poison event, replay policy, reconciliation; n8n remains an adapter candidate, not authority |
| 8. Evaluation Harness | Versioned datasets, agent/prompt/model/policy revisions, release gates | Evaluation packs/runs/quality gates exist; adoption plan records missing release manifest and independent evidence | Partially implemented | Failed safety/isolation/regression gate demonstrably blocks release |
| 9. Founder Console and approvals | Dashboard, execution controls, approvals, operational visibility | Workflow UI and pause/resume/stop controls exist; outbox/worker health and broader approval UX remain incomplete | Partially implemented | Browser tests for individual approvals, stop conditions, role visibility and accurate status |
| 10. Delivery Engine | Onboarding, projects, milestones, tasks, budgets, QA, handover, support | Delivery models/routes and capability map exist in part; onboarding/contracts branch adds candidate work | Partially implemented | Requirement-to-test traceability, workspace scoping, budget controls, change approval and handover evidence |
| 11. Finance and operations | Invoices, receipts, retainers, cost/margin, monitoring, backups | Finance/delivery feature branches contain candidate records and migrations; no end-to-end proof reviewed | Ready for integration review | Reconciliation, approval gates, observability, backup restore, RPO/RTO and access audit |
| 12. Hardening and release | CI, security scans, SBOM, migration tests, docs, deployment readiness | Existing test harness and readiness docs; CI backend migration job previously failed because its Postgres service did not create `agency_os_migrator` | Blocked / awaiting verification | Correct disposable Postgres setup, full backend suite, frontend checks, security scan, SBOM, restore rehearsal |

## Candidate branch reconciliation queue

These branches are review sources, not approved merge targets. Integrate only the minimal compatible files/commits after checking their base and migration ancestry.

| Area | Candidate branch(es) | Review rule |
|---|---|---|
| Workspace authorization | `security/human-workspace-authorization`, `security/machine-identity-rls-lookup` | Reconcile the human-workspace migration once; preserve authenticated actor derivation and explicit founder-authority grant |
| Full RLS inventory | `hardening/verify-full-rls-inventory` | Align required-table inventory with actual tenant schema; validate as non-superuser |
| Worker recovery | `test/worker-lease-recovery-main-20261126`, `test/worker-process-crash-recovery-main-20261126` | Preserve lease/outbox and actual process-kill coverage without replacing newer worker implementation |
| Data protection | `feature/tenant-dpg-hardening-current`, `feature/outreach-tenant-integrity` | Review PII handling, tenant integrity migration and policy enforcement; fail closed |
| Tool Gateway and MCP | `feature/os-tool-gateway`, `feature/managed-agent-custom-tools`, `feature/managed-agents-mcp-bridge` | OS owns registry, identity, authorization, invocation, audit and state; MCP is only a Claude-side protocol adapter |
| Revenue and Delivery | `feature/revenue-delivery-consolidated`, `feature/contracts-onboarding-clean`, `feature/outbound-communications-foundation`, `feature/outreach-tenant-integrity` | Reconcile domain schemas, UI and Alembic heads; do not duplicate tables/revisions |
| Workforce orchestration | `feature/claude-chief-of-staff-plan-drafts`, `feature/agency-os-chief-of-staff-orchestration` | Keep proposals distinct from execution; founder approval before task materialization |

## Verification ownership

### Repository-level checks available for this work

- Inspect exact branch files, diffs, migration revision IDs and down-revision links.
- Review route dependencies, scope filters, policy defaults, transaction boundaries and tests.
- Review Python/TypeScript source statically and compare candidate implementations.
- Add focused tests and docs where the repository interface allows safe, complete changes.
- Inspect GitHub check results and logs when present. A skipped test is not a pass.

### Local checks required from the project environment

Run against the exact integration head after it stabilizes:

1. Fresh PostgreSQL test stack: role bootstrap, migration upgrade to head, schema/RLS inventory.
2. Existing-volume upgrade and documented rollback/restore rehearsal on disposable data.
3. Backend unit suite, API authorization suite and PostgreSQL integration suite.
4. Concurrent worker claim, lease expiry, process kill/restart, retry/DLQ and cancellation/pause/resume race tests.
5. Frontend typecheck, production build and Playwright critical workflows.
6. Synthetic end-to-end: approved lead capture → CRM; draft → individual approval → send simulation → reply/opt-out stop; onboarding → delivery task → QA/evaluation → handover.
7. External-provider smoke tests only with explicitly configured test credentials and synthetic data.
8. Backup restore and operational recovery rehearsal before production use.

## Known verification blocker

The previously observed PR #58 backend workflow failed before backend compilation/tests because its PostgreSQL service lacked the dedicated `agency_os_migrator` role. The local disposable Compose harness creates that role via `docker/postgres/test-init.sql`. This is a test-environment mismatch; it is not evidence that the migration set passes or fails in a correctly initialized PostgreSQL environment.

Per project direction, do not spend this consolidation increment redesigning GitHub Actions. Validate through the checked-in PostgreSQL Compose harness and the user's local environment; report any CI-only discrepancy separately.

## Non-negotiable merge gate

Do not merge PR #58 while migration/RLS correctness, worker recovery, tenant isolation or approval boundaries are unverified. Do not delete source branches until all relevant changes have been accounted for, branch tip SHAs archived, and ancestry checked against the merged integration commit.


## Follow-up source comparison (2026-11-26)

A direct file comparison against the candidate branches found that several foundations are **already present on the integration branch**. Do not copy the older branch versions over them:

- **Workspace authorization:** the integration branch already contains `v2c4e6a8b0d2_human_workspace_authorization.py`. Its revision ancestry is the same as the security candidate, but the integration copy includes SQLite interrupted-DDL/idempotency handling. Preserve the integration copy pending PostgreSQL validation; review its full RLS policies and grant backfill before acceptance.
- **RLS inventory:** integration `app/db.py` already has `REQUIRED_RLS_TABLES`, role verification and includes `workspace_grants` in the inventory. The standalone hardening candidate's inventory does not include that table. Do not replace the integration inventory with the candidate version. Still verify every tenant table against PostgreSQL's actual schema and policy catalogue.
- **Data Protection Gateway:** integration already has `app/data_protection.py` and `tests/test_data_protection.py`. The tenant-DPG candidate differs in recursive metadata sanitization and trusted internal identifier handling; do not replace the current file wholesale. Review the candidate delta for compatibility with runtime metadata and add focused tests only where a concrete gap is proven.
- **Tenant outreach integrity:** integration already contains the exact candidate migration `m3f9c2a7e514_enforce_outreach_tenant_integrity.py` (same blob SHA). Preserve it and run the PostgreSQL test `tests/test_tenant_integrity_postgres.py`.
- **Tool Gateway:** integration already has `app/tool_gateway.py`, `app/tool_gateway_routes.py`, `app/tool_registry.py` and `app/machine_identity.py`. The reviewed custom-tools candidate is older in key files; the integration Tool Gateway includes workforce capability checks and a stricter sanitized denial audit. Keep the integration implementation as the baseline; review the MCP branch only for protocol-adapter gaps, not as a replacement authorization layer.
- **Worker crash recovery:** integration `tests/test_worker_postgres.py` is byte-for-byte identical to the process-crash-recovery candidate and contains a real subprocess launch. The lease-recovery candidate's file is older/different and must not overwrite the integration test. Review whether its distinct concurrent claim/lease/outbox cases are already covered before adding tests.

These are source-level comparisons only. They do not establish that PostgreSQL RLS, DPG behavior, Tool Gateway authorization or process recovery passes at runtime.


### Additional domain and MCP comparison

- **Revenue/Delivery and Contracts/Onboarding:** the integration branch already contains the candidate contract and onboarding migrations, domain/operations/outreach routes, and Founder Console pages for contracts, onboardings, opportunities, outreach, research-outreach and retainers. Candidate branches are heavily behind the integration line and overlap these files. Treat their remaining differences as targeted review items, not missing feature bundles. No external email/payment/telephony action is enabled merely by these records existing.
- **MCP adapter:** the MCP candidate adds a stateless Streamable HTTP façade, session-bound credentials, host/origin controls and read-only tool filtering. It is not safe to copy directly: its credential migration references parent revision `p6d8e2a4f913`, which is absent from the integration branch and was not found at the expected path on the candidate branch; its MCP tool dispatcher also passes `max_calls_per_session` and `allowed_tool_keys` arguments to `invoke_registered_tool`, which do not match the current integration service signature. The adapter must be ported against the current OS Tool Gateway, with the credential migration re-parented only after schema/lineage review. Keep this item **blocked for adaptation**, not accepted as complete.
- **Outreach implementation boundary:** the integration `app/outreach/routes.py` explicitly prepares an approved queue and stop controls; it states that it does not send email. This is the correct safe boundary until an external sender adapter, sender authorization, suppression/consent, idempotency, and reply/bounce/opt-out handling are verified end-to-end.


### Evaluation Harness implementation increment

Added the deterministic `safety_security` evaluation pack, registered it alongside `rag` and `agent_workflow`, and added unit tests for positive evidence, missing evidence, forbidden outcomes, registration and gate evaluation. The pack requires explicit control evidence, approval evidence, no forbidden outcomes, tenant-isolation success and data-policy success; missing evidence fails closed. Added `docs/EVALUATION_HARNESS.md` to define the evidence contract and remaining release-gate work.

**Status:** source implementation and tests added; not executed in this session. The pack is not yet a trusted release gate: the current evaluation API accepts payloads from authorized workspace members, so signed runner attestation, immutable test/commit/environment manifests and a release-approval blocker remain unimplemented. Never treat caller-supplied booleans as proof of production security.

A follow-on increment adds a deterministic `regression` pack, registered with the Harness and tested for complete, partial, missing and empty required-check evidence. The pack requires every named check to be explicitly true and rejects an empty check set. `docs/EVALUATION_HARNESS.md` now documents both safety/security and regression evidence contracts. These tests are source-added and remain unexecuted until repository CI/local verification.
