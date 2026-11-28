# Agency OS — authoritative implementation status

**Last reconciled:** 2026-11-28 16:40 UTC  
**Working branch:** `main` is the single active integration branch for founder-authorized work. Do not create parallel feature branches or PRs unless explicitly requested.  
**Verified code baseline:** PR #71 was merged into `main` at 2026-11-28 16:28:33 UTC; merged code commit `f07a8b7b8a864cbc08da35bf4b4c422cd4baf25e`. PRs #68, #69 and #70, plus the learning/Cowork/Code integration work in PR #71, are included.  
**Code-baseline CI:** [Run 46165349483](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/46165349483) completed successfully. Backend and frontend jobs passed, including PostgreSQL role bootstrap/migrations/integration tests, Python compilation, hardened runtime image checks, frontend typecheck and production build. Subsequent changes to `IMPLEMENTATION_STATUS.md` and `CLAUDE.md` are documentation-only; follow-up CI is triggered by those commits. No new test count is inferred from job status alone.  
**Release posture:** **NO-GO for production.** Green CI does not establish live provider compatibility, staging isolation, backup restore, operational readiness or compliance.

This file describes the merged `main` baseline. Historical PR/branch checkpoints remain historical evidence, not active integration work. See `docs/CONSOLIDATION_EXECUTION_LEDGER.md` and `docs/PRODUCTION_GRADE_MASTER_CHECKLIST.md` for historical integration and release gates.

## Verification evidence on merged `main`

| Check | Recorded result | Qualification |
|---|---|---|
| Backend pytest + PostgreSQL 16 integration | Passed | Main CI run [46165349483](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/46165349483); backend job completed successfully, including isolated PostgreSQL 16 integration. |
| Human tenant/workspace RLS | Passed in live PostgreSQL 16 CI | Dedicated `agency_os_test_app` NOBYPASSRLS login; cross-org/workspace access, grants/revocation and pooled-context behavior executed. |
| Worker capability boundary | Passed in live PostgreSQL 16 CI | Actual `agency_os_worker` NOBYPASSRLS login; capability, forged-GUC, direct-table/function privilege and scope checks executed. |
| Browser-session retention, orchestration-link RLS, outcome isolation and audit immutability | Passed in live PostgreSQL 16 CI | Previously skipped suites now execute; append-only evidence is preserved by fixtures. |
| PostgreSQL role bootstrap and migration upgrade | Passed | PostgreSQL 16 role setup, Alembic graph validation, full upgrade to head and Python compilation passed. Disposable CI database only. |
| Frontend TypeScript and Next.js production build | Passed | Main CI run above; no frontend lint result is claimed by this workflow. |
| Main push CI | Passed | [Run 46165349483](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/46165349483) completed successfully after PR #71 was merged. |
| Live Claude/Anthropic provider compatibility | Not verified | No live provider provisioning, credentials or production provider execution claimed. |
| Production migration, deployment, restore drill or compliance assessment | Not performed | Requires separate staging/production controls and explicit founder go/no-go. |

No production database migration, production deployment, external provider activation, client-data operation or compliance assessment is claimed.

## Mission and architecture

Agency OS is the founder-controlled internal operating system for an AI Solutions Agency, not a SaaS product. Its two operating engines are:

- **Revenue:** research, leads, CRM, pipeline, proposals, approved outreach and marketing operations.
- **Delivery:** discovery, solution design, engineering, QA/security, deployment, projects, support and measurable client outcomes.

The agency philosophy is **Results as a Service (RAAS)**: the client result is the product; AI is the means. RAAS does not automatically imply contingent/performance pricing. Outcome measurement, attribution, commercial model and risk allocation must be agreed explicitly.

Architecture remains a modular monolith: Next.js/React Founder Console, Python FastAPI backend, PostgreSQL source of truth, Redis for rate limiting, and independent Python workers. No business-record cache, object-storage artifact path or RAG ingestion path is currently implemented. PostgreSQL owns business state, permissions, approvals, executions, sessions, artifacts and audit. Providers and automation tools are adapters, not sources of truth. No second queue/orchestration engine is required at this stage.

## Implemented foundations

### Core data, identity and founder governance
- Organization/workspace-scoped clients, contacts, leads, opportunities, projects and milestones.
- Explicit Founder Authority distinct from organization-owner membership.
- Founder-only provisioning and decisions; single-use approval consumption matches action/resource/workspace and rechecks active Founder Authority.
- Protected commercial operations consume approval and mutate protected OS state in the same transaction, with audit.
- Central autonomy policy: explicitly allowlisted internal actions, founder-approval actions and manual-review default for unknown actions.
- Authentik OIDC authorization-code + PKCE foundations, pre-provisioned subject linking, HttpOnly session cookies, CSRF checks, persistent browser-session revocation/rotation and expiry. Live Authentik/JWKS/MFA assurance remains unverified.

### Tenant isolation, workers and execution reliability
- PostgreSQL RLS and role separation are implemented; application and worker roles are intended to be non-owner, least-privilege roles.
- Human workspace-grant authorization was restored in PR #58.
- The orchestration plan-to-delegation join table now carries organization/workspace scope, composite foreign keys to both parent records, and forced PostgreSQL RLS; the table is included in the startup RLS inventory. The migration backfills scope from the plan and refuses to proceed if existing links cross workspaces or are orphaned.
- A model/RLS inventory regression test requires every mapped table to be present in the RLS inventory, with the shared global `users` identity table as the explicit exception. The `users` table still needs a separate privacy/access review.
- Worker production startup verifies `PROCESS_ROLE=worker`, PostgreSQL and the `agency_os_worker` role with `NOBYPASSRLS`.
- Worker execution and maintenance use database-verified, capability-bound claim/renew/release operations; caller-forgeable machine GUCs do not establish worker authorization.
- Durable execution lifecycle includes persisted attempts, leases, heartbeats, bounded retries, expired-lease recovery, pause/cancel acknowledgement and workspace-scoped maintenance.
- PostgreSQL outbox foundation supports allowlisted handlers, SKIP LOCKED claims, leases, bounded attempts, acknowledgement, sanitized errors, retry, dead letter and reconciliation.
- Workspace-scoped execution history and execution trace APIs; Founder Console Processes and Monitoring views.

### Audit, privacy and retention
- Audit payloads reject invalid/oversized structures, detect known credential-bearing fields fail-closed and redact supported free-text/structured PII. The consolidated candidate removes the generic audit exemption for `resume_token`; resume identifiers remain validated only in the narrowly scoped execution-control boundary. Audit-token, worker-function privilege and Managed Agents ambiguous-create regressions passed in CI run `46133997208`.
- PostgreSQL audit events reject UPDATE/DELETE by application and worker roles. This is append-only protection, **not cryptographic tamper-evidence**; hash chaining or externally anchored integrity checkpoints are not implemented.
- Browser sessions store a digest of the JWT identifier, support server-side revocation and rotation, and are pruned in bounded batches.
- Agent sessions are constrained by machine identity data-class grants and cannot outlive the identity.
- Bounded retention scrubs terminal agent-session descriptive metadata after the configured 90-day default and tool invocation payloads after the configured 180-day default. Purged idempotency results return an explicit expired-result response rather than re-executing.
- Retention/deletion is incomplete for object artifacts, uploaded files, logs/traces, backups and provider-side data. Workspace erasure and machine-identity deletion require separate approved workflows.

### AI workforce and Claude runtime
- Workforce model includes offices, functional groups, departments, teams, human/agent/supervisor/sub-agent members, 121 position records, capability grants and delegation lineage.
- Founder-only bootstrap provisions the organizational catalogue; profiles remain inactive until explicit founder-authorized capability enablement and activation.
- Delegation enforces direct-manager hierarchy, active members, enabled definitions/grants and founder exclusion.
- Curated catalog of 18 reviewed, source-pinned skills with provenance and file digests. Skills are disabled, tool-free and public/synthetic-only; per-agent assignment and provider-side skill loading are not implemented.
- Chief of Staff plan draft is bounded, tool-free and requires founder review before task materialization. Worker maintenance releases dependent tasks after prerequisites succeed and synchronizes task/delegation state.
- Managed Agents adapter is opt-in and synthetic-first; it inspects provider Agent configuration, rejects unapproved built-in tools/MCP/skills/multiagent features, persists/resumes sessions, tracks workflow runs and routes non-completion to manual review. The adapter contains an OS-mediated custom-tool callback path, but live Anthropic account/API compatibility and provider execution have not been verified. The separate Vault-backed provider-MCP compatibility path is disabled and must not be enabled alongside the callback path. Cowork and Claude Code use the separate generic Agency MCP gateway. Automatic provider-session reconciliation remains unimplemented.
- Managed Agents is beta. Live account provisioning, API compatibility, environment sandbox/egress, ambiguous-create reconciliation and production eligibility are unverified. It is not eligible for ZDR or HIPAA BAA.
- Claude Agent SDK adapter is not implemented. Recursive supervisor reasoning, dynamic replanning, delegated per-agent machine identities and live client-data execution are not implemented.

### Tool Gateway
- OS-owned machine identities use one-time displayed credentials stored as digests, bounded expiry, revocation and workspace/data-class scopes.
- Agent sessions are persisted and bounded. Every Tool Gateway entry point now derives its tool allowlist from OS-issued machine scopes and enforces a 100-successful-call session ceiling; adapter-provided allowlists/limits can only narrow that policy. Tool calls also pass machine/session checks, data-class policy, input/output protection, typed schema validation, workforce capability checks, idempotency, durable invocation records and audit.
- Code-owned registry currently includes read-only health and public lead-research draft capture. Research capture validates bounded public HTTPS source references and stores a founder-review draft; it does not create a CRM contact/lead or send outreach.
- The generic Streamable HTTP Agency MCP gateway for Claude Code and eligible Cowork clients is implemented and disabled by default. It uses founder-provisioned workspace-scoped service identities, short-lived session credentials, digest-only token storage, session revalidation and the existing Tool Gateway; it has no independent tool registry or direct business-table access. The Managed Agents custom-tool callback is a separate worker-mediated path. The Vault-backed provider-MCP compatibility transport is disabled and is not the Code/Cowork gateway. Live Code/Cowork connector and Anthropic provider smoke tests remain pending. Per-execution sandbox isolation, runtime egress enforcement and resource quotas are not implemented or verified. The workforce capability model stores `budget_minor`, but no cumulative execution reservation/settlement enforces it.

### Revenue, Delivery and RAAS
- CRM includes client/contact/lead/opportunity records, append-only contact activity timeline, source/qualification notes and suppression reasons.
- Founder Console includes Contacts, Leads, Opportunities and Proposals workflows. Proposal drafts are linked to opportunities and pricing approval is founder-gated.
- Service catalogue is founder-governed and versioned. Contract register requires approved proposal and signed evidence before executed status. Onboarding requires executed contract, evidence-backed checklist and founder approval before project activation.
- Invoice register prevents overbilling, requires founder approval before issue evidence and maintains an append-only payment receipt ledger. No payment collection is integrated; this is not statutory accounting.
- Delivery foundations include playbooks, founder-approved scope changes, time/cost records, provisional project financial summaries, exception inbox and project outcomes.
- Project outcomes record problem, desired outcome, metric/unit, baseline, target, direction, date, measurement method and agreed acceptance criteria. Outcome measurements are append-only and source-backed as submitted metadata. Founder-only delivery acceptance is distinct from measured business impact.
- Founder Console includes Client Outcomes page.

## Current gaps and blockers

### P0 — security and data protection
- Complete a route/function/role/grant/ownership inventory for RLS, SECURITY DEFINER functions and pooled-connection context; mapped ORM tables are now checked against the required RLS inventory, but global `users` identity-table access still needs separate review.
- Complete negative cross-workspace tests for every API and nested object; organization membership must not substitute for exact workspace grant.
- Prove isolation across current browser/agent sessions, tool outputs and logs, then across files, object storage, caches, search/RAG and generated artifacts when those paths are implemented. No file upload/extraction, object storage, RAG ingestion or business-data cache path currently exists; the signed website lead intake is a fixed-workspace CRM ingestion and does not call an AI provider.
- Complete Data Protection Gateway classification/minimization/PII-secret detection/redaction for every ingestion, file extraction, RAG, connector, provider callback, tool, log, cache and artifact path. Current implemented provider-facing boundaries cover Managed Agents requests/results/callbacks, Tool Gateway input/output, audit payloads and structured logs. The consolidated security work adds structured credential-key rejection, structured PII-field redaction and provider event-ID protection; the current consolidated MCP/credential regression suite passed in CI run `46139048580` (**602 backend tests**). No file upload/extraction, object storage, RAG ingestion or general connector ingestion path is currently implemented. There is no automated content classifier; current runtime eligibility is a conservative data-class/authorization gate.
- Enforce per-client policy and runtime eligibility before any provider receives data.
- Complete scoped credential rotation, egress allowlists/SSRF defenses, sandbox isolation, resource limits, malware-safe file processing and secrets-history review.
- Add cryptographic audit integrity checkpoints; current append-only trigger alone is not cryptographic tamper-evidence.
- Complete retention/deletion for business records, sessions, artifacts, logs, backups and provider-side data with approved, recoverable workflows.
- Complete independent security assessment. No compliance claim is authorized.

### P1 — runtime, Revenue and Delivery
- Add the bounded `delete_pending` provider-credential cleanup/reconciliation worker, then run the staging Anthropic Vault/Environment/session/MCP smoke test with synthetic data. Keep write tools and approval-bearing tools disabled until atomic OS approval integration and negative tests pass.
- Add delegated machine identities, per-agent budget reservation/settlement and tool-level enforcement (the current `budget_minor` field is configuration metadata only), versioned agent runtime configuration, controlled promotion and rollback.
- Verify worker crash/restart, concurrent claims, lease expiry, retry/DLQ, cancellation races, duplicate outbox delivery and provider timeout reconciliation under multi-worker execution.
- Register only approved, idempotent outbox handlers; no production external handlers are currently enabled.
- Implement prospect research/enrichment with source provenance, dedupe/merge review, attribution and confidence.
- Implement approved outreach dispatch only after sender authorization, consent/suppression, rate limits, idempotency, delivery receipts and immediate reply/opt-out/bounce stop handling. No external message dispatch is enabled.
- Complete proposal revision/versioning and client delivery, contract/e-sign integration, invoice document delivery, payment provider reconciliation, refunds/credit notes and tax/accounting integrations as applicable.
- Complete Delivery requirement-to-test traceability, independent QA/rework metrics, production release gates, handover, support cases, SLA and renewal workflows.
- Add automatic KPI ingestion, verified impact evidence, outcome revision/scope-change workflow and client acceptance/sign-off.
- Add trusted Evaluation Harness runner attestation, immutable test/commit/environment manifests and non-bypassable release-blocking gates. Caller-supplied booleans are not trusted evidence.
- Complete provider routing/resilience, per-execution usage/cost accounting, budgets, margin/forecast and founder emergency disable controls.

### P2/P3 — Founder Console and operations
- Dashboard `System` / `Light` / `Dark` theme support is merged in PR #65 and its frontend lint/typecheck/build/browser checks passed. Browser-based end-to-end critical-flow and accessibility tests remain.
- Unified founder work queue across approvals, escalations, blocked tasks, failures, client risks and budget exceptions; drill-down to source record, execution, evidence and audit.
- Metrics/logs/traces, alert routing, dashboards, cost visibility, dependency/container/SAST/secret/license scans and SBOM.
- Encrypted PostgreSQL and object-artifact backups; isolated restore drill; measured RPO/RTO and recovery runbooks.
- Separate dev/staging/production configuration and credentials; staging synthetic acceptance; controlled migration/release/rollback.
- External deployment inspection on 2026-11-28: the connected Render workspace has no Agency OS API service, Render-managed PostgreSQL instance or Render Key Value instance. The Cloudflare `studio` Worker has no Agency OS API URL/service binding in its runtime settings. The live Code/Cowork MCP smoke test therefore remains blocked until a controlled staging API ingress and its database/cache/secrets are provisioned and verified. A suspended n8n service exists in Render, but the current native Python worker + PostgreSQL outbox design does not require reactivating it.
- Configure and verify Authentik, Claude, research sources, email/webhooks, object storage and website intake only with synthetic data and explicit authorization.
- Website signed lead bridge is implemented in both repositories but remains disabled until matching server-only secrets, fixed org/workspace mapping, HTTPS, external configuration and synthetic idempotency/recovery tests are complete.

## Immediate work order

1. Consolidated baseline: **PR #71 is merged**; `main` at `f07a8b7b8a864cbc08da35bf4b4c422cd4baf25e` has successful CI run `46165349483`.
2. Continue tenant/RLS and Data Protection Gateway inventory and route-by-route negative tests. Live PostgreSQL 16 human/worker isolation suites now execute in CI; broader API/object/artifact coverage remains open.
3. Artifact/object storage isolation and retention lifecycle.
4. Phase 4 runtime hardening: prove the active Managed Agents custom-tool lifecycle and Code/Cowork Agency MCP path with synthetic data; only implement Vault cleanup if the disabled Vault compatibility transport remains selected. Add worker/provider recovery drills.
5. Worker/outbox recovery and reconciliation acceptance.
6. Revenue provenance, dedupe and governed outreach.
7. Delivery QA, handover, support and RAAS evidence.
8. Founder Console work queue and operational drill-down.
9. Monitoring, SBOM, backup/restore, RPO/RTO and runbooks.
10. Staging synthetic acceptance, independent security review and explicit founder production go/no-go.

## Founder-environment checks to run last

After code changes stabilize, run from the local checkout on exact `main`:

```bash
git fetch origin
git switch main
git pull --ff-only origin main

cd frontend
npm ci
npm run lint
npx tsc --noEmit
npm run build
cd ..

# Focused security regressions on merged main
python -m pytest -q tests/test_data_protection.py tests/test_log_sanitization.py tests/test_audit_payload_protection.py tests/test_tool_gateway_policy.py tests/test_machine_identity.py tests/test_rls_migration.py

# Full backend suite
python -m pytest -q

# Isolated PostgreSQL 16 suite
docker compose -p agency-os-pg-test \
  -f docker-compose.postgres-test.yml \
  up --build --abort-on-container-exit \
  --exit-code-from postgres-tests postgres-tests
```

Then run browser critical-flow/accessibility tests and verify the exact `main` commit. PR #71 is merged; production release remains a separate decision. Live provider credentials, DNS, object storage, email/webhooks, staging deployment and backup restore require founder-environment access and will be presented as a final checklist. Production migration/deployment and destructive data actions require separate explicit approval.


## Historical founder verification update — 2026-11-27 (pre-consolidation)

- On pre-fix PR head `88697b83bae5f1728cffab7c3c44707e368cd114`, the full host suite reported **538 passed, 3 failed, 20 skipped**. Two failures were resume audit events persisting `resume_token` after the generic audit exemption was removed; the resume flow now emits only `provider_session_reuse_required` in the audit payload, with a regression assertion that the token is absent. The third failure expected 404 for an unregistered tool even though the test identity lacked the invocation scope; the test now supplies the specific scope so the expected 404 tests registry absence rather than authorization denial.
- The isolated PostgreSQL suite on that same pre-fix head reported **106 passed, 1 failed**; the sole failure was the same resume audit-token issue. The fixes are committed on the PR branch; focused, full and PostgreSQL suites must be rerun on the current head before merge.
- The user's local uncommitted `.gitignore`, `frontend/next-env.d.ts` and generated `frontend/tsconfig.tsbuildinfo` were observed and not modified. The pre-existing local PostgreSQL volume remains out of scope and untouched.


## Historical founder verification update — 2026-11-27 (pre-consolidation PR #68 head 41ffdd29)

Founder-reported test results on the exact PR head after fast-forwarding to `41ffdd29a8968e6b7f62d3ea9057f78296c6f5b3`:

- Focused security/regression command covering execution pause/resume, API, audit payload protection, machine identity, DPG and Tool Gateway policy: **141 passed, 2 warnings**.
- Full host suite: **541 passed, 20 skipped, 2 warnings**. The 20 skips are environment-gated live-PostgreSQL tests requiring dedicated connection variables; they are not counted as passes.
- Isolated PostgreSQL 16 Compose suite: **107 passed, 2 warnings**, exit code 0. Migration and app-role grant jobs completed in the disposable test stack.
- The earlier resume audit-token and unregistered-tool test failures are resolved in these reruns.
- Remaining warnings are Starlette/httpx and Authlib/httpx deprecations; they did not fail the runs.
- At that pre-consolidation checkpoint, GitHub Actions had intentionally not been run. No production database, deployment, provider activation or production data operation was performed; PR #68 was still draft at that time.


## Additional independent-review finding — 2026-11-27

- A second-pass review found that the generic `protect_untrusted_payload` API still exposed a caller-selected `resume_token` trusted-identifier exemption. This was narrower than arbitrary-key trust but still violated the intended rule that resume tokens are trusted only inside the validated execution `control_request`. The generic allowlist is now limited to `draft_id`, `lead_id` and `research_record_id`, with a regression test asserting that callers cannot request the resume-token exemption. This regression is included in the consolidated candidate; the current 579-test CI run passed.
- Tool Gateway review confirmed that the successful-call ceiling is checked under the locked AgentSession row and persisted invocation rows retain the session ID. The 100-call ceiling remains a global interim cap, not a persisted per-session budget grant.
