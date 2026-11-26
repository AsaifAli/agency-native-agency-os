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

### Signed tenant-scope hardening plan (2026-11-26)

The current GUC trust issue is a security-boundary defect, not a missing predicate. Do not attempt to fix it by signing a workspace ID in the worker process: the worker currently enumerates all workspace scopes, so a worker-held signing key would let a compromised worker mint a valid token for any workspace.

#### Required target contract

1. RLS policies must consult only database-validated, transaction-local identity/scope values. Raw caller-settable `agency_os.user_id`, `machine_org_id`, `machine_workspace_id`, `machine_identity_lookup_id` and browser-session digest settings must never be sufficient authorization inputs.
2. Human scope assertions must be signed by the API trust boundary. The signing secret must be available to the API issuer and a narrowly scoped database verifier, but not readable by `agency_os_app` SQL or any worker process. The database verifier must validate signature, key ID, expiry, issuer/audience, scope kind and canonical claim encoding before setting trusted transaction-local values. Revocation and workspace grants must still be checked by RLS predicates at query time; a valid signature is not a substitute for live authorization.
3. Worker scope must be bound to an actual execution/attempt lease. The worker must not be able to request a signed assertion for an arbitrary org/workspace. The intended boundary is a database-owned atomic claim operation that validates the worker role, claims one eligible execution under the existing lease/idempotency rules, and establishes the exact parent execution workspace for that transaction. Follow-on heartbeat, control, completion and failure operations must prove the same execution/attempt/worker tuple. Maintenance operations need separate bounded SECURITY DEFINER contracts rather than a general workspace-scope minting endpoint.
4. All trusted values must be transaction-local and cleared/replaced on every transaction. Pool reuse, nested sessions, rollback, commit, and thread heartbeat sessions must not inherit another scope.
5. API and worker roles remain non-owner and NOBYPASSRLS. No SECURITY DEFINER function may expose signing material, arbitrary scope selection, generic SQL, or an unrestricted table-wide bypass.

#### Delivery sequence

- **A. Threat-model tests first:** add PostgreSQL tests demonstrating direct GUC forgery for the API and worker roles, then convert them into denial assertions once the trusted path exists. Include role privilege/catalog assertions, signature tampering/expiry/audience/key-rotation cases, revoked-grant checks, cross-workspace and cross-org attempts, and pool reuse.
- **B. Human assertion path:** add an explicit API-only signing configuration and provisioning/rotation procedure for a verifier key held in a private database schema. Add a SECURITY DEFINER verifier with a fixed search_path and strict claim schema; update authentication middleware and RLS policies to use only verifier-set trusted context. Keep browser-session bootstrap narrowly scoped and prevent arbitrary token-hash impersonation.
- **C. Worker claim path:** move lease claim and exact workspace context establishment into an atomic database-owned operation (or an equally strong separate claim broker). Do not expose an API that signs arbitrary worker-supplied scope. Bind every worker mutation to the leased execution and attempt. Review global maintenance and outbox paths separately.
- **D. Rollout:** support a controlled dual-read migration only during a bounded migration window; then remove raw-GUC policy references and reject legacy context calls. Test migrations from the current revision and downgrade/restore strategy on a disposable PostgreSQL instance.
- **E. Acceptance:** PostgreSQL tests must prove that direct raw GUC writes cannot widen access, API/worker roles cannot read signing material, forged/expired/replayed/wrong-audience assertions fail, revoked grants take effect, and a worker cannot access a workspace without a valid leased execution. Run the complete existing SQLite and PostgreSQL suites, plus role/catalog inventory checks.

#### Explicit non-goals

- Do not use a signing key shared with the worker.
- Do not make the worker a superuser, table owner or BYPASSRLS role.
- Do not treat the current `worker_workspace_scopes()` inventory as authorization evidence.
- Do not claim resistance to a fully compromised API process: the API is the human identity assertion issuer and remains a trusted application boundary. The database must, however, reject forged claims from stolen app/worker database credentials alone.

**Status:** design and threat boundary documented; implementation not yet started or verified. PR remains draft until both human and worker paths are complete and negative PostgreSQL tests pass.


### Follow-up source audit: worker role contract and scope establishment (2026-11-26)

A second source pass inspected `app/db.py`, `app/auth.py`, `app/config.py`, `app/worker/runner.py`, `app/worker/processor.py`, `app/worker_service.py`, the PostgreSQL RLS migrations, the Compose test harness and the live role tests.

Additional findings:

- `app/worker/runner.py` calls `list_worker_scopes()`, loops over every returned org/workspace pair, and creates a `scoped_worker_session_factory(org_id, workspace_id, ...)`. This is a direct application-level arbitrary-scope selection path, not merely an internal queue scheduling detail.
- `app/worker/processor.py` performs the initial claim, start, heartbeat and subsequent execution mutations through that caller-selected session factory. `claim_next_execution()` in `app/worker_service.py` is an ORM transaction, not yet a database-owned claim-and-bind operation. The follow-up hardening must therefore change both the worker polling contract and the lease lifecycle boundary; changing only RLS predicates or deleting the inventory function would break the worker.
- `migrations/versions/t0a1b2c3d4e5_postgresql_tenant_row_level_security.py` builds RLS predicates directly from caller-settable `current_setting(...)` values. `u1b2c3d4e5f6_worker_nobypassrls_scope.py` narrows worker table privileges and adds bounded maintenance functions, but its `worker_workspace_scopes()` function returns all workspace IDs and does not bind a scope to a lease.
- The worker role is intentionally `NOBYPASSRLS` in `docker/postgres/test-init.sql`, and the Compose grant step explicitly runs `ALTER ROLE agency_os_worker NOBYPASSRLS`. However, `app/config.py` production validation currently rejects `agency_os_app` as the worker URL user with an error saying the worker must use a dedicated **BYPASSRLS** worker role. That contradicts the migration, test role setup and stated security contract. This validation text/condition must be corrected as part of the worker-role hardening, with a configuration regression test; do not change the database role to BYPASSRLS to satisfy the incorrect check.
- `set_rls_context()` stores raw identity and scope values in `Session.info` and writes them with `set_config(..., true)`. It also reapplies them after transaction begin. The API path currently sets the human user ID after bearer/browser-session authentication; the worker path sets org/workspace directly. Browser-session bootstrap uses a separate token-hash GUC. All three paths need an explicit trusted replacement, not a partial conversion.

#### Implementation guardrails added by this review

- Preserve the current NOBYPASSRLS app and worker roles; do not “fix” the config mismatch by granting BYPASSRLS.
- Do not add a generic SECURITY DEFINER function that accepts org/workspace arguments from the worker. The claim function must derive scope from the selected eligible execution under lock and bind the claim to the worker/attempt tuple.
- Keep global retention, outbox dispatch/reconciliation, machine-session expiry, retry promotion and expired-lease recovery as separate reviewed operations. Each needs a bounded contract and must not depend on arbitrary workspace scope selection.
- Treat the existing 61-pass PostgreSQL result as historical evidence for the previous code only. No signed-scope implementation or new PostgreSQL verification has been performed in this follow-up.

**Status update:** source audit refined; implementation remains not started. Tenant-isolation acceptance remains blocked. No runtime tests were run in this environment, and no production configuration or database role was changed.


### Worker role configuration correction (2026-11-26)

A small, isolated inconsistency was corrected before beginning the larger scope redesign:

- Production configuration rejected `agency_os_app` for `PROCESS_ROLE=worker`, which is correct because the worker must use its dedicated login.
- The validation error incorrectly described that dedicated login as `BYPASSRLS`. The database migration and disposable PostgreSQL role setup explicitly require `agency_os_worker NOBYPASSRLS`.
- Updated the validation message to require the dedicated **NOBYPASSRLS** worker role; the database role itself was not changed.
- Added production Settings regression tests for acceptance of the dedicated `agency_os_worker` login and rejection of `agency_os_app` with an explicit NOBYPASSRLS contract.

Commits:
- Test first: `c95abd5e86d8e1cb1d5e9e942302f5de1c7e2f0c`
- Corrected test hostnames: `c1475a3416a85f022f9bd61f16bd2ee8d88123d8`
- Configuration correction: `04b5f9f078985119ad4b9afe2048e8eba897a7cf`

**Verification:** not run in this environment. The tests are committed as regression coverage but are not yet runtime-verified. This correction does not resolve raw GUC forgery, worker arbitrary-scope selection, or full tenant-isolation acceptance.


### Production database login allowlist tightened (2026-11-26)

Follow-up to the worker-role mismatch: the production settings validator previously rejected only one known wrong username for each process type. That meant an unrelated login (including a privileged login) could pass this part of application configuration validation.

Changes on the existing integration branch:
- API process now requires the exact `agency_os_app` login.
- Worker process now requires the exact `agency_os_worker` login.
- Both roles are expected to remain non-owner, non-superuser, **NOBYPASSRLS** roles; database startup role verification remains the independent database-side check.
- Added tests for the accepted worker login, worker rejection of the API login and an unrelated `postgres` login, and API rejection of the worker login.

Commits:
- `41d15816f7adc2e93dbc74e8772bddf9af0acc42` — regression tests first
- `ff9d51ca17c1a886397af30ff14b738c33f7de7a` — exact role allowlist

**Verification:** not executed here. The new regression tests must be run in the repository environment. This narrows production configuration acceptance but does not remove caller-forgeable RLS GUCs or the worker's arbitrary workspace-scope inventory path. Tenant-isolation acceptance remains blocked.


### Production worker startup role verification (2026-11-26)

Added a fail-closed production startup check in `app/worker/runner.py`:
- A production worker must run with `PROCESS_ROLE=worker`.
- Its actual worker engine connection is checked with `verify_postgres_role(... expected_bypassrls=False, require_rls=True)`.
- The check therefore validates PostgreSQL role attributes and the complete required FORCE-RLS/policy inventory before the polling loop starts.
- Non-production test/development runs skip this production-only check.

Regression tests were committed before implementation:
- `4f4ac0c10430ae5eac7aa535bb0f151c038f345c` — tests for valid production worker, wrong process role, and non-production behavior.
- `ab8e475701083db86e61ea0a99aa69f6e710a61d` — startup enforcement.

**Verification:** not run in this environment. This is defense-in-depth around role misconfiguration; it does not solve raw caller-settable RLS GUCs or replace the planned database-owned worker claim/lease authorization. Tenant-isolation acceptance remains blocked.


### Worker fail-closed startup regression (2026-11-26)

Added a regression test proving that a production worker does not call workspace inventory/polling if PostgreSQL role verification fails. The test asserts the startup exception propagates and the scope-enumeration function is never reached.

- `c99bbb0cd6e37b23f49730a4f08b0eace4173128` — regression test.

**Verification:** committed but not executed here. No additional runtime behavior changed in this increment. This protects the existing startup guard; it does not address the deeper arbitrary-workspace worker authorization issue.


### Exact PostgreSQL login verification (2026-11-26)

Strengthened production startup verification to check the actual PostgreSQL `current_user` against the exact dedicated role, not only its SUPERUSER/BYPASSRLS flags and table ownership.

- API startup now requires `agency_os_app`.
- Worker startup now requires `agency_os_worker`.
- The shared verifier rejects an empty expected role and reports a generic exact-role mismatch without exposing connection details.
- Added/updated regression tests for the worker verifier call and required expected-role argument.

Commits:
- `d9c4d0107922f6904e6e8c3224d4f432f24caec7` — worker verifier contract test.
- `baa67b91bdf92150c508fa3150949ce6ee4eaa77` — enforce exact current database role in verifier.
- `cc8ffcab82f8bcdf140ee9bf6b244bf597269df5` — pin API startup to `agency_os_app`.
- `9cda0d1291d0369d4ea91cbdaeac8d22ccd376d4` — pin worker startup to `agency_os_worker`.
- `9f67d9646c1c04cd3d10a7bae207115eec8b0c95` — verifier argument validation test.

**Verification status:** source changes committed; tests not yet executed in this environment. The verifier still needs live PostgreSQL tests for actual role mismatch, and this does not resolve the caller-settable RLS GUC issue.


### Verification run and complete call-site correction (2026-11-26)

A clean ephemeral Python sandbox cloned the integration branch and installed `requirements-dev.txt`. This enabled real repository tests without modifying the user's local environment.

**Executed successfully on the sandbox (Python 3.13.18):**
- `env -u MIGRATION_DATABASE_URL DATABASE_URL=sqlite:////tmp/agency-os-api-tests.db python -m pytest -q --tb=short` — **452 passed, 10 skipped, 2 deprecation warnings** (31.47s).
- `python -m compileall -q app tests` — passed.
- `python -m alembic heads` — one head: `w3d5f7a9b1c3`.
- Focused RLS context and worker startup suite — **21 passed**.
- Repository-wide call-site search identified two additional exact-role verifier callers missed in the first pass. Updated standalone worker entrypoint and both live PostgreSQL RLS test suites to pass the exact expected role.

**Not executed:** PostgreSQL Docker harness and live PostgreSQL RLS tests. The sandbox has no Docker daemon and no configured PostgreSQL test credentials. Ten skips are the PostgreSQL-only tests requiring those services/URLs. This run does not prove database role mismatch rejection against a live server, nor fix caller-settable GUC trust.

Commits after the prior ledger entry:
- `166cfc577b2188b3100e330c7a4cff7fe302f96e` — exact app role in live RLS test.
- `85bbd213d6238550d8ee726bd1923b5087cb5834` — exact worker role in live RLS test.
- `40dd96777f82856a52a8bc1b18e7c321de57e18c` — exact worker role in standalone process entrypoint.

Tested branch head: `40dd96777f82856a52a8bc1b18e7c321de57e18c`.


### RLS identity and context call-site inventory (2026-11-26)

A call-site inventory was completed before changing the RLS trust mechanism. This is a source-level inventory, not proof that each route is secure at runtime.

| Context kind | Current call sites | Current trust input | Required replacement boundary |
|---|---|---|---|
| Human user identity | `app/auth.py`, `app/main.py` | Authenticated bearer/browser-session result is copied into `agency_os.user_id` | API-issued signed assertion, verified by PostgreSQL; live membership and workspace grants remain checked by RLS |
| Browser-session bootstrap | `app/browser_sessions.py` | Raw token hash copied into `agency_os.browser_session_token_hash` to locate the session, then resolved user copied into `agency_os.user_id` | Narrow verifier function for token-hash lookup; then signed human assertion for subsequent access; do not expose token hash or signing material to app-role SQL |
| Machine identity bootstrap/use | `app/machine_identity.py` | Lookup ID and then org/workspace are copied into `agency_os.machine_identity_lookup_id`, `agency_os.machine_org_id`, and `agency_os.machine_workspace_id` | Narrow machine-identity verifier bound to the authenticated credential and current active identity; do not accept caller-selected org/workspace as authority |
| Public website intake | `app/website_intake_routes.py` | Configured org/workspace identifiers copied directly into machine GUCs | Dedicated intake capability scoped to the configured target and operation; must not inherit a general-purpose worker scope mechanism |
| Worker execution | `app/db.py` via `scoped_worker_session_factory`, called from `app/worker/runner.py` | Worker enumerates all workspace IDs, then sets org/workspace GUCs itself | Database-owned claim-and-bind transaction: claim one eligible execution, derive scope from its row, and bind every lease mutation to execution/attempt/worker tuple |

The migration search also confirms the GUCs are consumed across the base tenant RLS migration and the human workspace-authorization migration, including organizations/workspaces, execution/attempt paths, machine identities, browser sessions, and outbox policy logic. A migration must update the complete policy/function inventory atomically; changing only the most obvious task policy would leave alternate data paths exposed or break authentication bootstrap.

#### Safe implementation order

1. Introduce PostgreSQL verifier primitives and role/privilege checks without removing the existing GUC policies. Keep verifier secrets unreadable to `agency_os_app` and `agency_os_worker`; the API can only submit signed assertions, not retrieve signing keys.
2. Add human and browser-session negative PostgreSQL tests (forged user GUC, token-hash lookup boundaries, expired/tampered assertion, revoked membership/grant, key rotation, and pooled-connection reuse).
3. Add machine-identity and public-intake capability tests, including revoked/disabled identity and attempts to select another workspace.
4. Implement worker claim-and-bind as a DB-owned atomic operation. Keep provider calls outside the transaction; heartbeat, control, completion, failure, and recovery must prove the exact live lease tuple.
5. Separate maintenance/outbox/retention operations into narrowly parameterized, bounded database contracts. Do not reintroduce a generic org/workspace scope-minting function.
6. Switch callers and RLS policies only after both old and new paths are covered; then remove raw GUC trust and the all-workspace inventory function in a single reviewed migration sequence with rollback/restore evidence.

**Status:** inventory complete at source level. No RLS policy, identity flow, migration, or runtime behavior was changed in this increment. The signed human/machine assertions and worker claim-and-bind remain unimplemented. PostgreSQL negative tests are still required before tenant-isolation acceptance.


### Protected-action transaction boundary review (2026-11-26)

Reviewed all six application call sites of `require_approved_action()` in `app/operations_routes.py` and `app/outreach/routes.py`.

| Protected action | Route mutation after approval consumption | Transaction observation |
|---|---|---|
| `invoice.issue` | Records invoice as issued, external reference/time/actor, audit event and outbox event | Same request session; one commit after all writes |
| `delivery.activate` | Creates project, activates onboarding, records actor/time, audit event and outbox event | Same request session; one commit after all writes |
| `contract.execute` | Records executed contract and signed evidence, audit event and outbox event | Same request session; one commit after all writes |
| `pricing.change` | Marks proposal approved and records approver/time, audit event and outbox event | Same request session; one commit after all writes |
| `scope.change.accept` | Updates project budget/contract value/hours/due date and scope request decision, audit event and outbox event | Same request session; one commit after all writes |
| `external_communication.sensitive` | Moves outbound message to queued, records queue metadata, audit event and outbox event | Same request session; one commit after all writes; this route queues but does not send |

The helper's conditional one-time approval-consumption update and `approval.consumed` audit flush occur on the caller's session. The inspected routes commit only after the protected business mutation and associated audit/outbox writes, so rollback should revert the consumption together with the protected state change. Existing action-policy tests cover rollback and single-use semantics; the dedicated PostgreSQL race test covers two competing consumers at the helper boundary.

**Limitations:** this was source inspection. It does not establish that every database trigger/provider adapter is side-effect-free before commit, nor does the single PostgreSQL race test cover every route under concurrent requests. Keep provider/network calls outside the transaction and add route-level PostgreSQL rollback/race tests for high-impact protected actions before production readiness.

**Status:** no code behavior changed in this review. The six inspected application paths have the intended single-transaction shape; PostgreSQL route-level concurrency coverage remains partial.


### Verification refresh and worker-scope implementation gate (2026-11-26)

At PR code head `df36a07b2eae19cc22c9caaf15e8bff98cac66e8`, the disposable Python 3.13.18 sandbox reran:

- `env -u MIGRATION_DATABASE_URL DATABASE_URL=sqlite:////tmp/agency-os-api-tests.db python -m pytest -q --tb=short`: **452 passed, 10 skipped, 2 deprecation warnings**.
- `python -m compileall -q app tests`: passed.
- `python -m alembic heads`: exactly one head, `w3d5f7a9b1c3`.
- `git status --short`: clean.
- PostgreSQL-only tests were skipped because no PostgreSQL test URLs/Docker daemon are available in this sandbox. This run does not replace the user's earlier 61-test PostgreSQL result, which was at an earlier code head.

#### Worker-scope implementation gate

The worker source review confirms that `run_worker()` enumerates `worker_workspace_scopes()`, constructs `scoped_worker_session_factory(org_id, workspace_id)`, and uses that factory for execution processing, retry promotion, lease recovery, delegation queueing, machine-session expiry, and outbox dispatch. Browser-session pruning is a separate bounded SECURITY DEFINER operation.

A partial change that merely removes the inventory function and adds a no-argument SQL claim function would be misleading: current RLS policies still trust worker-settable `agency_os.machine_org_id` and `agency_os.machine_workspace_id` settings, and the worker has direct table privileges for the existing service operations. A genuine boundary requires migrating all execution/attempt reads and writes, heartbeat/provider-run attachment, cancellation, retry/recovery, delegation synchronization, and workspace-bound outbox work to narrowly scoped database contracts, then revoking direct worker access where appropriate. It must also prevent the worker role from minting a workspace scope through custom GUCs. This is a coordinated schema + service + runner migration, not a safe one-file patch.

**Decision:** do not introduce a partial claim function or remove the existing inventory yet. Preserve the known-working worker path while designing the full contract inventory and PostgreSQL tests first. The raw GUC trust weakness remains a critical, explicitly open security finding; current worker NOBYPASSRLS and scope tests protect against accidental unscoped access and pool leakage, not malicious SQL under a compromised worker credential.


### Evaluation evidence trust boundary (2026-11-26)

The ordinary workspace evaluation API accepts caller-supplied `expected` and `actual` payloads. Those values can be useful for exploratory scoring, but they are not proof that a trusted test runner executed the controls. A caller could otherwise submit a passing `safety_security` or `regression` result and have it appear indistinguishable from verified release evidence.

The integration branch now persists `evaluation_runs.evidence_trust` with a migration default of `self_reported`. The normal API explicitly writes `self_reported`; `EvaluationOut` exposes that trust label and reports `release_eligible=false`. The API does not accept a client-supplied trust flag. Existing rows are backfilled by the migration default as self-reported.

Verification at integration head `56137e1ce8f642f18fed6f66c4f3026a57e3895c`:
- Evaluation API focused tests: **2 passed**, including create and list responses for a passing self-submitted safety/security payload.
- Full suite: **453 passed, 10 skipped, 2 deprecation warnings**.
- `python -m compileall -q app tests`: passed.
- `python -m alembic heads`: single head `x4c8d1e6f902`.
- Full SQLite Alembic upgrade through `x4c8d1e6f902`: passed.

**Limitations:** there is still no trusted runner attestation issuer/verifier, immutable run manifest, signed artifact digest, or non-bypassable release integration. Therefore all API-created evaluations remain ineligible for release gating. This is a fail-safe classification improvement, not completion of the Evaluation Harness release gate. PostgreSQL migration and RLS verification remain pending.


### Worker capability-boundary regression tests (2026-11-26)

Added `tests/test_worker_capability_boundary_postgres.py` and included it in `Dockerfile.postgres-test`.

- `test_forged_workspace_gucs_do_not_authorize_worker_reads` uses the actual `agency_os_worker` login, sets the legacy `agency_os.machine_org_id` and `agency_os.machine_workspace_id` values, and asserts that a synthetic tenant task remains invisible without a lease capability.
- `test_worker_cannot_read_private_lease_capability_storage` requires the private capability table to exist, asserts the worker has no SELECT privilege, and asserts a direct read is rejected.

**Verification at code commit `8c3dce0ce5a9afbee301a483ce7660fb40f8b000`:** focused test collection succeeds but both PostgreSQL tests were skipped because the sandbox has no PostgreSQL URLs. Full SQLite/unit suite: **453 passed, 12 skipped, 2 deprecation warnings**; `compileall` passed. These tests are added but not yet demonstrated failing against the old PostgreSQL policy or passing after a capability cutover. Do not treat this as a security fix.

**Next gate:** run the isolated PostgreSQL harness with the actual worker role to establish the expected RED result for forged GUC authorization. Then implement the complete capability-backed claim/lifecycle/maintenance contracts and only later change RLS policies and grants. No worker privilege or RLS policy has been changed in this increment.


### Worker lease capability storage foundation (2026-11-26)

Added migration `y5e9a2c7d1f4_worker_lease_capability_storage.py` after `x4c8d1e6f902`. On PostgreSQL it creates:

- `agency_os_private.worker_lease_capabilities`: unique SHA-256 token hash, execution/attempt/worker/generation binding, expiry and invalidation timestamps.
- `agency_os_private.worker_transaction_context`: transaction-bound backend PID + transaction ID context linked to a capability and its exact execution tuple.
- Both tables are owned by `agency_os_migrator`; direct privileges are revoked from PUBLIC, `agency_os_app` and `agency_os_worker`.

Verification on integration head `9b30cd3ab24dc448da9e878772ac8b0ab8aee913`:
- Alembic reports a single head: `y5e9a2c7d1f4`.
- Full SQLite migration upgrade through the new revision: passed (PostgreSQL-only DDL intentionally no-ops on SQLite).
- Full unit/API suite: **453 passed, 12 skipped, 2 deprecation warnings**.
- `python -m compileall -q app tests`: passed.

**Not yet verified:** PostgreSQL execution of this migration, actual table ownership/privileges, SECURITY DEFINER verifier, claim/capability issuance, RLS context consumption, and worker runtime conversion. The prior live PostgreSQL run confirmed forged worker GUCs still authorize cross-workspace reads. The migration is storage groundwork only; no RLS policy or worker direct-table grant was changed. The worker vulnerability remains open and the forged-GUC PostgreSQL regression is expected to remain RED until the full cutover.


### Worker capability verifier increment (2026-11-26)

Added migration `z6f1b3d8a2c5_worker_capability_verifier.py` and mapped `ExecutionAttempt.lease_generation`.

The PostgreSQL migration:
- Adds a positive lease generation to execution attempts (existing attempts default to generation 1).
- Adds SECURITY DEFINER `agency_os_private.establish_worker_execution_context(bytea,text,text,text,integer)` with a fixed search path and migration-role ownership.
- Requires the real `agency_os_worker` session, a 32-byte presented token, exact execution/attempt/worker/generation match, non-invalidated/unexpired capability hash, and a still-live claimed/running attempt and execution.
- Writes verified context only into the private transaction-context table; it does not accept caller-set workspace GUCs as proof.
- Grants EXECUTE to `agency_os_worker` only; PUBLIC and `agency_os_app` are revoked. Worker cannot directly INSERT into the private context table.

Added PostgreSQL test `test_worker_can_only_establish_context_through_capability_verifier` for function presence, execute grant, denied direct context INSERT, and rejection of a nonexistent capability.

Verification on integration source through commit `695922142d7dfefccc60f386d236edf7d8c7a30d`:
- Single Alembic head: `z6f1b3d8a2c5`.
- Full SQLite migration upgrade: passed (PostgreSQL-specific function DDL intentionally no-ops on SQLite).
- Full unit/API suite: **453 passed, 13 skipped, 2 deprecation warnings**.
- `python -m compileall -q app tests`: passed.

**PostgreSQL verification is still required** for this new function, notably whether the target PostgreSQL version provides `sha256(bytea)`, SECURITY DEFINER ownership/search path and exact grants. The live forged-GUC regression remains open: RLS policies still trust historical worker GUCs and broad worker table privileges remain. The verifier is not yet called by the worker runtime; capability issuance/claim is not implemented; lifecycle/maintenance contracts are not converted; no RLS policy cutover has occurred. Do not represent this increment as fixing worker tenant isolation.


### Specialist profiles and team blueprint adoption (2026-11-26)

Adapted selected ideas from `msitarzewski/agency-agents` (MIT-licensed upstream) into the existing workforce registry without importing its installer, runtime, desktop app or full agent catalogue.

Implemented:
- `app/workforce_blueprints.py`: versioned, declarative specialist profiles and four scenario blueprints: client onboarding/delivery, enterprise feature delivery, evidence-backed marketing campaign, and incident response/recovery.
- Ten curated specialist profiles: Multi-Agent Systems Architect, AI Solutions Architect, Backend Architect, Database Reliability Engineer, AI Engineer, AI-Generated Code Security Auditor, Privacy Engineer, UI Finish-Gate Reviewer, Business Discovery Coach, and Content Strategist.
- Specialist definitions specify mission, responsibilities, inputs, outputs, non-responsibilities and review gate. They explicitly default to disabled and carry no tool grants.
- Blueprint tasks reference stable specialist keys, department keys, structured input/output contracts and explicit review requirements. Activation groups are limited to `always`, `phase`, `as_needed`, and `post_fix`.
- Catalogue validation checks unique keys/slugs, valid specialist-to-department references, valid activation modes and mandatory review. Definitions are read-only planning metadata; they cannot create permissions or execute tasks.
- Workspace-scoped read-only endpoints: `GET /v1/orgs/{org_id}/workforce/specialists?workspace_id=...` and `GET /v1/orgs/{org_id}/workforce/blueprints?workspace_id=...`. Membership and workspace access are checked before returning catalogue data.
- Founder Console workforce page displays specialist profiles and blueprint task groups.
- Tests cover catalogue contents, disabled/no-tool defaults, blueprint references, mandatory review, workspace isolation and operator read-only access.

Verification on integration source at `e59febcf7a5b96ff9c97b9778de6f79580657b05`:
- Focused workforce API tests: **25 passed**.
- Full Python suite: **456 passed, 13 skipped, 2 warnings**.
- `python -m compileall -q app tests`: passed.
- PostgreSQL-only tests were skipped because PostgreSQL test URLs were not configured in this environment.
- Frontend lint/build not yet run in this environment.

Not implemented by design: automatic activation, tool grants, blueprint execution/instantiation, or automatic external communication. Blueprints are currently read-only plans; the next phase can add founder-approved conversion into persisted OS task plans after worker authorization and execution security are complete.

Upstream attribution: specialist/blueprint concepts adapted from https://github.com/msitarzewski/agency-agents under MIT; no upstream agent files or installer code copied.


### Claude / Agency OS workforce boundary refinement (2026-11-26)

Refined the specialist catalogue adoption to preserve the intended runtime boundary:

- Moved the ten detailed specialist definitions (mission, responsibilities, inputs, outputs, non-responsibilities and review gates) into agents/specialists/catalog.py as source material reserved for the future Claude runtime integration. These are not executable agents and are not loaded as a runtime by the OS.
- Reduced app/workforce_blueprints.py specialist records to OS-owned identity/governance metadata: stable specialist key, title, department, Claude runtime ownership, source reference, catalogued status and disabled-by-default state.
- Kept versioned team blueprints in the OS as declarative workflow templates. They reference specialist keys and departments and retain structured task objectives, input/output contracts, activation phases and mandatory review gates.
- The specialist API now exposes only the OS registry metadata; it no longer returns detailed specialist instructions. The Founder Console labels these as Claude-owned profile references and no longer renders detailed agent behavior as OS-managed profiles.
- Updated the workforce API regression test to assert the separation: API payloads contain no mission/responsibility prompt content, while the detailed source catalogue remains available for the future Claude adapter.
- Updated agents/README.md to document the boundary. Claude will own specialist prompts, skills, reasoning, collaboration and delegation; the OS remains authoritative for identities, permissions, plans, approvals, budgets, execution records and audit. Claude tool access must pass through the OS Tool Gateway/MCP boundary.

Verification on the integration branch working tree based on ec56e022ee0172afc782b3c5135a66430c5cac82:
- Specialist/blueprint focused API tests: 3 passed.
- Full Python suite: 456 passed, 13 skipped, 2 deprecation warnings.
- python -m compileall -q app agents tests: passed.
- git diff --check: passed.
- PostgreSQL-only tests were skipped because test database URLs are not configured in this sandbox.
- Frontend lint/build was not run; frontend dependencies are not installed in this sandbox.

This is an ownership and presentation boundary refinement only. It does not implement the Claude Managed Agents adapter, MCP Tool Gateway, specialist provisioning, automatic collaboration, or blueprint execution. No agent was activated and no permissions were granted.
