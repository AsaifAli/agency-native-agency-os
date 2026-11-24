# AI-Native Agency OS

Founder-controlled private Agency OS monorepo. This is the unified redevelopment workspace for reusable AI Automation Command Center and AI Engineering Evaluation Harness capabilities. The v5 bundle adds delivery operations for playbooks, scope control, time/cost capture and founder exception visibility.

## What this repository is
- `app/` — Agency OS FastAPI control-plane foundation: authentication, tenant membership, Revenue/Delivery domains, founder approvals, autonomy policy, execution records, telephony records and delivery operations.
- `frontend/` — Next.js private Founder Console foundation.
- `integrations/command_center_source/` — cleaned Command Center source snapshot; migration input, not a production runtime.
- `integrations/evaluation_harness_source/` — cleaned evaluation source snapshot; migration input, not yet the production evaluation service.
- `docs/` — architecture, integration map, security baseline, audits and operating model.
- `skills/` — Agency OS-owned, reviewed task playbooks.
- `tests/` — backend and integration tests.

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

The OS owns organizations, clients, users, agent definitions, tasks, approvals, budgets, permissions, call records, transcripts and audit state. Claude is an execution runtime behind an adapter; the OS owns business state and authorization. Providers are not sources of truth.

## Important boundaries
- Managed Agents is beta and is not ZDR or HIPAA BAA eligible. Use only approved eligible data; the current execution policy is synthetic-first.
- The Managed Agent referenced by the adapter owns its configured tools, MCP servers, skills and multiagent settings. Before creating a session, the adapter fetches the provider Agent and fails closed if those capabilities are configured. The OS MCP gateway is not implemented yet, so the initial provider Agent must remain tool-free.
- Contracts, pricing, payments, sensitive external communications, production releases, destructive actions, client-data deletion and security/permission changes require backend-enforced approval.
- Public agency website and EvidenceFlow, QuoteSense, LegacyLens and WebQA Intelligence remain separate projects. A signed, idempotent website lead intake endpoint is implemented but disabled by default; website forwarding is staged separately and is not yet deployed.
- OpenClaw is not part of this private OS.
- Never put secrets, customer data or production data in source control.

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

## Operating model and integrations
- [Agency organization and workforce blueprint](docs/AGENCY_ORGANIZATION_WORKFORCE_BLUEPRINT.md) — all 16 departments, positions, reporting, responsibilities, KPIs, autonomy and OS mapping. The Founder Console now includes a Workforce page to provision and inspect the chart.
- [Reference integration decisions](docs/REFERENCE_INTEGRATION_DECISIONS.md) — ECC, Strix, Claude Skills Hub and CodeRabbit fit and guardrails.
- [Feature discovery and adoption decisions](docs/FEATURE_DISCOVERY_AND_ADOPTION.md) — additional orchestration, observability, MCP governance and engineering assurance references.
- [Claude Managed Agents adapter](docs/CLAUDE_MANAGED_AGENTS_ADAPTER.md) — current adapter contract, configuration and caveats.
- [Website lead intake](docs/WEBSITE_LEAD_INTAKE.md) — signed, idempotent public website → private Revenue Engine boundary.
- [Implementation status](IMPLEMENTATION_STATUS.md) — implemented, incomplete and unverified capabilities.

## Telephony foundation
The current telephony module records inbound/outbound call intent, status, CRM associations and transcripts. It does not place or answer calls. See `docs/TELEPHONY_AND_EVENTS.md` and `docs/APPLY_BUNDLE.md` before applying migrations.

## Delivery operations (v5)
The OS includes workspace-scoped service playbooks, founder-approved scope changes, project time entries, project cost records, provisional financial summaries, a read-only founder exception inbox and agent execution reliability metrics. See `docs/DELIVERY_OPERATIONS_V5.md`.

## Verification
The backend CI at commit `0f8384ce9a9bfc50babac7f4533bcc089e9cbd65` completed successfully: **156 passed, 0 failed, 1 warning**. It validated the migration graph, PostgreSQL 16 migrations, Python compilation and backend/PostgreSQL integration tests, including workforce, Managed Agents safety and signed website intake. The frontend production build was not part of this run. This does not validate live providers, website deployment, backup restore, penetration testing or compliance. See [the CI run](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/45466473903).

## Scope freeze
The agreed product scope, architecture decisions, domain lifecycles, security gates and definition of done are documented in:
- `docs/FINAL_SCOPE_AND_ACCEPTANCE.md`
- `docs/ARCHITECTURE_DECISIONS.md`
- `docs/DOMAIN_LIFECYCLE.md`
- `docs/SECURITY_RELIABILITY_ACCEPTANCE.md`
- `docs/DELIVERY_OPERATIONS_V5.md`
- `docs/FINAL_CONSOLIDATED_BASELINE_V5.md`
- `docs/BASELINE_RECONCILIATION.md`

The OS initially uses native domain services, durable workers and a PostgreSQL transactional outbox. n8n-related files are legacy references, not an enabled runtime dependency. Avoid speculative feature expansion; finish implementation, integration, stabilization, testing and validation against the acceptance baseline.
