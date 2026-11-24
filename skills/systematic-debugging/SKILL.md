---
name: systematic-debugging
description: Diagnose defects and regressions using reproducible evidence, competing hypotheses, instrumentation, and a regression test before changing code.
---
# Systematic Debugging

Use when behavior is failing, intermittent, slow, or inconsistent with expected state.

1. Reproduce the failure with the smallest safe input and record the exact command, request, environment, and observed result.
2. Trace the full path: caller, authorization, state transition, persistence, worker/provider boundary, and response.
3. Form at least two plausible hypotheses when the cause is not obvious. Rank them by evidence.
4. Add temporary, privacy-safe instrumentation at the boundary that distinguishes the hypotheses. Never log secrets, raw prompts, or unredacted client data.
5. Change one cause at a time. Avoid unrelated cleanup during diagnosis.
6. Add a regression test that fails before the fix and passes after it.
7. Check retries, duplicate delivery, cancellation, stale leases, and recovery if the failure crosses an asynchronous boundary.
8. Remove temporary instrumentation and verify the final diff is minimal.

Do not repeat a failing tool call without changing the hypothesis or inputs. Do not claim a root cause from correlation alone.
