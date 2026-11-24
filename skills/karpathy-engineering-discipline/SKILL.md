---
name: karpathy-engineering-discipline
description: Reduce coding-agent mistakes by thinking before coding, choosing simplicity, making surgical changes, and defining verifiable goals.
---
# Engineering Discipline

Apply these four principles to non-trivial engineering work.

## Think before coding
- State material assumptions and uncertainties.
- Inspect relevant code and documentation before changing anything.
- Surface contradictions and ask when ambiguity changes the implementation.
- Explain important trade-offs rather than silently choosing.

## Simplicity first
- Implement only what the request and acceptance criteria require.
- Avoid speculative abstractions, unnecessary configuration, duplicate platforms, and premature generalization.
- Prefer existing dependencies and platform features over new dependencies.

## Surgical changes
- Preserve unrelated behavior, comments, formatting, and files.
- Do not refactor unrelated code because it looks imperfect.
- Remove only dead code introduced by the current change unless cleanup is explicitly in scope.

## Goal-driven execution
- Define observable success criteria.
- Write a failing regression test for defects.
- Run deterministic checks and report evidence.
- If a check cannot run, state why; never infer success.

These principles complement, but do not replace, the Agency OS security, privacy, approval, and recovery requirements.
