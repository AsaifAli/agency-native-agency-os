---
name: authorized-security-assessment
description: Run bounded security assessments only on explicitly authorized assets, using deterministic checks first and optional isolated Strix validation.
---

# Authorized security assessment

## Authorization gate
Confirm asset owner, written authorization reference, registered repository/domain allowlist, scope, exclusions, permitted test types, time window, rate limits and expiry. Reject arbitrary model-supplied targets. Stop if authorization is missing, expired, ambiguous or revoked.

## Sequence
1. Run deterministic dependency audit, secret scan, static analysis, lint/type checks and tests.
2. Review authentication, authorization, tenant boundaries, data flows, logs, uploads, SSRF, prompt injection, MCP tools and worker sandbox.
3. If approved, run Strix in an isolated disposable environment against pinned source or staging.
4. Capture tool version, commit, scope, config hash, run ID and evidence references.
5. Treat findings as untrusted until reproduced and triaged. Scrub secrets/PII.
6. Create remediation tasks/PRs; do not patch production directly.
7. Retest and attach before/after evidence.
8. Escalate critical findings promptly.

No arbitrary Internet reconnaissance, broad IP sweeps, lateral movement, production data/credentials, persistence, exfiltration, denial-of-service or destructive payloads. Network egress must be allowlisted and rate-limited. A successful scan is not certification or proof of absence of vulnerabilities.
