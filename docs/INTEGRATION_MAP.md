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

## Private AI business operations layer

The first tranche adds workspace-scoped, versioned knowledge records and source-validated business drafts for front-desk lead response, meeting-to-proposal preparation and receivables follow-up. The OS owns the records, provenance, approvals, audit and workspace authorization; Claude remains an optional hosted reasoning/runtime adapter. The UI is a Founder Console page, and read-only receivables ageing and founder count snapshots do not perform external actions. Binary upload/index lifecycle, hosted model generation, transcript ingestion, payment matching and reminder dispatch remain out of scope until separately secured and tested. Local AI and local inference are explicitly excluded. Worker access to these tables is denied until a dedicated execution-capability path exists.

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

## Results as a Service (RAAS)

The agency sells measurable client outcomes, not agents or automation for their own sake. The OS records the agreed problem, metric, baseline, target, measurement method and acceptance criteria as project outcomes. Measurements are append-only and retain source references; a source reference or narrative is not independent verification. Delivery acceptance is a founder-authorized decision against the agreed criteria and remains distinct from whether the business-impact target has been achieved.

RAAS does not imply contingent/performance-based pricing. Pricing, attribution, measurement windows, external dependencies and risk allocation must be explicitly agreed in the commercial scope. Automatic KPI ingestion, client sign-off, verified external impact attestations and outcome revision workflows remain future work.

## Automation boundaries

Native Python workers and the PostgreSQL transactional outbox are the initial automation architecture. No n8n, Activepieces, Temporal or second workflow engine is required for the current workload. External calls run outside database transactions; consumers must be idempotent; delivery is at-least-once with bounded retries, dead letters and reconciliation.

### n8n evaluation decision

n8n remains an optional integration/trigger layer, not an execution system of record or a second business control plane. Do not reactivate the currently suspended instance until a concrete webhook, connector or schedule requirement cannot be handled proportionately by the OS outbox and workers.

The current agency-managed use case may fit n8n's Sustainable Use License: the agency may build and operate workflows for clients on its own instance, provided clients do not access the n8n editor or change workflow logic. If clients configure workflows through n8n UI, API, MCP or an AI agent, or n8n is offered as a hosted service, obtain the appropriate commercial license first. Confirm any changed use case with n8n licensing before adoption. n8n is source-available under a fair-code license, not OSI open source. See the [n8n license FAQ](https://support.n8n.io/article/can-i-use-your-license-for-my-use-case?trk=article-ssr-frontend-pulse_little-text-block) and [Sustainable Use License](https://github.com/n8n-io/n8n-docs/blob/main/docs/n8n-community-license/README.md).

If adopted later:
- n8n may receive webhooks, run schedules and call authenticated Agency OS APIs; it must never write core tables or own approval, CRM, project, execution or audit state.
- Keep its editor and public API private to authorized operators; clients receive approved outputs and workflow visualizations through the Agency OS, not direct n8n access.
- Use external task-runner mode for Code nodes; n8n documents that internal mode shares the n8n process identity and is not suitable for production code execution. Harden runners as separate unprivileged, read-only containers.
- Require TLS, SSO/MFA, encryption-key rotation, node allowlists, SSRF protection, execution-data redaction, restricted egress, workflow versioning, release review, logs and recovery procedures.
- Do not enable queue mode or a second Redis/worker fleet unless measured workflow volume justifies it; n8n queue mode introduces its own Redis-backed execution workers and database state.

Security references: [Securing n8n](https://docs.n8n.io/deploy/host-n8n/configure-n8n/security/), [Task runners](https://docs.n8n.io/deploy/host-n8n/configure-n8n/set-up-task-runners/), [Queue mode](https://docs.n8n.io/deploy/host-n8n/configure-n8n/scaling/enable-queue-mode/).

## Private AI and Business Operations layer (planned)

The selective design from the ReStructure Brief's "The Private AI Operating System" is captured in [PRIVATE_AI_OPERATING_MODEL.md](PRIVATE_AI_OPERATING_MODEL.md). It proposes a workspace-scoped, versioned knowledge layer; grounded lead-response drafts; meeting-to-proposal preparation; receivables/reminder and payment-match proposals; a source-backed founder brief; and governed hosted-provider routing. Local AI runtimes and local inference are explicitly out of scope.

These are planned capabilities, not implemented features. They must reuse the existing CRM, proposal, invoice, payment-receipt, approval, execution, audit and outbox foundations. The OS remains the only business control plane. Do not add a parallel Hermes/CRM/accounting/workflow stack or claim local-only processing without end-to-end data-flow and egress verification. File/RAG ingestion, auto-send, meeting recording and bank matching remain gated by the security and lifecycle prerequisites in the design document. Local AI runtimes and local inference are explicitly out of scope.

## Other systems

- Public agency website: separate application; signed, idempotent server-to-server lead intake is implemented in both repositories and merged to main (website PR #30; OS endpoint already merged). It remains disabled until external configuration and end-to-end validation.
- EvidenceFlow, QuoteSense, LegacyLens and WebQA Intelligence: separate portfolio/client-demo applications, not OS modules.
- OpenClaw: not part of this private OS.
- Telephony: provider-neutral record foundation; no live dialing, STT/TTS or voice runtime is claimed.

## Security and founder authority

1. OS owns users, organizations, clients, workspaces, workforce members, tasks, executions, approvals, budgets, artifacts and audit.
2. Workforce bootstrap does not activate agents. Founder-only capability enablement and member activation are opt-in and policy-checked.
3. An opt-in, session-authenticated MCP transport now delegates to the OS Tool Gateway; production enablement remains blocked pending CI, staging, cross-workspace and provider/Vault verification. See [CLAUDE_MANAGED_MCP_GATEWAY.md](CLAUDE_MANAGED_MCP_GATEWAY.md).
4. Unknown actions default to manual review; protected actions require founder approval.
5. Runtime eligibility, data classification, tenant scope and authorization are enforced by backend code.
6. Managed Agents remains opt-in, beta and synthetic-first; no ZDR/BAA eligibility or production readiness is implied.
7. Client data and artifacts must remain workspace-scoped. Full isolation, retention/deletion and data-protection controls remain validation work.

## Verification

The native backend CI validates migrations, PostgreSQL integration and automated tests. It does not prove live provider setup, frontend build, production isolation, backup restore, penetration testing or compliance. See `IMPLEMENTATION_STATUS.md` for exact evidence and gaps.
