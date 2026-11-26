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


### CI evidence checkpoint

GitHub workflow run **45844644766** (run #1404) tested the PR merge ref at the then-current PR head `aab8ba149ee5e6d9ce2173fc2f7db7791209cdc0`, not the later regression-pack commits. Frontend TypeScript check and production build passed. Backend Alembic graph validation passed, but PostgreSQL migration application stopped at `t0a1b2c3d4e5_postgresql_tenant_row_level_security.py` because the workflow's PostgreSQL service did not initialize role `agency_os_migrator`. Python compilation and backend/PostgreSQL tests were skipped. This confirms the known harness mismatch; it does not validate the backend. The newly added regression pack commits occurred after this run and have no recorded workflow run yet.


## Outbox observability increment (2026-11-26)

A founder-only, workspace-scoped read endpoint has been added at
`GET /v1/orgs/{org_id}/workspaces/{workspace_id}/outbox/summary`.
It requires active organization membership, an exact active workspace grant,
and explicit Founder Authority (organization owner role alone is insufficient).
The response contains only counts by delivery state, oldest pending age,
expired lease count, exhausted pending count and an as-of timestamp. It does
not expose event payloads, idempotency keys, worker IDs or provider error text.

The aggregate service has focused SQLite tests for workspace scoping,
payload non-disclosure, expired leases and exhausted pending work. These tests
were added but have **not been executed** in this environment. PostgreSQL RLS,
HTTP authorization and browser/dashboard integration remain awaiting local
verification. The endpoint is an API foundation; no Founder Console widget
has been claimed.


### Test-gate audit (2026-11-26)

Latest PR-head workflow run #1431:
- Frontend dependency install, TypeScript check and production build passed.
- Alembic graph validation passed.
- PostgreSQL migration application failed before Python compilation or pytest because the CI service does not create the `agency_os_migrator` role required by the migration ownership statements.
- Python compilation and backend/PostgreSQL tests were skipped. This is an environment/bootstrap failure, not evidence that backend tests pass or fail.

Coverage present on the integration branch:
- Execution controls: queued/running cancellation, workspace boundary, retry-wait cancellation, pause acknowledgement, resume/session reuse, runtime capability rejection and stop-over-pause.
- PostgreSQL worker integration: concurrent claims, expired lease recovery, outbox concurrent claims/recovery/dead-letter, and real subprocess kill/recovery. These require the isolated PostgreSQL test stack and must not be replaced by SQLite-only tests.
- Outbox unit/migration tests: handler allowlist, leases, success acknowledgement, retry/redaction, dead-letter, reconciliation and migration idempotency.
- Tenant/security: workspace grant migration, RLS dialect checks, machine identity expiry/revocation, workspace/data-class scope, Tool Gateway grants, idempotent replay and audit redaction.
- Managed Agents: provider session reuse, tool approval boundaries, policy checks, retries, interrupt/pause/resume and custom-tool execution.
- Evaluation: RAG/agent workflow and the new safety/security and regression packs.

## Local verification checkpoint (2026-11-26)

The user ran the following checks against local checkout of integration head
`4dcd3a99a81977de349712e56919b4a63e82982d` and reported these results:

- Full Python suite: **443 passed, 8 skipped, 2 warnings**.
- Isolated PostgreSQL Docker harness: **59 passed, 2 warnings**. The harness initialized its dedicated roles and completed its PostgreSQL test target.
- API suite: **16 passed, 2 warnings**, including outbox summary authorization, Founder Authority, workspace grant, cross-workspace exclusion and payload-free response checks.
- Approval policy suite: **11 passed**.
- Python compilation: `python -m compileall -q app tests` completed with no output/errors.

These are user-reported local results, not independently executed in this repository-inspection environment. The SQLite skips are not counted as PostgreSQL passes; the separate Docker harness is the PostgreSQL evidence. Deprecation warnings did not fail the reported test runs.

Remaining acceptance tests before PR can leave draft:
1. Add race/idempotency tests for pause/resume/cancel vs lease expiry, retry and worker acknowledgement; assert one terminal outcome and complete audit.
2. Exercise approval consumption and the protected action under concurrent PostgreSQL requests; exactly one transaction may consume the approval and perform the action.
3. Add trusted-runner provenance/replay tests before treating Evaluation Harness results as release-grade evidence.
4. Run frontend workflow controls against API capability differences (pause-after-start only for runtimes that support safe interruption), plus browser E2E for pause/resume/stop and error states.
5. Complete remaining migration/RLS, tenant-isolation, backup/restore and release-readiness checks from the phase ledger.

The outbox summary API authorization and workspace-isolation tests are now executed and passed in the user's local API test run. This does not establish browser/dashboard integration or PostgreSQL-specific route concurrency behavior.

### PostgreSQL harness verification update (2026-11-26)

The project owner ran the isolated PostgreSQL Compose harness against integration commit `019de10c16f6460f208b109fd40d0a324b5d546a` after adding the expired-worker cancellation acknowledgement regression:

- Command: `docker compose -p agency-os-pg-test -f docker-compose.postgres-test.yml up --build --abort-on-container-exit --exit-code-from postgres-tests postgres-tests`.
- Result: **61 passed, 2 warnings in 2.66s**, exit code 0.
- The run included the PostgreSQL approval-consumption concurrency test and the expired-lease recovery/stale-worker acknowledgement test. The latter verifies recovery clears the expired lease, a stale acknowledgement is rejected, the execution remains in retry state, and no cancellation audit event is emitted.
- Warnings were Starlette/Authlib deprecations concerning the `httpx` compatibility layer; they did not fail the run.

This is owner-reported runtime evidence for the isolated PostgreSQL harness at that exact commit. It does not establish full RLS/tenant isolation across all API, file, cache and worker surfaces, browser E2E, backup restore, trusted evaluation attestation, or production readiness. The harness should be rerun after any subsequent backend or migration changes.

### Tenant-isolation source audit (2026-11-26)

The PostgreSQL Compose harness includes `tests/test_tenant_rls_postgres.py`, `tests/test_worker_rls_postgres.py`, `tests/test_tenant_integrity_postgres.py`, and the static RLS migration/context inventory tests. The owner-reported 61-pass run therefore exercised the dedicated app-role and worker-role RLS tests as configured by the harness (the run output reported no skips). Specifically, the app-role test checks exact workspace grants, cross-org/workspace read/write denial, revocation taking effect on a reused pooled connection, browser-session token-hash isolation and context reset; the worker-role test checks NOBYPASSRLS, workspace-scoped task reads, no-context denial and restricted browser-session access. This is useful runtime evidence, but coverage is still focused on representative tables and paths rather than every tenant-owned resource/API/file/cache surface.

**Security limitation identified during source review:** RLS predicates currently trust transaction-local custom PostgreSQL settings such as `agency_os.user_id`, `agency_os.machine_org_id` and `agency_os.machine_workspace_id`. The API and worker roles can set arbitrary custom GUC values themselves. Consequently, these policies provide strong defence against accidental unscoped ORM queries and connection-pool context leakage, but they are not an independent security boundary against arbitrary SQL executed with those role credentials or a compromised API/worker process. In particular, the worker's `worker_workspace_scopes()` function intentionally exposes the org/workspace inventory needed for central polling, and the worker can set its machine scope to any returned workspace. Do not describe this design as resistant to a compromised worker credential.

**Required hardening decision before production or merge as a complete tenant-isolation control:** introduce a database-verifiable, non-forgeable scope assertion (for example, short-lived signed scope claims validated by narrowly granted SECURITY DEFINER functions, with signing authority kept outside the worker and verification material inaccessible to app/worker SQL roles), or use genuinely workspace-scoped database identities/credentials. The implementation must cover human and machine context, grant/revoke functions, execution attempts, and connection-pool reuse. Add negative PostgreSQL tests that attempt to forge a wider scope directly from the app and worker roles and prove the database rejects it. Do not weaken current RLS checks while this is unresolved.

**Current classification:** RLS schema/policy coverage and representative live isolation tests are implemented and owner-tested; protection against forged custom-GUC context is a known security gap requiring design and PostgreSQL proof. Full tenant-isolation acceptance remains **blocked**.
