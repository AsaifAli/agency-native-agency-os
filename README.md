# AI-Native Agency OS

A private, founder-controlled operating system for running an AI solutions agency. This is an internal operating environment, **not a SaaS product**. The public agency website remains a separate application and communicates with the OS only through the signed, idempotent lead-intake boundary.

## Operating model

The agency workforce is represented inside the OS: Founder, Chief of Staff, Executive Office, functional-group leaders, department heads, teams, human members, agents, supervisors and sub-agents. The workforce catalogue describes the organisation; it does not imply that every profile is already a live autonomous runtime.

The founder retains supreme authority. Agents may perform only explicitly enabled, scoped and data-eligible work. Protected actions—including pricing, contracts, payments, sensitive external communications, production releases, destructive actions, client-data deletion and permission/security changes—remain behind backend-enforced founder approval. Unknown actions default to manual review.

The operating philosophy is **founder-in-the-loop, not founder-in-every-loop**: routine work can be delegated within policy, while commercial and high-impact decisions remain under founder control.

## Two operating engines

- **Revenue Engine:** research, lead intake, CRM, qualification, opportunities, proposals and governed outreach foundations.
- **Delivery Engine:** client/workspace onboarding foundations, projects, milestones, tasks, playbooks, scope changes, time/cost capture, QA and handover foundations.

The AI workforce supports both engines. Departments, teams, positions, agents, skills, tools, workers, workflows, tasks, sessions and executions are distinct concepts with explicit relationships and permissions.

## Native architecture

- `frontend/` — Next.js Founder Console.
- `app/` — FastAPI modular monolith and canonical domain services.
- `app/workforce_*.py` — governed workforce catalogue, member lifecycle, capabilities, orchestration plans and delegation DAGs.
- `app/execution_service.py`, `app/worker/`, `app/worker_service.py` — OS-owned execution state, worker claims, attempts, leases, heartbeats, recovery and dependency-ready delegation queueing.
- `app/evaluation/` and `app/evaluation_service.py` — OS-owned deterministic evaluation packs, metrics and quality gates.
- `app/integrations/` — provider/runtime adapters; the OS retains identity, authorization and business state.
- `migrations/` — additive Alembic migrations.
- `tests/` — backend, security, integration and regression tests.
- `docs/` and `skills/` — architecture, security, workforce, operating procedures and reviewed task playbooks.

The former Command Center and Evaluation Harness repositories are **not separate runtimes or control planes**. Their relevant execution, workforce and evaluation capabilities have been migrated into native OS modules. Legacy source snapshots, standalone harness API/dashboard, MLOps extras, n8n workflow exports and duplicate service configuration are not part of this runtime.

## Security and autonomy boundaries

- PostgreSQL is the source of truth; Redis is not authoritative business state.
- Workers execute through OS authorization and persisted execution records.
- Runtime/provider adapters cannot bypass OS policy or write business state independently.
- Workforce activation and capability enablement are founder-only, opt-in operations. Capabilities default disabled.
- Tool grants remain disabled until the OS MCP gateway and scoped tool authorization are implemented.
- Managed Agents is beta and is not eligible for ZDR or HIPAA BAA. The current adapter is opt-in and synthetic-first; live provider setup and production eligibility are not claimed.
- Website lead intake is signed and idempotent, disabled by default, and does not trigger outreach or execution.
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

Docker Compose:

```bash
cp .env.example .env
# Set local-only secrets and database credentials in .env
docker compose up --build
```

Never commit `.env`. Use separate dev, staging and production configuration. Review migrations and backups before applying changes to any persistent database.

## Key operating documents

- `docs/FINAL_SCOPE_AND_ACCEPTANCE.md` — frozen product boundary and acceptance criteria.
- `docs/AGENCY_ORGANIZATION_WORKFORCE_BLUEPRINT.md` — departments, teams, positions and reporting structure.
- `docs/WORKFORCE_AUTONOMY_AND_FOUNDER_AUTHORITY.md` and `docs/FOUNDER_AUTONOMY_MODEL.md` — founder authority and governed autonomy.
- `docs/INTEGRATION_MAP.md` — migration decisions and native module boundaries.
- `docs/CLAUDE_MANAGED_AGENTS_ADAPTER.md` — runtime adapter behavior and limitations.
- `docs/WEBSITE_LEAD_INTAKE.md` — signed website-to-OS boundary.
- `docs/DELIVERY_OPERATIONS_V5.md` — delivery operations.
- `IMPLEMENTATION_STATUS.md` — implemented, tested, partial and unverified capabilities.

## Verification boundary

The native-source cleanup commit (`80b989ae611b08d9a9c37925195517417ba79b05`) passed backend CI: **162 passed, 1 warning** (run [45471143658](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/45471143658)). CI validated migrations against PostgreSQL 16, Python compilation and the backend/PostgreSQL integration suite. The frontend production build, live Claude sessions, website deployment, backup restore, penetration testing and regulatory compliance remain unverified.

This repository is a substantial development foundation, **not a production-ready or fully autonomous agency OS**. See `IMPLEMENTATION_STATUS.md` for the remaining work and evidence boundaries.
