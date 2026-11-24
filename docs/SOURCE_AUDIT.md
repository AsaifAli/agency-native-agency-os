# Uploaded source audit

## Archives received

- `ai-automation-command-center-render-ready.zip`
- `ai-engineering-automation-hub-full.zip`

Both archives were extracted for inspection. The initial unified repository contained cleaned source snapshots; `.git`, `.env`, virtual environments, local databases, caches and secret artifacts were deliberately excluded. This document records the historical source review; the snapshots have since been removed after the active OS capabilities were migrated.

## Command Center findings

Reusable strengths:
- FastAPI API and typed request/response schemas.
- Agent/workflow implementations, async worker patterns and Redis/RQ integration.
- Provider integration boundary and configurable LLM calls.
- Existing tests for API, agents and role-based access.
- Telemetry, deployment and security documentation.

Gaps against Agency OS requirements:
- LangGraph may be used only for bounded agent reasoning where justified. No external workflow engine owns business process state; native OS services and durable workers are the initial approach.
- Existing role/API-key model is not sufficient for organization and tenant isolation.
- Existing run and approval concepts need canonical OS task/session/approval records.
- Existing app does not provide the complete Agent Registry, client, budget, permissions and founder governance domain.
- Existing demo deployment configuration is not a production deployment baseline.

Test evidence:
- Command Center pytest collection was attempted from the extracted source.
- Collection is blocked in this environment because `redis` is not installed (`ModuleNotFoundError`). No Command Center test pass is claimed. The Agency OS starter foundation suite separately passed: **7 passed**.

## Evaluation Harness findings

Reusable strengths:
- Shared `AgentRun`/trajectory concepts.
- Evaluation packs and deterministic metrics, quality gates and regression baselines.
- Judge abstraction, plugin/adapter contracts, prompt/model lineage and experiment tracking.
- Legacy workflow JSON exports retained as migration references only; they are not an enabled runtime dependency.
- API, security, evaluation, harness, plugin and target tests.

Gaps against Agency OS requirements:
- Existing persistence uses a lightweight SQLite/PostgreSQL compatibility layer and requires migration to OS-owned schemas and tenant-scoped records.
- API key authentication is not a replacement for OS user/service identity and scoped authorization.
- Existing target registry includes portfolio-specific projects outside Agency OS scope; those dependencies must be removed.
- Harness is to become a service integrated by API, not another orchestrator or separate business control plane.
- Client data, secrets, artifacts and execution traces require classification, retention and tenant-aware lifecycle controls.

Test evidence:
- Original Evaluation Harness test suite (before out-of-scope portfolio target files were excluded): **37 passed** in the extracted environment. The retained generic subset is revalidated separately during migration.
- After removing the portfolio-specific target API and target tests from the integration snapshot, the retained generic evaluation subset also passed: **6 passed**. These validate only the retained generic primitives; they do not validate integration, production readiness, tenant isolation or compliance.

## Security hygiene observations

The uploaded archives contained local `.env` files and secret-like artifacts. These were not copied into the unified repository and their values are intentionally not reproduced here. Treat any real credentials that were present in the archives as potentially exposed: rotate/revoke them, review provider and service logs, and use a secrets manager for future deployment. A clean `.env.example` is provided instead.

## Overall conclusion

Both repositories contain useful implementation assets, but neither is the finished Agency OS. The correct path is a controlled migration into the OS domain model and security boundary—not a blind file merge. See `FINAL_SCOPE_AND_ACCEPTANCE.md` and `ARCHITECTURE_DECISIONS.md` for the frozen target. The integration snapshots were used as migration inputs and have now been removed from the runtime repository. The native implementation and current limitations are documented in `docs/INTEGRATION_MAP.md` and `IMPLEMENTATION_STATUS.md`.
