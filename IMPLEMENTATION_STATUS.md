# Agency OS implementation status — stabilization checkpoint

## Source of truth
- Working branch: feature/agency-os-v5-stabilization.
- Starting branch head inspected: f3ae03d7c6e674a0c7d85157a7bb779559ce1b83.
- The source includes an opt-in Claude Managed Agents adapter and adapter tests. Earlier text claiming that the adapter did not exist was stale and incorrect.
- CI at the inspected head completed with **4 failed, 136 passed**. Failures were: one Managed Agents test mock-client header setup issue, and three processor classification tests caused by a duplicate RuntimeExecutionError definition shadowing the shared runtime exception.
- A previous CI run on commit 4e914384bd1eef94c1ffe61b94ea5e284e6da8b0 reported 133 passed, 0 skipped. That is historical evidence only and does not validate the current head.
- PostgreSQL migrations and source compilation completed in the failed run. The test suite did execute against PostgreSQL 16.
- No frontend production build, production deployment, live Anthropic session, live integration, backup restore drill, independent penetration test or compliance assessment is claimed.

## Implemented source capabilities
- FastAPI modular backend and Next.js Founder Console foundation.
- Organization/workspace-scoped clients, contacts, leads, opportunities, projects and milestones.
- Agent, task, approval, audit and evaluation foundations.
- Explicit Founder Authority separate from organization-owner membership; founder provisioning CLI and founder-only decisions.
- Single-use approval consumption with action/resource/workspace matching and active Founder Authority recheck.
- Central autonomy classification: allowlisted internal actions, founder-approval actions and manual-review default for unknown actions.
- Durable execution lifecycle with persisted attempts, worker claims, leases, heartbeats, bounded retries and expired-execution recovery.
- Mock runtime boundary and opt-in Claude Managed Agents adapter.
- Managed Agents adapter persists session ID after create response, resumes persisted session, enforces synthetic-only eligibility, sets a session budget and routes tool/action pauses to manual review.
- Transactional outbox writes for selected domain events; dispatcher supports registered-handler filtering, SKIP LOCKED claims, leases, bounded attempts, acknowledgement, sanitized errors, retries, dead letters and lease reconciliation.
- Founder-only outbox health endpoint.
- Workspace-scoped call/transcript records; no live voice provider or dialing.
- Delivery playbooks, founder-approved scope changes, time/cost records, provisional project financial summaries, exception inbox and execution reliability views.

## Known gaps / not validated
- No production outbox handlers are registered; external side effects remain disabled.
- Outbox handler heartbeat and real worker crash/restart recovery need further validation.
- Supervisor-driven task decomposition, specialist delegation, review and escalation are not implemented.
- Managed Agents live provisioning, provider API contract against the actual account, webhook/reconciliation for ambiguous session creation and production runtime eligibility are not verified.
- Claude Agent SDK adapter is not implemented.
- Agency OS MCP server and narrowly scoped OS tools are not implemented.
- Full OIDC/JWKS/MFA, secure frontend session lifecycle and scoped machine identities are not implemented.
- Complete cross-workspace isolation across APIs/workers/files/sessions/caches and PostgreSQL RLS are not validated.
- Complete Data Protection Gateway, PII redaction and retention/deletion lifecycle are not implemented.
- Relationship timeline, proposal/SOW/contract workflow, outreach dispatch, scheduling, support and handover workflows are incomplete.
- Live telephony, signed webhooks, STT/TTS and recording lifecycle are not implemented.
- Full finance ledger, invoicing, payment collection and tax/accounting are not implemented.
- Complete QA acceptance/rework metrics and production release gates are incomplete.
- Frontend production build, monitoring/alerting, SBOM, restore drill and security review are not validated.
- Website-to-OS lead intake remains deferred.

## Safety boundary
Use synthetic/mock data until authentication, tenant isolation, runtime eligibility, retention, provider authorization and recovery controls are validated. Do not enable real outreach, dialing, client transcript ingestion or production side effects based only on API routes or outbox rows. Managed Agents is beta and is not ZDR/HIPAA eligible; do not send confidential/regulated data without an eligible, reviewed alternative and appropriate contractual controls.

The repository is a substantial development foundation, not a production-ready or fully autonomous agency OS.
