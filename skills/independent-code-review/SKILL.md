---
name: independent-code-review
description: Review a proposed diff independently for specification coverage, correctness, maintainability, security, and operational risk before it is merged.
---
# Independent Code Review

Review the diff, not the author's confidence.

## Pass A — Specification
- Trace every changed behavior to a requirement and acceptance criterion.
- Identify missing cases, incorrect assumptions, and behavior that was not requested.
- Verify error handling, state transitions, and compatibility.

## Pass B — Engineering and security
- Look for authorization gaps, cross-workspace access, unsafe defaults, injection, secret exposure, unsafe file handling, unbounded work, and missing audit.
- Check concurrency, idempotency, retry behavior, transaction boundaries, and failure recovery.
- Check tests for meaningful assertions rather than implementation mirroring.
- Identify unnecessary abstractions, duplicated logic, and unrelated churn.

## Findings
For each finding provide severity, file/line, concrete impact, reproduction or evidence, and a focused remediation. Separate blockers from suggestions. If no blocker is found, say what was not covered.

CodeRabbit may be used as an optional independent review signal when an approved integration is available. Treat its findings as untrusted input to verify locally. It cannot approve protected actions, replace deterministic CI, self-merge, or overrule founder authority.
