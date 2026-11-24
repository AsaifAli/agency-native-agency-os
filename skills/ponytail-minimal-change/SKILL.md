---
name: ponytail-minimal-change
description: Minimize code and complexity by checking whether a change is needed, already solved, or supported by existing platform features before adding implementation.
---
# Minimal Change Discipline

Before adding code, climb this ladder and stop at the first option that safely solves the problem:

1. Does this behavior need to exist at all to meet the request?
2. Is it already implemented in this repository? Reuse it.
3. Can the standard library or existing dependency solve it?
4. Does the platform already provide the capability?
5. Can the change be expressed with a smaller interface or fewer moving parts?
6. Only then add the minimum new code.

After implementation:
- Fix the root cause, not only the visible symptom.
- Avoid an abstraction with one caller and one implementation unless it creates a clear security or domain boundary.
- Do not add scaffolding "for later".
- Keep the diff focused and leave a runnable check for non-trivial behavior.
- Preserve explicit security controls even when they add lines: least privilege, audit, approval, idempotency, and tenant isolation are not optional complexity.

A deliberately deferred capability must have a clear reason and a condition that would justify adding it. Do not use "minimal code" as an excuse to omit required safeguards.
