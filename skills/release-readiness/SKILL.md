---
name: release-readiness
description: Verify a change through deterministic checks, independent review, security gates, migration safety, and founder-controlled release approval.
---
# Release Readiness

Use before merging or deploying non-trivial changes.

1. Confirm the requested scope and identify the exact base/head commits.
2. Inspect the complete diff for unrelated changes, secrets, generated files, license obligations, and migration impact.
3. Run focused tests, full relevant suites, lint/type checks, dependency/security scans, migration upgrade checks, and production build as applicable.
4. Verify authorization denials, tenant/workspace boundaries, data-class restrictions, idempotency, retry/recovery, and audit for affected flows.
5. Obtain independent review. Resolve all blocker findings with evidence.
6. Confirm CI is green on the exact commit being proposed—not merely on a nearby branch or earlier revision.
7. For migrations, document forward and rollback/recovery behavior. Never reset or delete persistent data to make a test pass.
8. Confirm secrets/configuration are external and environment-specific. Do not deploy or activate external side effects as part of a code-only merge.
9. Present remaining unverified items plainly.
10. Protected releases, production changes, permission changes, destructive actions, and client-data deletion require explicit founder approval.

A green test suite is evidence for the tested scope, not proof of overall security or production readiness.
