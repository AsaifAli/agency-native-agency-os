# Agency OS repository manifest

This manifest describes the current native Agency OS repository, not a standalone Command Center or Evaluation Harness bundle.

## Core runtime
- `app/`: FastAPI modular monolith, domain services, Founder Authority, autonomy/action policy, workforce, execution lifecycle, provider adapters, transactional outbox and deterministic evaluation.
- `app/evaluation/`: native RAG and agent-workflow evaluation packs and metrics.
- `app/worker/`: durable execution worker and runtime factory.
- `frontend/`: Next.js private Founder Console.
- `migrations/`: additive Alembic schema history. Do not rewrite or delete applied migrations.
- `tests/`: backend, API, policy, workforce, runtime, worker, evaluation and PostgreSQL integration tests.
- `docs/`: product scope, architecture, security, workforce, delivery, integrations and operational evidence.
- `skills/`: reviewed internal task playbooks.

## External boundaries
- PostgreSQL is the business source of truth; Redis is non-authoritative queue/cache infrastructure.
- Claude Managed Agents is an opt-in runtime adapter, not the system of record.
- The public website remains separate and uses the signed, idempotent lead-intake API when explicitly configured.
- EvidenceFlow, QuoteSense, LegacyLens and WebQA Intelligence remain separate applications.

## Removed from the runtime repository
The old `integrations/command_center_source/` and `integrations/evaluation_harness_source/` snapshots, standalone Harness server/dashboard/plugin/MLOps/n8n workflow content and unused legacy HTTP adapters are not part of the native OS runtime. Required evaluation primitives now live in `app/evaluation/`; Command Center execution/workforce capabilities are implemented through native OS services.

## Verification
See `IMPLEMENTATION_STATUS.md` for tested checkpoints, current gaps and what remains unverified. A passing backend CI run does not prove production readiness, provider configuration, frontend build, backup restore, penetration testing or compliance.
