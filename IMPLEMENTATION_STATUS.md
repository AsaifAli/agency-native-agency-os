# Agency OS implementation status — stabilization checkpoint

## Verified cleanup checkpoint
- Branch: `feature/agency-os-native-runtime-cleanup`.
- Commit: `80b989ae611b08d9a9c37925195517417ba79b05`.
- GitHub Actions run: [45471143658](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/45471143658) — **162 passed, 1 warning**.
- CI validated the Alembic graph, applied migrations to PostgreSQL 16, compiled Python source and ran backend plus PostgreSQL integration tests after the evaluation move and snapshot cleanup.
- The warning is the Starlette/httpx TestClient deprecation; no test failures were reported.
- Frontend TypeScript checking and Next.js production build are validated in main CI. Live Claude provider sessions, production deployment, backup restore drill, independent penetration test and compliance assessment are not claimed.

## Implemented source capabilities
- Governed workforce schema for offices, functional groups, departments, teams, human/agent/supervisor/sub-agent members, 121 durable position records, capability grants and task delegation lineage; backend migrations and tests passed.
- Founder-only, idempotent bootstrap for the Office of the CEO, five functional groups, 16 departments, 31 teams, 5 group heads, 16 department heads, 16 department specialist definitions, Chief of Staff, Executive Assistant and the full 121-position catalogue. Workforce profiles remain inactive until the founder explicitly enables an eligible capability and activates a member.
- Workspace-scoped workforce APIs and founder-only bootstrap, capability enablement, member activation and pause. Capability enablement checks autonomous action policy, public/synthetic data eligibility, configured runtime and absence of ungoverned tool grants. Delegation API enforces downward direct-manager relationships, active members, enabled agent definitions, enabled capability grants and founder exclusion. The cleanup commit passed backend CI (162 passed, 1 warning).
- Signed public website lead intake endpoint (disabled by default): fixed server-side org/workspace mapping, HMAC-SHA256 timestamp validation, body/schema bounds, constant-time signature/key checks, source idempotency, CRM Contact/Lead creation, audit and transactional outbox event in one transaction. No outreach or execution is triggered.
- Workspace-scoped, authenticated execution history API with bounded status filtering and result limits.
- Execution trace API that joins execution and attempt lifecycle audit events after verifying the execution belongs to the requested organization/workspace.
- Founder Console Processes page for execution history and event timelines; Monitoring page for persisted execution status/retry summaries; Workforce page for the org chart, team/position catalogue and member registry.
- Founder dashboard now reads pending approval counts and execution activity from existing APIs.
- Agent Studio department selector now exposes all 16 departments in the workforce blueprint.
- FastAPI modular backend and Next.js Founder Console foundation.
- Organization/workspace-scoped clients, contacts, leads, opportunities, projects and milestones.
- CRM relationship timeline: workspace-scoped append-only contact activities with notes, calls, emails, meetings, tasks and status updates; no activity creates an external communication.
- Founder Console Revenue workflow pages for Contacts, Leads, Opportunities and Proposals, including source/qualification notes, suppression reasons, opportunity stage progression and founder pricing approval.
- Agent, task, approval and audit foundations. Deterministic RAG and agent-workflow evaluation packs, metrics, weighted scores and quality gates are first-party modules under `app/evaluation/`; evaluation run persistence and audit remain in the OS database.
- Explicit Founder Authority separate from organization-owner membership; founder provisioning CLI and founder-only decisions.
- Single-use approval consumption with action/resource/workspace matching and active Founder Authority recheck.
- Central autonomy classification: allowlisted internal actions, founder-approval actions and manual-review default for unknown actions.
- Durable execution lifecycle with persisted attempts, worker claims, leases, heartbeats, bounded retries and expired-execution recovery.
- Mock runtime boundary and opt-in Claude Managed Agents adapter. Before a new session, the adapter inspects the provider Agent and fails closed if tools, MCP servers, skills or multiagent features are enabled; it tracks workflow runs and requires all runs to end plus a final end_turn before success.
- Managed Agents adapter persists session ID after create response, resumes persisted sessions, applies synthetic-only eligibility, sets a session budget, paginates event history, tracks open workflow runs and routes non-completion pauses to manual review.
- Transactional outbox writes for selected domain events; dispatcher supports registered-handler filtering, SKIP LOCKED claims, leases, bounded attempts, acknowledgement, sanitized errors, retries, dead letters and lease reconciliation.
- Founder-only outbox health endpoint.
- Workspace-scoped call/transcript records; no live voice provider or dialing.
- Delivery playbooks, founder-approved scope changes, time/cost records, provisional project financial summaries, exception inbox and execution reliability views.
- Founder-governed service catalogue with draft-first offerings, founder-only activation/retirement, immutable code/version revisions, workspace-scoped constraints and audit/outbox events.
- Proposal drafts linked to opportunities with single-use founder pricing approval.
- Contract register requires an approved proposal and records signed evidence before executed status; client onboarding requires an executed contract, evidence-backed checklist and founder approval before project activation.
- Invoice register requires an executed contract, prevents overbilling, requires single-use founder approval before issue evidence is recorded, and maintains an append-only payment receipt ledger. No payment collection is integrated.
- Curated Agent Skills catalog contains eighteen reviewed, source-pinned instruction packs with authenticated read-only catalog/detail APIs, license/provenance metadata, and per-file SHA-256 digests. All entries are disabled, tool-free, and limited to public/synthetic data; the catalog does not yet assign skills to workforce members or load provider-side Claude skills.
- Founder Console Skills & Tools page now browses the catalog, filters by category/search, and displays skill instructions, provenance, and SHA-256 digest through the authenticated API.
- Expanded 18-skill catalog CI run [45487106060](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/45487106060) passed PostgreSQL 16 migration validation, Python compilation, **177 backend tests (1 warning)**, frontend TypeScript checking, and the Next.js production build on code commit `524d6369bd98feef77818de412b7a978e66222b7`.
- Target organization model and workforce governance are documented in `docs/AGENCY_ORGANIZATION_WORKFORCE_BLUEPRINT.md` and `docs/REFERENCE_INTEGRATION_DECISIONS.md`; skill availability does not mean every role has a live runtime.

## Workforce/runtime gaps still open
- Workforce bootstrap provisions organisational profiles and positions inactive. Founder-only capability enablement and member activation are implemented as explicit, policy-checked operations; this does not automatically provision separate provider Agents or start Claude sessions.
- **Orchestration and authorization hardening (main commit `387d283bfe65f470cacc9b9a2785de8fce141b78`; CI run [45481253037](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/45481253037), 168 passed, 1 warning):** founder-authorized plans persist a root task, ordered child-task DAG, direct-manager delegation lineage, earlier-step dependency ordinals and workspace-scoped plan state. Plan creation requires an active non-founder Chief of Staff/supervisor with planning authority; all delegators must be within that creator's reporting subtree. Plan refresh is founder-only. Worker maintenance creates idempotent executions for eligible Agent assignments, releases dependent work after prerequisites succeed, and synchronizes task/delegation lifecycle state. Policy/runtime-blocked work remains blocked with a recorded reason and requires a founder requeue. Required review is founder-only and cannot pass before the child task is terminal.
- **Still not full autonomous supervisor reasoning:** the Chief of Staff can generate one bounded, tool-free Claude Managed Agents plan draft through the dedicated `plan.generate` capability. The OS persists the request as an execution, validates bounded JSON, and holds the proposal for explicit founder review and assignment before materializing any plan or delegations. This does not yet provide recursive supervisor decomposition, per-agent machine identities, an MCP tool gateway, dynamic replanning, or live client-data execution. The reconciled integration was merged in PR #11 (merge commit `9674c40f08228b032ae79f8e9df590609d8463df`). Its exact tested head `2fef1b62967ea17495e580ed6abfc5cce36362fb` passed PostgreSQL 16 migration validation, Python compilation, backend/PostgreSQL integration tests, frontend TypeScript checking and Next.js production build (run [45489030391](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/45489030391)); no live Claude session was used.
- Capability records deliberately default disabled. Tool grants cannot be enabled until the OS MCP gateway and narrowly scoped tool authorization are implemented.
- Group heads, department heads and specialist Agent definitions are local OS profiles. They are not automatically provisioned as separate Anthropic provider Agents.
- Founder and Executive Office workforce records are chart entries; they are not live human identity accounts.

## Known gaps / not validated
- No production outbox handlers are registered; the website lead event is persisted but does not trigger notifications or automation. External side effects remain disabled.
- Outbox handler heartbeat and actual worker crash/restart recovery need further validation.
- AI-driven Chief of Staff planning, autonomous recursive decomposition, delegated machine identities, and dynamic replanning/escalation are not implemented. The orchestration plan API and worker queue are execution foundations; the Founder Console now exposes plan creation, dependency monitoring, founder review and blocked-work recovery. The production build now passes, but live provider sessions and runtime behavior remain unverified.
- Managed Agents live provisioning, provider API compatibility against the actual account, Environment sandbox/egress configuration, webhook/reconciliation for ambiguous session creation and production runtime eligibility are not verified.
- The pre-created Managed Agent owns its tools/MCP/skills. The adapter now queries the provider Agent and rejects non-empty tools/MCP/skills or enabled multiagent configuration; actual account configuration and environment sandbox/egress still require live verification.
- Claude Agent SDK adapter is not implemented.
- Agency OS MCP server and narrowly scoped OS tools are not implemented; this is the prerequisite for enabling real agent capabilities and OS-mediated side effects.
- Full OIDC/JWKS/MFA, secure frontend session lifecycle and scoped machine identities are not implemented.
- Complete cross-workspace isolation across APIs/workers/files/sessions/caches and PostgreSQL RLS are not validated.
- Complete Data Protection Gateway, PII redaction and retention/deletion lifecycle are not implemented.
- Revenue operations remain partial: CRM clients/contacts/leads/opportunities, contact activity history, lead suppression, proposal drafts and founder pricing approval are implemented. Prospect research/enrichment, evidence/provenance capture at scale, deduplication/merge review, governed outreach drafting/dispatch, sender identity, reply/opt-out/bounce event handling, campaign operations and revenue attribution remain incomplete. No external message dispatch is enabled.
- Proposal drafts and founder pricing approval, service catalogue, contract register, contract-backed onboarding, invoice approval/issue evidence and payment receipt reconciliation are implemented as internal records. Remaining gaps include proposal revision/versioning and client delivery, legal template review/e-signature provider, invoice document generation/sending, payment-provider reconciliation/webhooks, refunds/credit notes, tax/accounting integrations and statutory accounting. Existing records are not a full finance ledger or statutory accounting system.
- Marketing content/ad generation and campaign analytics are not yet connected to governed publishing/advertising integrations. Draft generation must be separated from paid spend or publication approval.
- Client success, support case management, service-level tracking, renewal/expansion workflows and structured delivery handover remain incomplete. Contract-backed onboarding and delivery activation foundations exist.
- Live telephony, signed webhooks, STT/TTS and recording lifecycle are not implemented.
- Complete QA acceptance/rework metrics and production release gates are incomplete.
- Frontend TypeScript checking and production build pass in main CI. Production monitoring/alerting, SBOM generation, backup restore drill and independent security review are not validated.
- Website-to-OS endpoint is implemented and backend-tested on OS main. Website forwarding/admin retry merged to website main via PR #30 (merge commit `89bbed3484b11b78db2b0ca3d98744cb409a8c48`); website BYOK/studio restoration merged via PR #33 (merge commit `9e2507aec579188ea34e17b51d2b9409d9ed7349`). The PR quality workflow passed lint, typecheck, dependency audit, structure, build, Playwright and Lighthouse. The post-merge website main workflow was pending at last check. Neither side is externally configured or deployed; the bridge remains disabled until migrations, matching server-only secrets, fixed org/workspace mapping, HTTPS and synthetic end-to-end idempotency/recovery checks are complete.

## Additional feature discovery
- `docs/FEATURE_DISCOVERY_AND_ADOPTION.md` records reviewed patterns from LangGraph, Temporal, Langfuse, Arize Phoenix, ToolHive, Semgrep, OpenHands, Prefect and Sentry. These are research references, not installed integrations.
- The selected immediate work was execution visibility using existing OS-owned records; no new workflow runtime or external provider was added.

## Reference integration decisions
- ECC: selected research-first engineering, skill governance and independent review patterns; no wholesale harness import.
- Strix: optional isolated, authorization-gated QA/Security runner; not installed or executed.
- Claude Skills Hub: discovery index only; imported skills require provenance, license, static review, sandbox test and pinning.
- Agent Skills: eighteen curated adaptations are available through the authenticated read-only skills API; all remain disabled with no tool grants. Provider-side skill injection and per-agent assignment are not implemented.
- CodeRabbit: optional PR review signal after privacy, retention, subprocessor, pricing and GitHub permission review; not connected and never a replacement for CI/QA/founder approval.

## Safety boundary
Use synthetic/mock data until authentication, tenant isolation, runtime eligibility, retention, provider authorization and recovery controls are validated. Do not enable real outreach, dialing, client transcript ingestion or production side effects based only on API routes or outbox rows. Managed Agents is beta and not ZDR/HIPAA eligible; do not send confidential/regulated data without an eligible, reviewed alternative and appropriate contractual controls.

The standalone Command Center and Evaluation Harness source snapshots have been removed after migrating the active deterministic evaluation packs into `app/evaluation/`. Native workforce, execution, worker and evaluation modules remain OS-owned. The repository is a substantial development foundation, not a production-ready or fully autonomous agency OS.


## Revenue and client lifecycle clarification (2026-11-25)
The agreed agency workflow starts before an inbound website enquiry. The Revenue Engine must support founder-governed market research, prospect sourcing/enrichment, outreach drafting and authorized dispatch, reply/opt-out/bounce stop conditions, CRM relationship history, campaign/content/ad production, proposal and commercial approvals, invoicing/payment tracking and revenue analytics. The Delivery Engine begins after an approved opportunity and onboarding. These are required operating capabilities, not optional SaaS features. Current source implementation is partial as detailed above; the presence of a department charter, skill or plan-draft capability does not mean the corresponding operational integration is live.

## Recent integration and Supabase hardening
- PR #11 merged to main as `9674c40f08228b032ae79f8e9df590609d8463df`; exact PR head CI passed backend/PostgreSQL migration tests, Python compilation, frontend TypeScript checking and Next.js production build.
- PR #10 was closed as superseded by PR #11.
- Website Supabase project `AI-Agency-Service` has the lead-sync migration applied. A further migration `20261124212429_restrict_admin_helper_execution` was applied and committed to website source as `supabase/migrations/202611250002_restrict_admin_helper_execution.sql`. It moves admin policy checks to trusted JWT app_metadata expressions and revokes direct anon/authenticated EXECUTE on the SECURITY DEFINER helper. Post-change advisor no longer reports the exposed helper; remaining findings are leaked-password protection disabled and an informational RLS/no-policy notice on the service-only rate-limit table.


## Revenue and delivery implementation reconciliation (2026-11-25)
The internal workflow now present in source is: contact → lead qualification/suppression → opportunity → proposal draft → founder pricing approval → contract draft/approval → recorded signed evidence → onboarding checklist → founder-approved delivery activation → project-linked invoice draft → founder invoice approval/issue evidence → append-only payment receipt reconciliation. These are internal records and approval workflows only; they do not send proposals/contracts/invoices, collect money, contact prospects, place calls, or activate external integrations.

Merged work includes PR #17 (contact timeline), PR #19 (leads/opportunities), PR #20 (proposal approval lifecycle) and PR #21 (service catalogue). Main CI passed after PR #21 merge on commit `7801ab0b42788fb06077e5937038dd0a79dce286` (backend and frontend checks). PR #26 adds immutable catalogue snapshots to proposals but remains open and unvalidated; its GitHub Actions jobs failed before exposing step/log details and must be diagnosed and pass before merge.

## AI-native revenue and engagement framework (PR #28 — pending validation)
- Proposal drafts now distinguish one-time projects from retainers. Retainer terms include billing frequency, initial term, included hours per period, optional rollover, support response target and proposed auto-renewal. Proposal terms are snapshotted into contracts; contract total commitment is calculated from recurring fee multiplied by complete billing periods and guarded against the supported integer range.
- One-time engagements remain fixed-value contracts. Retainers support monthly, quarterly or annual cadence; term length must align to complete billing periods. Auto-renewal is recorded as a proposed term only and never executed automatically.
- Lead research records persist evidence summaries, fit/confidence scores, buying signals, risks, HTTPS source references and research timestamps. Records are workspace-scoped and append-only through the API.
- Outreach drafts persist channel, content, personalization basis and linked research references. Founder review can mark a draft approved/rejected; approved_draft is explicitly not a send authorization. There is no send, schedule or dispatch endpoint in this feature.
- Research and outreach lifecycle changes emit versioned transactional outbox events so future agent workers can react without provider systems owning business state.
- Autonomy vocabulary now includes internal lead research/qualification, outreach drafting/personalization, account-health assessment, retainer-usage analysis, QA preparation and project status summaries. Outreach sending, outbound calls and retainer auto-renewal remain fail-closed to manual review.
- Claude remains the intended reasoning/runtime provider behind the adapter. This PR does not yet provide a production MCP tool gateway, live web-research connector, email/LinkedIn sender, telephony integration or autonomous scheduling. Those require the OS authorization gateway, data policy, consent/suppression, rate/stop checks, budgets, provider configuration and end-to-end tests.
- Retainer period ledger, actual usage aggregation against time entries, SLA measurement, overage approvals, recurring invoice schedule, renewal/termination workflow and client health scoring remain planned follow-on work.
- PR #28 is open. GitHub Actions repeatedly terminates backend/frontend jobs as failed within seconds and exposes no step summaries or downloadable job logs through the connected GitHub API. Do not merge or claim validation until this runner/CI issue is diagnosed and both jobs pass.


## Retainer service-period ledger and current release readiness (PR #28 — unmerged)
- Added a workspace-scoped `RetainerServicePeriod` ledger with contract/project linkage, period number, UTC boundaries, included allowance, rollover allowance, usage snapshot, overage snapshot and founder closeout evidence.
- Period creation requires Founder Authority, an executed retainer contract, an active onboarding/project link, a valid contracted period number and sequential period closure. Periods after the first must be contiguous with the preceding closed period.
- Closing a period is founder-only and idempotent. It snapshots billable time entries for that project and period, calculates overage minutes and emits audit plus transactional outbox events. Overage is recorded only; it is not approved for charging or invoiced automatically.
- Billable time entries for an active retainer project require a matching open service period. The API rejects backdated billable entries against a closed period. Non-billable internal time is not treated as retainer consumption.
- Added Retainer Operations Founder Console page for viewing periods, creating the next period and founder closeout.
- Added tests for usage aggregation, overage calculation, rollover and rejection of late billable entries. These tests are authored but have not yet been executed in CI; PostgreSQL concurrency/locking tests remain required.
- Hardened Revenue endpoints: collection routes now explicitly accept the organization path parameter; lead/contact/client linkage is checked; opportunities cannot be created from suppressed/unqualified leads; research timestamps and source access timestamps must be timezone-aware and not future-dated; outreach list status filters are allowlisted.
- PR #28 remains open and unmerged. Do not interpret source commits as test evidence. GitHub Actions usage is near its limit; avoid repeated reruns and reserve the next run for consolidated validation.
- Current progress estimate is tracked in `docs/PRODUCTION_READINESS_CHECKLIST.md`: approximately 52% internal implementation, 49% including external integrations, 20% production verification. These are weighted estimates, not release-readiness claims.

- Added a unique optional retainer-period reference to invoice records. A closed period can now produce one idempotent recurring invoice draft for its contracted per-period fee; the draft links to the period and contract, reserves remaining contract commitment and includes an explicit note when usage overage exists. Overage is excluded from the invoice amount and requires separate approval. The existing invoice approval/issue-evidence lifecycle remains the only route toward issue; no invoice is sent.
- Added Retainer Console invoice-draft creation and status visibility. The user must choose a due date; no schedule runner or autonomous invoice issuance is enabled.


## External operating-model audit — 2026-11-25
- Reviewed FounderOS and AI-Native OS at pinned public revisions; adopted only relevant operating patterns, not standalone runtimes or unreviewed executable assets.
- Added four independently authored Agency OS skills and a governed operating-loop design document in the integration PR. They remain disabled, tool-free and public/synthetic-only.
- Candidate loops are documented, not scheduled or autonomous. No new provider tools, MCP grants, data classes or external side effects were enabled.
- Remaining prerequisites: PR #30 security verification, complete tenant/DPG coverage, machine identities, session lifecycle, OS Tool Gateway, skill assignment authorization, durable loop runtime, independent gates and recovery tests.


## Consolidation sprint update — 2026-11-25
- PR #31 merged to main as `f8fc318cfece0dafb64a846d93fe7d78e64c5593`. It adds the governed operating model and four curated reference skills. They remain disabled, tool-free and restricted to public/synthetic data; the candidate loops are not active or scheduled.
- PR #30 remains open. Its DPG boundary has been hardened for sanitized string-only metadata keys, post-redaction key collisions, finite numeric values and total serialized metadata size. Adversarial tests were added but not executed.
- PR #30 PostgreSQL tenant-integrity migration and cross-tenant tests remain unverified. Do not apply the migration to a populated environment until isolated PostgreSQL 16 upgrade/downgrade and mismatch-preflight tests have been completed.
- Next implementation priorities are complete tenant isolation, machine identities/session lifecycle, OS Tool Gateway, DPG coverage for files/RAG/tools, durable governed loops, and external integration/recovery evidence.
- CI is supplementary; independent test execution is the intended validation path. No new test pass, deployment or production-readiness claim is made by this documentation update.


## Current PR consolidation — 2026-11-25
- PR #31 is merged to main (`f8fc318cfece0dafb64a846d93fe7d78e64c5593`): operating-loop design and four curated skills are present, but disabled and without tool grants.
- PR #30 is closed as superseded, not merged. Its security changes were ported onto current main in PR #33 (`feature/tenant-dpg-hardening-rebased`), which is 10 commits ahead and 0 behind main at the latest comparison.
- PR #33 contains tenant integrity constraints/migration, DPG input/output protection, metadata bounds and adversarial tests. It remains open and unverified; do not merge or apply its migration to populated data until isolated PostgreSQL 16 verification and focused/full backend tests are completed.
- Evidence-backed progress percentages remain unchanged at 52% internal implementation, 49% overall, 20% production verification and 5% external configuration. Unmerged code and unexecuted tests are not counted as completed.


## DPG follow-up — 2026-11-25
- The execution input boundary now bounds the complete serialized request before regex processing, in addition to the metadata-specific bound.
- Opaque org/workspace/task/agent IDs and provider run identifiers are checked for secrets/PII; identifiers are rejected rather than redacted to preserve correlation integrity.
- The runtime's external-run-ID persistence callback is wrapped by the DPG, closing a path where a provider could otherwise persist an unfiltered identifier before returning its result.
- Provider name and external run ID are checked before result persistence; detail text continues to receive PII redaction and secret blocking.
- Regression tests cover oversized prompts, invalid metadata shape, callback sanitization, sensitive provider identifiers, and worker-level fail-closed audit behavior. In an isolated validation copy, 81 DPG/worker tests passed.
- Independent testing is not dependent on GitHub Actions. SQLite migration upgrade/downgrade/re-upgrade, preflight-abort and all 16 cross-scope rejection cases passed in an isolated validation copy; PostgreSQL 16 verification and the full backend suite on the exact main head remain pending.


## PR #33 independent validation update — 2026-11-25
- PR #33 now includes CRM and outreach tenant composite constraints, preflight checks, DPG request/result/callback protection, a reusable decoded-payload boundary, and worker-level audit/fail-closed tests.
- Isolated local validation copy: 81 DPG + worker-service tests passed; 5 API, 11 action-policy, 5 approval, 12 execution-service and 3 outreach API tests passed; Python compile check passed.
- SQLite migration rehearsal from `l2e8a0b6d549` successfully upgraded, downgraded and re-upgraded to `m3f9c2a7e514`.
- A cross-tenant contact/client mismatch caused preflight to abort while Alembic remained on the parent revision. All 16 deliberate cross-scope insert attempts were rejected by the migrated SQLite schema.
- PostgreSQL 16 verification and full backend-suite execution on the exact remote PR head remain pending. The current local evidence does not replace those checks.
- PR #33 was merged to main as `09d23d90b258c55331367f94096bc6906cdce249`. The migration must not be applied to populated production data until PostgreSQL 16 verification passes; no deployment or production-readiness claim is made.


## Latest authoritative development update — 2026-11-25

- PR #33 is merged to main as `09d23d90b258c55331367f94096bc6906cdce249`; any earlier notes in this document describing PR #33 as open or pending are superseded.
- PR #34 candidate `feature/machine-identity-session-gateway` adds founder-governed machine identity issuance/revocation, one-time high-entropy credentials with digest-only persistence, workspace-bound sessions, expiry limits and a fail-closed tool/session authorization primitive.
- Credentials are scoped to one organization/workspace and explicit subject. Agent identities require the referenced agent to be enabled in the same workspace. Only synthetic/public data grants are enabled in this increment.
- Revocation and session creation/tool authorization serialize on the identity row; revocation cancels active sessions in the same transaction.
- The new authorization primitive is not a tool execution gateway. No tool adapters, provider-side MCP tools, external dispatch or autonomous side effects are enabled by this increment.
- Independent candidate validation: 12 machine-identity tests, 5 API tests, 20 workforce tests, 5 approval tests, 11 action-policy tests, 12 execution-service tests and 3 outreach API tests passed in separate pytest invocations (66 total). SQLite migration rehearsal from parent revision `m3f9c2a7e514` upgraded, downgraded and re-upgraded to `n4a7c2e91b60`. The candidate was syntax-compiled. These results are from an isolated reconciled candidate, not the exact remote PR head.
- PostgreSQL 16 verification, full exact-head backend suite, actual Tool Registry/invocation execution, scheduled session cleanup, and production secret-manager setup remain incomplete.
- Do not issue production credentials, enable tool grants, or claim production readiness until the gateway, isolation, PostgreSQL and operational lifecycle gates are verified.


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


## Managed Agents custom tool bridge — 2026-11-25 (PR #38 candidate)

- [x] Extracted a shared in-process `invoke_registered_tool` service used by HTTP and provider custom-tool callbacks.
- [x] Added exact provider-safe custom tool names and JSON schemas generated from the OS Tool Registry.
- [x] Managed Agents validates provider Agent tools against the OS registry on create and resume; unknown tools, schema drift, built-in toolsets, MCP servers, skills and multiagent features are rejected.
- [x] Handles `agent.custom_tool_use` events while sessions are running/idle and sends `user.custom_tool_result` events only after the OS service completes.
- [x] Waits for the provider session to resume after custom-tool results; built-in permission-gated actions are not auto-confirmed.
- [x] Worker lazily creates/reuses an agent machine session, persists it on `Execution.machine_session_id`, and calls the OS gateway with exact agent/org/workspace scope.
- [x] Provider event IDs map to deterministic idempotency keys; tool results are committed before being returned to the provider.
- [x] Centralized session creation audit covers worker and HTTP creation paths; tool denials persist safe reason-code audit events after rollback.
- [x] DPG now preserves only explicitly trusted OS-generated identifier fields in tool output; arbitrary/untrusted payload strings remain PII-scanned.
- [x] Migration `q7f2b9d4c631` adds the composite scoped execution-to-session link and one-session-per-execution uniqueness.
- [x] Independent isolated-candidate validation: **236 focused tests passed** across 16 modules, Python compile check passed, and SQLite migration upgrade/downgrade/re-upgrade through `q7f2b9d4c631` passed.
- [ ] PostgreSQL 16 verification and full backend suite on exact PR #38 head remain pending. A previous full-suite attempt in the isolated candidate timed out; no full-suite pass is claimed.
- [ ] Provider Agent external configuration, machine identity issuance for each agent, real API credential setup and synthetic live end-to-end test remain external/release steps.
- [ ] Built-in web search/fetch, MCP, skills, multiagent, budgets and tools with approvals remain disabled. The research capture tool stores supplied references; it does not independently browse or verify them.
- [ ] Session retention/deletion and physical cleanup remain outstanding; the new restrictive FK requires safe detachment/reconciliation before deletion.
