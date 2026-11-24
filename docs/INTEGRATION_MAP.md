# Integration map — one Agency OS

## Decision

The uploaded Command Center and Evaluation Harness source snapshots are migration inputs to one private Agency OS. They are not independent production products and must not retain competing identity, persistence, authorization or orchestration.

## Command Center -> OS execution capabilities

| Existing capability | OS destination | Treatment |
|---|---|---|
| FastAPI run/control endpoints | Task and execution APIs | Rebuild around OS identity, tenant scope and policy |
| Agent/workflow definitions | Agent Registry, skills and native process definitions | Normalize distinct concepts and version them |
| RQ/Redis worker patterns | Native durable workers | Reuse patterns only where useful; PostgreSQL owns execution state |
| LangGraph | Bounded reasoning adapter only where justified | It does not own business process state |
| PostgreSQL run/audit persistence | OS database | Migrate into canonical tenant-scoped records |
| Human approvals | OS approval service | Backend-enforced before protected side effects |
| LLM provider integrations | Runtime/provider adapters | Secrets stay outside prompts, logs and source |
| Streamlit operations UI | Not retained | Next.js Founder Console is the operator UI |

## Evaluation Harness -> OS evaluation service

| Existing capability | OS destination | Treatment |
|---|---|---|
| AgentRun/trajectory capture | Execution/session event contract | Tenant, task, agent, session and correlation scoped |
| Evaluation packs and metrics | Versioned evaluation service | Preserve generic RAG, agent, safety and regression primitives |
| LLM judge | Evaluation judge adapter | Runtime policy, data eligibility, cost budget and untrusted-output handling |
| Golden datasets/baselines | Versioned evaluation datasets | Synthetic-first; client datasets separately classified and authorized |
| Regression/quality gates | Task/release quality gates | Deterministic required gates cannot be overridden by model output |
| Prompt/model/config lineage | Artifact and execution lineage | Immutable version references |

## Native automation boundaries

No n8n, Activepieces, Temporal or other workflow engine is required initially. The OS owns business state, permissions, approvals, audit and durable execution. Native workers perform controlled jobs. PostgreSQL transactional outbox is the integration boundary.

Existing n8n-related source files and workflow JSON exports may remain as legacy migration references only. They are not enabled or required at runtime. External automation may be reconsidered only when measured requirements exceed the tested native design.

## Other systems

- Public agency website: separate application; future secure server-to-server intake API. Not included in this source bundle.
- EvidenceFlow, QuoteSense, LegacyLens and WebQA Intelligence: separate portfolio/client-demo projects, not OS modules.
- OpenClaw: not part of the private Agency OS.
- Telephony: provider-neutral adapter and separate real-time voice/media boundary. Current source only records call intent/history and transcript artifacts; it does not place or receive calls.

## Current integration evidence

- Generic RAG and agent-workflow evaluation packs are exposed through the OS API and persist evaluation runs in the OS scope.
- Telephony record APIs create workspace-scoped call records, transcript records, audit entries and outbox events.
- These are foundation slices, not completed integrations. Evaluation trajectories, judges, regression baselines, actual provider dispatch, voice runtime, webhook security and outbox dispatch remain unimplemented.

## Migration principles

1. OS owns canonical identity, workspace, client, task, agent, session, approval, execution and audit records.
2. Port useful worker/execution behavior behind OS domain contracts.
3. Port generic evaluation primitives behind OS event and policy contracts.
4. Complete outbox dispatch with leases, retries, dead letters and reconciliation.
5. Implement provider adapters only behind authentication, data protection, authorization and audit.
6. Preserve the website as a separate future intake client.
7. Keep legacy snapshots for traceability until each useful primitive is ported and verified; do not run them as duplicate platforms.
