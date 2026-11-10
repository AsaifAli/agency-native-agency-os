# AI-Native Agency OS

Founder-controlled private Agency OS monorepo. This is the unified redevelopment workspace for the AI Automation Command Center and AI Engineering Evaluation Harness.

## What this repository is

- `app/` — Agency OS FastAPI control-plane foundation: authentication, tenant membership, domain models, approvals, policy checks, audit events and runtime integration boundaries.
- `frontend/` — Next.js founder dashboard foundation.
- `integrations/command_center_source/` — cleaned source snapshot of reusable Command Center execution, worker, workflow and telemetry modules. It is a migration source, not yet the production runtime.
- `integrations/evaluation_harness_source/` — cleaned evaluation harness source, evaluation packs, datasets, tests and n8n workflow templates. It is a migration source, not yet the production evaluation service.
- `docs/` — architecture, integration map, security baseline and current audit.
- `tests/` — OS foundation tests.

## Target architecture

```text
Founder Dashboard (Next.js)
          |
Agency OS API (FastAPI) ---- PostgreSQL (business source of truth)
          |                  Redis (queues/cache)
          |
  Policy + Tenant Security + Data Protection + Audit
          |
  Runtime Adapter ---- Claude Managed Agents (eligible data only)
          |           \ Claude Agent SDK / self-managed fallback
          |
  Worker/Sandbox layer
          |
  n8n integration (triggers, schedules, integrations, retries)
          |
  Evaluation Service (Harness packs, trajectories, judge, regression gates)
```

The OS owns organizations, clients, users, agent definitions, tasks, approvals, budgets, permissions and audit state. Claude is an execution runtime, n8n is the automation layer, and the Harness is an evaluation service. None of those external systems owns business-critical state.

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

## Current implementation status

This is an integration baseline, not a production-ready system. The original repositories have been audited and their source has been staged into one monorepo. The legacy modules still need to be ported behind Agency OS domain contracts and tenant-scoped service boundaries. See `docs/INTEGRATION_MAP.md`, `docs/SOURCE_AUDIT.md` and `IMPLEMENTATION_STATUS.md`.

## Verification

Only claim a test, deployment, security control or compliance property when it has been executed and evidenced. Current audit results are recorded in `docs/SOURCE_AUDIT.md`.
