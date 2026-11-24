---
name: independent-release-review
description: Independently assess changes using evidence, deterministic gates, security review and optional external PR review.
---

# Independent release review

Inputs: PR and exact head SHA, requirements, CI links/artifacts, migration and rollback plan, data-classification impact.

1. Verify intent and requirement traceability.
2. Read the full diff, not only generated summaries.
3. Check authentication, authorization, workspace scope and service identities.
4. Check external calls, signatures, idempotency, duplicate effects, retries and recovery.
5. Check PII/secrets in prompts, logs, traces, results and artifacts.
6. Check migrations, backfills, indexes, PostgreSQL behavior and rollback/recovery.
7. Check negative-path tests and actual CI status.
8. Check dependencies, license, lockfiles, SBOM and supply-chain changes.
9. Use a second reviewer for high-risk changes; CodeRabbit may be an additional signal after privacy/scope review.
10. Confirm the authoring agent did not self-approve or self-merge.

Failed deterministic CI blocks release. Critical/high security findings block until fixed or explicitly risk-accepted by the founder. Missing evidence is unverified, not assumed safe. This review cannot grant production approval.
