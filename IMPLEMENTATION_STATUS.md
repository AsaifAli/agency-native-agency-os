# Agency OS implementation status — v5 stabilization baseline

## Source of truth and verification

- Active implementation baseline: `feature/agency-os-v5-autonomous-business-os` at commit `d30957e5`.
- This stabilization branch is based on that exact v5 commit; it is not based on the older `main` branch.
- The original v5 bundle manifest reported **102 passed, 1 skipped**; the newer reproducible CI result supersedes that historical build-environment count.
- The previous Phase 1 document contained contradictory historical test claims. The contradiction is corrected; the current 133-test CI run is the verified baseline.
- GitHub Actions backend CI passed on commit `4e914384bd1eef94c1ffe61b94ea5e284e6da8b0`: **133 passed, 0 skipped, 1 upstream Starlette/httpx deprecation warning**. The workflow validated the Alembic graph, applied all migrations to a disposable PostgreSQL 16 database, compiled Python source and ran the full backend suite including the PostgreSQL concurrency/recovery tests.
- Frontend production build has not been verified. There is no committed frontend lockfile, so CI does not claim reproducible frontend dependency installation.
- No production deployment, live provider integration, backup restore drill, penetration test, or compliance assessment is claimed.

## Implemented in source

- FastAPI modular backend and Next.js private Founder Console foundation.
- Organization/workspace-scoped clients, contacts, leads, opportunities, projects and milestones.
- Agent, task, approval, audit and evaluation foundations.
- Explicit Founder Authority, distinct from organization-owner membership, with provisioning CLI and founder-only approval decisions.
- Single-use approval consumption primitive with action/resource/workspace matching and active Founder Authority recheck.
- Central autonomy classification: allowlisted routine internal actions, founder-approval actions, and manual-review default for unknown actions.
- Durable execution lifecycle: queued executions, persisted attempts, worker claims, leases, heartbeats, bounded retries and expired-execution recovery.
- Mock runtime boundary, explicitly disabled unless configured for development/test.
- Transactional outbox writes in the same business transaction for selected Revenue/Delivery, Operations and Telephony events.
- Outbox delivery implementation: registered-event filtering, `FOR UPDATE SKIP LOCKED` claims, expiring leases, bounded attempts, handler invocation outside DB transactions, acknowledgement, sanitized errors, exponential retry, dead-letter transition and lease reconciliation.
- Worker maintenance invokes outbox reconciliation and dispatch for explicitly registered handlers.
- Founder-only, organization-scoped outbox health read endpoint.
- Workspace-scoped call-session/transcript record APIs; no live voice provider or dialing is enabled.
- Service playbooks, founder-approved scope changes, time entries, project costs, provisional financial summaries, exception inbox and agent execution reliability views.

## Explicitly not implemented or not validated

- No production outbox handlers are registered; the handler registry is intentionally empty. Outbox events are persisted but no external side effects are enabled.
- Outbox handler lease renewal/heartbeat and actual worker process crash/restart recovery are not implemented/validated.
- Supervisor-driven task decomposition, specialist delegation, review and escalation are not implemented.
- Claude Managed Agents and Claude Agent SDK adapters are not implemented; runtime registry currently enables only the explicitly configured mock runtime in development/test.
- Production OIDC/JWKS/MFA, secure frontend session lifecycle and scoped machine identities are not implemented.
- Full API/worker/file/session/cache cross-workspace isolation and PostgreSQL RLS are not validated.
- Complete Data Protection Gateway, PII redaction and end-to-end retention/deletion lifecycle are not implemented.
- Full relationship timeline, proposal/SOW/contract workflow, outreach delivery, scheduling, support and handover workflows are incomplete.
- Live inbound/outbound telephony, signed webhooks, real-time voice runtime, STT/TTS and recording management are not implemented.
- Complete finance ledger, invoicing, payment collection, tax/accounting and FX conversion are not implemented.
- Full QA acceptance/rework metrics and production release gates are incomplete.
- Frontend production build, deployment, monitoring/alerting, SBOM, restore drill and security review are not validated.
- Website-to-OS lead intake is intentionally deferred until the private OS is stabilized.

## Safety boundary

Use synthetic/mock data until authentication, tenant isolation, runtime eligibility, retention, provider authorization and recovery controls are validated. Do not enable real outbound communication, dialing, client transcript ingestion or production side effects based only on the presence of an API route or outbox row.

The current source is a substantial development foundation. It is **not yet a fully autonomous or production-ready business OS**.

## Stabilization acceptance order

1. Establish reproducible CI and resolve migration/test failures.
2. Close authorization and cross-workspace isolation gaps in API and worker paths.
3. Complete execution/outbox recovery evidence and operational visibility.
4. Implement the supervisor/orchestration layer over persisted tasks and executions.
5. Add Claude runtime adapter behind a provider boundary, retaining mock runtime tests.
6. Add evaluation/release gates and end-to-end synthetic Revenue-to-Delivery workflow evidence.
7. Only then assess production identity, external providers, voice and deployment readiness.
