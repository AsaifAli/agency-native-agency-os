# Native integration map — one Agency OS

## Architecture decision

The Agency OS is the only business control plane. The former AI Automation Command Center and AI Engineering Evaluation Harness are not deployed as independent applications, databases, APIs or orchestration systems.

Their useful capabilities are represented by native OS modules:

| Capability | Native OS owner | Boundary |
|---|---|---|
| Agent/workforce registry | `app/workforce_*.py`, `app/models.py` | OS-owned identity, status, reporting, capability and delegation records |
| Task and execution control | `app/main.py`, `app/execution_service.py` | Authenticated, tenant-scoped OS APIs and policy |
| Durable worker execution | `app/worker/`, `app/worker_service.py` | PostgreSQL-owned executions, attempts, leases, heartbeat and recovery |
| Provider/runtime execution | `app/integrations/` | Adapter only; no provider-owned business state or policy bypass |
| Approval and autonomy policy | `app/action_policy.py`, `app/autonomy_policy.py`, `app/founder_admin.py` | Founder authority and backend-enforced protected-action gates |
| Evaluation packs and metrics | `app/evaluation/`, `app/evaluation_service.py` | Deterministic RAG and agent-workflow evaluation in the OS API |
| Audit and event delivery | `app/audit.py`, `app/outbox_service.py` | OS-owned audit and transactional outbox |
| Operator interface | `frontend/` | Next.js Founder Console; dashboards are read models |

## Command Center migration

The standalone Command Center API, scheduler, demo storage, separate auth, independent worker configuration and legacy deployment files were removed. The OS retains its own workforce registry, task/execution APIs, durable workers, runtime adapters, approval policy, audit and Founder Console.

Do not reintroduce a second identity system, database, approval system, scheduler or control plane. Add new agent capabilities through the Agent Registry, OS authorization and scoped runtime/tool adapters.

## Evaluation Harness migration

The standalone Harness API, dashboard, persistence layer, plugin host, MLOps extras, n8n workflow exports and separate deployment configuration were removed from the OS repository. The reusable deterministic evaluation primitives were moved into `app/evaluation/`:

- RAG retrieval, citation and groundedness metrics.
- Agent-workflow task, step, tool, policy and approval metrics.
- Versioned-in-code pack definitions, weighted scores and deterministic gates.
- Tenant-scoped evaluation API persistence and audit remain owned by the OS.

Evaluation judges, trajectory capture, golden-dataset lifecycle, regression baselines and release orchestration are not claimed as implemented merely because deterministic packs exist. Add these only behind OS tenant/data policy, budgets, audit and release gates.

## Automation boundaries

Native Python workers and the PostgreSQL transactional outbox are the initial automation architecture. No n8n, Activepieces, Temporal or second workflow engine is required. External calls run outside database transactions; consumers must be idempotent; delivery is at-least-once with bounded retries, dead letters and reconciliation.

## Other systems

- Public agency website: separate application; signed, idempotent server-to-server lead intake is disabled by default until external configuration and end-to-end validation.
- EvidenceFlow, QuoteSense, LegacyLens and WebQA Intelligence: separate portfolio/client-demo applications, not OS modules.
- OpenClaw: not part of this private OS.
- Telephony: provider-neutral record foundation; no live dialing, STT/TTS or voice runtime is claimed.

## Security and founder authority

1. OS owns users, organizations, clients, workspaces, workforce members, tasks, executions, approvals, budgets, artifacts and audit.
2. Workforce bootstrap does not activate agents. Founder-only capability enablement and member activation are opt-in and policy-checked.
3. Tool grants remain disabled until a governed OS MCP gateway exists.
4. Unknown actions default to manual review; protected actions require founder approval.
5. Runtime eligibility, data classification, tenant scope and authorization are enforced by backend code.
6. Managed Agents remains opt-in, beta and synthetic-first; no ZDR/BAA eligibility or production readiness is implied.
7. Client data and artifacts must remain workspace-scoped. Full isolation, retention/deletion and data-protection controls remain validation work.

## Verification

The native backend CI validates migrations, PostgreSQL integration and automated tests. It does not prove live provider setup, frontend build, production isolation, backup restore, penetration testing or compliance. See `IMPLEMENTATION_STATUS.md` for exact evidence and gaps.
