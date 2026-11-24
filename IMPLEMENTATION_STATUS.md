# Agency OS implementation status — stabilization checkpoint

## Verified checkpoint
- Working branch: `feature/agency-os-v5-stabilization`.
- Verified commit: `0f8384ce9a9bfc50babac7f4533bcc089e9cbd65`.
- GitHub Actions run: [45466473903](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/45466473903).
- Backend CI: **156 passed, 0 failed, 1 warning** (Starlette/httpx TestClient deprecation; GitHub Actions also reports a Node 20 action deprecation warning).
- CI validated the Alembic graph, applied migrations to PostgreSQL 16, compiled Python source and ran backend plus PostgreSQL integration tests.
- CI covers workforce provisioning and position/team records, manager-chain delegation guards, Claude provider-agent tooling checks, Managed Agents workflow-run completion and signed/idempotent website lead intake.
- Frontend production build, live Claude provider session, website deployment, backup restore drill, independent penetration test and compliance assessment are not claimed.

## Implemented source capabilities
- Governed workforce schema for offices, functional groups, departments, teams, human/agent/supervisor/sub-agent members, 121 durable position records, capability grants and task delegation lineage; backend migrations and tests passed.
- Founder-only, idempotent bootstrap for the Office of the CEO, five functional groups, 16 departments, 31 teams, 5 group heads, 16 department heads, 16 department specialist definitions, Chief of Staff, Executive Assistant and the full 121-position catalogue. Agent definitions remain disabled and members planned.
- Workspace-scoped workforce read API and founder-only bootstrap; founder-only capability configuration remains disabled by default. Delegation API enforces downward direct-manager relationships, active members, enabled agent definitions, enabled capability grants and founder exclusion. Backend tests passed.
- Signed public website lead intake endpoint (disabled by default): fixed server-side org/workspace mapping, HMAC-SHA256 timestamp validation, body/schema bounds, constant-time signature/key checks, source idempotency, CRM Contact/Lead creation, audit and transactional outbox event in one transaction. No outreach or execution is triggered.
- Workspace-scoped, authenticated execution history API with bounded status filtering and result limits.
- Execution trace API that joins execution and attempt lifecycle audit events after verifying the execution belongs to the requested organization/workspace.
- Founder Console Processes page for execution history and event timelines; Monitoring page for persisted execution status/retry summaries; Workforce page for the org chart, team/position catalogue and member registry.
- Founder dashboard now reads pending approval counts and execution activity from existing APIs.
- Agent Studio department selector now exposes all 16 departments in the workforce blueprint.
- FastAPI modular backend and Next.js Founder Console foundation.
- Organization/workspace-scoped clients, contacts, leads, opportunities, projects and milestones.
- Agent, task, approval, audit and evaluation foundations.
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
- Target organization model and governance skills are documented in `docs/AGENCY_ORGANIZATION_WORKFORCE_BLUEPRINT.md`, `docs/REFERENCE_INTEGRATION_DECISIONS.md` and `skills/`; this does not mean all positions/skills are provisioned as live agents.

## Workforce/runtime gaps still open
- Workforce initialization provisions organisational members and positions only. It does not activate members, enable Agent definitions or start Claude sessions.
- The supervisor planning/decomposition loop, OS-owned child-task scheduling, dependency resolution, result aggregation, review and escalation are not implemented.
- Capability records are configurable but deliberately default disabled. There is no OS MCP tool gateway yet, so capabilities must not be enabled for real tool access.
- Group heads, department heads and specialist Agent definitions are local OS profiles. They are not automatically provisioned as separate Anthropic provider Agents.
- Founder and Executive Office workforce records are chart entries; they are not live human identity accounts.

## Known gaps / not validated
- No production outbox handlers are registered; the website lead event is persisted but does not trigger notifications or automation. External side effects remain disabled.
- Outbox handler heartbeat and actual worker crash/restart recovery need further validation.
- Supervisor-driven task decomposition, specialist execution scheduling, review and escalation are not implemented; the new trace/history UI is visibility, not orchestration.
- Managed Agents live provisioning, provider API compatibility against the actual account, Environment sandbox/egress configuration, webhook/reconciliation for ambiguous session creation and production runtime eligibility are not verified.
- The pre-created Managed Agent owns its tools/MCP/skills. The adapter now queries the provider Agent and rejects non-empty tools/MCP/skills or enabled multiagent configuration; actual account configuration and environment sandbox/egress still require live verification.
- Claude Agent SDK adapter is not implemented.
- Agency OS MCP server and narrowly scoped OS tools are not implemented; this is the prerequisite for enabling real agent capabilities and OS-mediated side effects.
- Full OIDC/JWKS/MFA, secure frontend session lifecycle and scoped machine identities are not implemented.
- Complete cross-workspace isolation across APIs/workers/files/sessions/caches and PostgreSQL RLS are not validated.
- Complete Data Protection Gateway, PII redaction and retention/deletion lifecycle are not implemented.
- Relationship timeline, proposal/SOW/contract workflow, outreach dispatch, scheduling, support and handover workflows are incomplete.
- Live telephony, signed webhooks, STT/TTS and recording lifecycle are not implemented.
- Full finance ledger, invoicing, payment collection and tax/accounting are not implemented.
- Complete QA acceptance/rework metrics and production release gates are incomplete.
- Frontend production build, monitoring/alerting, SBOM, restore drill and security review are not validated.
- Website-to-OS endpoint is implemented and CI-tested on the stabilization branch. Website forwarding/admin retry code is on the separate website branch `feature/agency-os-lead-intake`; it has not been merged, configured or deployed. The bridge remains disabled until both sides are configured and the synthetic end-to-end test is completed.

## Additional feature discovery
- `docs/FEATURE_DISCOVERY_AND_ADOPTION.md` records reviewed patterns from LangGraph, Temporal, Langfuse, Arize Phoenix, ToolHive, Semgrep, OpenHands, Prefect and Sentry. These are research references, not installed integrations.
- The selected immediate work was execution visibility using existing OS-owned records; no new workflow runtime or external provider was added.

## Reference integration decisions
- ECC: selected research-first engineering, skill governance and independent review patterns; no wholesale harness import.
- Strix: optional isolated, authorization-gated QA/Security runner; not installed or executed.
- Claude Skills Hub: discovery index only; imported skills require provenance, license, static review, sandbox test and pinning.
- CodeRabbit: optional PR review signal after privacy, retention, subprocessor, pricing and GitHub permission review; not connected and never a replacement for CI/QA/founder approval.

## Safety boundary
Use synthetic/mock data until authentication, tenant isolation, runtime eligibility, retention, provider authorization and recovery controls are validated. Do not enable real outreach, dialing, client transcript ingestion or production side effects based only on API routes or outbox rows. Managed Agents is beta and not ZDR/HIPAA eligible; do not send confidential/regulated data without an eligible, reviewed alternative and appropriate contractual controls.

The repository is a substantial development foundation, not a production-ready or fully autonomous agency OS.
