# Integration map — one Agency OS

## Decision

Both uploaded repositories are inputs to one private Agency OS. They are not to remain two independently deployed products and they are not to become separate OS modules with competing identity, persistence or orchestration.

## Command Center → OS execution capabilities

| Existing capability | Destination in the OS | Migration treatment |
|---|---|---|
| FastAPI run/control endpoints | OS task and execution APIs | Rebuild around OS task IDs, tenant scope and policy checks |
| Agent/workflow definitions | Agent Registry + versioned skills | Normalize agent, skill, tool and workflow concepts |
| RQ workers / Redis | OS worker execution layer | Reuse worker patterns; introduce tenant-scoped job envelopes and sandboxing |
| LangGraph orchestration | Runtime/agent adapter only where justified | Remove as business workflow owner; n8n owns visual automation |
| PostgreSQL run/audit persistence | OS database | Migrate schemas; OS remains source of truth |
| Human approvals | OS approval service | Centralize and enforce in backend before side effects |
| LLM provider integration | Runtime adapter / gateway | No provider secrets in prompts, logs or source |
| Streamlit operations UI | Not retained as product UI | Founder dashboard is Next.js |

## Evaluation Harness → OS evaluation service

| Existing capability | Destination in the OS | Migration treatment |
|---|---|---|
| AgentRun/trajectory capture | Shared execution event contract | Bind every record to tenant, task, agent and session |
| Evaluation packs and metrics | Versioned evaluation service | Preserve generic RAG/agent workflow/code evaluation primitives; remove out-of-scope portfolio targets |
| LLM-as-a-judge | Evaluation judge adapter | Explicit model/runtime policy, cost budget and untrusted-output handling |
| Golden datasets/baselines | Versioned evaluation datasets | Synthetic/mock-first; client datasets separately classified and authorized |
| Regression/quality gates | Release and task quality gates | Deterministic gates; no model may override a failed required gate |
| Prompt/model/config lineage | OS artifact lineage | Persist immutable version references |
| n8n workflows | OS-managed n8n integration | n8n triggers and integrates; API enforces authorization and approvals |

## n8n boundaries

n8n owns event triggers, schedules, external integrations, conditional routing, retries and notifications. The OS owns workflow metadata, authorization, client scope, execution state, approvals and audit. Do not build a competing general-purpose workflow engine in FastAPI.

## Out of scope

The public agency website, EvidenceFlow, QuoteSense, LegacyLens and WebQA Intelligence are separate initiatives. Their adapters, datasets and demo-specific workflows are not included as Agency OS runtime dependencies. OpenClaw is public-site demo-only.

## Implemented vertical slice — evaluation packs

The OS API now imports the Harness' generic RAG and agent-workflow packs through a namespaced registry. `POST /v1/orgs/{org_id}/evaluations` evaluates expected/actual payloads, applies weighted metrics and hard gates, persists the run under the OS organization/workspace, and emits an `evaluation.completed` audit event. The dashboard lists active packs and runs a synthetic sample.

This is the first integration slice, not the complete Harness migration: trajectories, judge calls, regression baselines, model lineage, dataset governance and release-gate wiring remain.

## Migration order

1. Establish canonical OS identity, tenant, task, agent, session, approval and audit contracts.
2. Port Command Center worker/execution behavior behind those contracts; remove hardcoded business workflows.
3. Port Harness trajectory/evaluation packs behind the OS execution event contract.
4. Integrate n8n through authenticated, idempotent callbacks.
5. Add Claude Managed Agents behind a replaceable runtime adapter and enforce data eligibility before dispatch.
6. Add observability, budgets, lifecycle cleanup, CI gates and production hardening.
