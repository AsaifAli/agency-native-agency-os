---
name: research-first-change
description: Use before changing Agency OS code or integrations. Research contracts, plan the smallest safe change, test, independently review and verify evidence.
---

# Research-first engineering change

1. Inspect branch, working tree, architecture decisions, implementation status and tests.
2. Trace API, model, service, permission and event contracts; reuse rather than duplicate state.
3. Record objective, affected paths, trust boundaries, migration impact, failure modes and acceptance tests.
4. Prefer the smallest reversible implementation.
5. Add/update tests first for security-sensitive changes and bug fixes.
6. Implement deterministic logic in code; model reasoning does not authorize side effects.
7. Check tenant/workspace scope, data classification, idempotency, retries, audit, cost and cancellation.
8. Run applicable lint/type checks, focused/full tests, migrations and builds.
9. Review the full diff independently; resolve critical/high findings or record explicit founder risk acceptance.
10. Verify exact branch, commit and CI before updating status.

Never execute scripts copied from skills before review. Never add dependencies without need, license/security review, pin strategy and removal path. Never bypass approvals by switching tools/providers. Never reset data or change founder permissions without authorization and a recovery plan.

Report changed paths, exact test results, security impact, limitations and rollback.
