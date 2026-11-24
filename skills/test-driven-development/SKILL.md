---
name: test-driven-development
description: Implement or change behavior through a focused red-green-refactor loop with regression tests and deterministic verification.
---
# Test-Driven Development

Use for bug fixes, business rules, API behavior, state transitions, and non-trivial refactors.

1. Read the relevant implementation and existing tests. Identify the narrowest behavior boundary.
2. Write or adapt a test that expresses the required behavior and fails for the current defect.
3. Run that test alone and confirm it fails for the expected reason—not because the test harness is broken.
4. Implement the smallest change that makes the test pass.
5. Run the focused test, then the relevant module suite.
6. Refactor only while the tests remain green. Do not introduce speculative abstractions.
7. Run the repository's required lint, type, migration, security, and build checks for the affected layer.
8. Report the exact commands and outcomes. Distinguish tests run locally from CI checks.

Agency OS requirements:
- Test authorization failures as carefully as success paths.
- Include organization/workspace boundary cases and idempotent retries where applicable.
- Never use production credentials or real client data in tests.
- Do not weaken or delete a failing test merely to obtain a green run.
- A passing unit test does not prove provider integration, tenant isolation, or production readiness.
