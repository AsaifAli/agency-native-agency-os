# Revenue feature PR reconciliation — 2026-11-25

## Source branches
- PR #25: consent-governed outbound email preparation and stop controls.
- PR #26: immutable service-catalogue snapshots on proposal drafts.
- PR #28: engagement terms, source-backed lead research, outreach drafts and retainer operations.

## Integration decisions
- Retained the PR #25 governed outbound communications backend and UI at `/outreach`.
- Moved the PR #28 research and outreach-draft UI to `/research-outreach`; the two features no longer compete for the same route.
- Combined PR #26 service-offering identity/revision/pricing snapshots with PR #28 one-time and retainer engagement terms in proposal models, API schemas/routes, Founder Console and regression tests.
- Preserved the additive feature migration revisions and added merge revision `l2e8a0b6d549`, joining `h7f3a5c9d2e6`, `h7f3a5b9d261` and `k1d7f9a5c438`.
- Outbound communications remain draft/approval/internal-queue only. No provider dispatch or signed provider webhook is enabled.
- Research is source-backed record creation and founder-reviewed draft preparation; no autonomous live prospect sourcing connector is enabled.
- Retainer recurring invoice creation produces drafts only; no invoice sending, payment collection or automatic renewal is enabled.

## Validation evidence available before publication
- SQLite backend suite: 209 passed, 3 skipped (PostgreSQL-only worker/outbox concurrency and recovery cases).
- Isolated PostgreSQL worker tests: 3 passed.
- Fresh PostgreSQL migration to Alembic head `l2e8a0b6d549`: passed.
- Frontend lint, TypeScript check, Next.js production build and npm audit: passed; npm audit reported zero vulnerabilities.
- `git diff --check`: passed.
- These checks were run against the user's reconciled local working tree, not yet against the GitHub integration commit. Exact-commit remote validation remains outstanding.

## Remaining production gates
Composite tenant foreign keys, broader cross-workspace tests, signed provider webhooks, outbound dispatch, Data Protection Gateway, OS tool gateway, machine identities, session retention/deletion, observability, backup restore, SBOM and independent security review remain open. This PR is a development integration, not a production-readiness certification.
