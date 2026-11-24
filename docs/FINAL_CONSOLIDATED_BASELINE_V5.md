# Final consolidated implementation baseline — v5

This release takes the founder-governance v4 snapshot as the code baseline and adds a tested delivery-operations vertical slice. It preserves the existing Revenue/Delivery, execution, approvals, telephony-record and evaluation foundations.

## Product definition

A private, founder-controlled operating system for an AI solutions agency. It is not a SaaS product. The public agency website remains separate. The OS is the private system of record for business operations, authorization, execution, approvals, artifacts and audit.

The operating principle is **founder-in-the-loop, not founder-in-every-loop**:
- Agents/workers may perform explicitly allowlisted, low-risk internal work after backend authorization and budget/data/scope checks.
- Unknown actions default to manual review.
- Sensitive commercial, financial, external, production and destructive actions require explicit founder approval.
- Founder authority is a distinct grant, not implied by organization-owner role.
- Every execution must be bounded, persisted, auditable and recoverable.

## Included in this consolidated bundle

- v4 Founder Authority model, provisioning CLI, autonomy classification, telephony record APIs and approval enforcement foundation.
- Existing Revenue/Delivery domain models and APIs for clients, contacts, leads, opportunities, projects and milestones.
- Existing worker/execution lifecycle foundation and mock runtime.
- Existing evaluation API foundation and retained Evaluation Harness source snapshot.
- New service playbooks, scope-change requests, time entries, project cost records and project financial summary.
- New founder exception inbox and agent execution reliability read model.
- Founder Console Operations page for exceptions and execution reliability.
- Additive migration `d8c5a1f20973_delivery_operations.py`.

## Frozen architecture

- Next.js private Founder Console.
- FastAPI modular monolith.
- PostgreSQL as source of truth.
- Native OS domain services, durable workers and transactional outbox.
- Provider adapters; providers do not own business state.
- Docker Compose for local development.
- Redis remains optional coordination/cache infrastructure; not the source of truth or a substitute for durable execution.
- n8n is not an enabled runtime dependency.
- No public signup, client portal, SaaS subscription/billing, website chatbot, Kubernetes or second workflow orchestrator.

## Departments and supervision model

Logical departments:
- Chief of Staff
- Business Development
- Marketing
- Solutions
- Engineering
- QA/Security
- Operations/Delivery
- Client Success
- Finance

Supervisor responsibilities are activated when workload requires them; they are not all permanently running agents. Supervisors plan and decompose authorized tasks, define acceptance criteria, select permitted specialists, track dependencies and budgets, review outcomes, retry/reassign within bounds and escalate exceptions. Supervisors cannot grant permissions, exceed budgets, approve their own protected actions or perform founder-reserved actions.

## P0 implementation priorities after bundle application

1. Production authentication, founder session lifecycle and scoped machine identities.
2. Complete endpoint/worker enforcement of autonomy classes and Data Protection Gateway.
3. Durable outbox dispatcher, safe leases, heartbeats, bounded retries, dead letters and reconciliation.
4. Supervisor orchestration and specialist delegation using persisted OS tasks/executions.
5. Full exception resolution actions and workflow recovery controls.
6. Independent QA acceptance and release gates.
7. Cross-workspace isolation tests for APIs, workers, sessions, files and caches.
8. End-to-end synthetic workflow evidence: lead → qualification → approval → project → execution → QA → handover.

## P1 operating capabilities

- Full client engagement lifecycle and relationship timeline.
- Proposal/SOW records and commercial approvals.
- Delivery playbook adoption and traceability from requirements to tests/handover.
- Time/capacity reporting and estimates versus actuals.
- Project-level costs and provisional margin.
- Agent outcome, QA acceptance, rework and escalation metrics.
- External provider adapters and website lead intake after security and idempotency gates.

## Explicitly deferred

- Full accounting, payroll, tax/statutory compliance.
- Client portal and public signup.
- Website chatbot/voice widget.
- Live autonomous outbound dialing or email until consent, suppression, sender identity, webhook and stop-condition controls are validated.
- Automatic proposal/contract sending, binding pricing, payments and production deployment.
- Permanent always-on agent supervisors.
- Multiple orchestrators or platform proliferation.

## Acceptance rule

A capability must be labelled separately as:
- **Implemented** — source code exists.
- **Tested** — automated/manual tests pass.
- **Externally configured** — provider/account configuration is complete.
- **Validated** — end-to-end behavior and recovery are demonstrated in the target environment.
- **Production-ready** — all mandatory security, reliability, operational and business gates have evidence.

Passing unit tests does not prove production readiness. See `SECURITY_RELIABILITY_ACCEPTANCE.md`, `FOUNDER_AUTONOMY_MODEL.md` and `DELIVERY_OPERATIONS_V5.md`.
