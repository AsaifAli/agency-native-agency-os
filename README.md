# AI-Native Agency OS

Founder-controlled private Agency OS monorepo. This is the unified redevelopment workspace for reusable AI Automation Command Center and AI Engineering Evaluation Harness capabilities. The v5 bundle adds a delivery-operations vertical slice for playbooks, scope control, time/cost capture and founder exception visibility.

## What this repository is

- `app/` — Agency OS FastAPI control-plane foundation: authentication, tenant membership, Revenue/Delivery domains, founder approvals, autonomy policy, execution records, telephony records and delivery operations.
- `frontend/` — Next.js founder dashboard foundation.
- `integrations/command_center_source/` — cleaned source snapshot of reusable Command Center execution, worker and telemetry modules. It is a migration source, not a production runtime.
- `integrations/evaluation_harness_source/` — cleaned evaluation harness source, evaluation packs, datasets and tests. It is a migration source, not yet the production evaluation service.
- `docs/` — architecture, integration map, security baseline and current audit.
- `tests/` — OS foundation tests.

## Target architecture

```text
Founder Dashboard (Next.js)
          |
Agency OS API (FastAPI) ---- PostgreSQL (business source of truth)
          |                  PostgreSQL transactional outbox
          |
  Policy + Tenant Security + Data Protection + Audit
          |
  Runtime Adapter ---- Claude Managed Agents (eligible data only)
          |           \ Claude Agent SDK / self-managed fallback
          |
  Worker/Sandbox layer
          |
  Durable workers + provider adapters (external integrations)
          |
  Evaluation Service (Harness packs, trajectories, judge, regression gates)
```

The OS owns organizations, clients, users, agent definitions, tasks, approvals, budgets, permissions, call records, transcripts and audit state. Claude is a candidate execution runtime; the OS owns business state and native automation policy. External providers are adapters, not sources of truth. None of those external systems owns business-critical state.

## Important boundaries

- Managed Agents is beta and is not currently eligible for ZDR or HIPAA BAA coverage. Route only eligible public/synthetic or contractually authorized workloads; use a verified alternative runtime for workloads requiring ZDR/BAA.
- Contracts, pricing, payments, sensitive external communications, production releases, destructive actions, client-data deletion and security/permission changes require backend-enforced approval.
- Public agency website and EvidenceFlow, QuoteSense, LegacyLens and WebQA Intelligence remain separate projects and are not Agency OS modules.
- OpenClaw is not part of this private OS.
- Do not put secrets, customer data or production data in source control.

## Local development

Backend:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

Docker:
```bash
docker compose up --build
```

Copy `.env.example` to `.env` and supply local-only values. Never commit `.env`.

## Telephony foundation

The current telephony module records inbound/outbound call intent, status, CRM associations and transcripts. It does not place or answer calls. See `docs/TELEPHONY_AND_EVENTS.md` and `docs/APPLY_BUNDLE.md` before applying migrations.

## Delivery operations (v5)

The OS now includes workspace-scoped service playbooks, founder-approved scope changes, project time entries, project cost records, provisional financial summaries, a read-only founder exception inbox and agent execution reliability metrics. See `docs/DELIVERY_OPERATIONS_V5.md` for the API and limits.

## Current implementation status

This is a tested development foundation, not a production-ready or fully autonomous system. The original repositories have been audited and their source has been staged into one monorepo. The legacy modules still need to be ported behind Agency OS domain contracts and tenant-scoped service boundaries. See `docs/INTEGRATION_MAP.md`, `docs/SOURCE_AUDIT.md` and `IMPLEMENTATION_STATUS.md`.

## Verification

Only claim a test, deployment, security control or compliance property when it has been executed and evidenced. Current audit results are recorded in `docs/SOURCE_AUDIT.md`.


## Final scope freeze

The agreed product scope, architecture decisions, domain lifecycles, security gates and definition of done are documented in:

- `docs/FINAL_SCOPE_AND_ACCEPTANCE.md`
- `docs/ARCHITECTURE_DECISIONS.md`
- `docs/DOMAIN_LIFECYCLE.md`
- `docs/SECURITY_RELIABILITY_ACCEPTANCE.md`
- `docs/DELIVERY_OPERATIONS_V5.md`
- `docs/FINAL_CONSOLIDATED_BASELINE_V5.md`
- `docs/BASELINE_RECONCILIATION.md`

No speculative feature expansion is planned after this baseline. Work moves to implementation completion, integration, stabilization, testing and validation.

## Automation decision

The OS initially uses native domain services, durable workers and a PostgreSQL transactional outbox. n8n-related files in the repository are legacy references only and are not an enabled runtime dependency.
