---
name: agentic-build-loop
description: Turn a bounded engineering objective into a reviewed specification, acceptance tests, implementation plan, maker-checker cycle, and verified change.
---

# Agentic Build Loop

## Purpose
Use this procedure for non-trivial engineering changes. The agent is an implementation worker, not the owner of architecture, risk acceptance, or release authority.

## Required sequence
1. **Frame the outcome.** State the user-visible behavior, affected domains, constraints, non-goals, data classes, and rollback path.
2. **Inspect before changing.** Read the relevant modules, migrations, tests, contracts, and current repository state. Identify existing behavior to preserve.
3. **Specify acceptance.** Write observable acceptance criteria and focused regression tests before implementation. Include authorization, tenant scope, audit, idempotency and failure cases where relevant.
4. **Design the boundary.** Propose module responsibilities, data flow, API/schema contracts and migration impact. Prefer additive, backward-compatible changes.
5. **Implement narrowly.** Make the smallest coherent change. Do not expand scope or replace working architecture without evidence.
6. **Verify honestly.** Run focused tests, then the repository's required suite and static checks where available. Record exact commands, results, skips and environmental blockers.
7. **Independent check.** A checker that did not author the change reviews requirements, diff, security, migration safety, operational behavior and test evidence.
8. **Release decision.** Produce a reviewable PR. Never self-merge, deploy, alter credentials, or bypass a protected release gate.

## Stop conditions
Stop and escalate when requirements conflict, tenant boundaries are unclear, a migration may rewrite/delete data, tests cannot validate a security-sensitive change, a secret is exposed, or the requested work exceeds the authorized scope.

## Output contract
Return: specification; acceptance criteria; touched files; migration and compatibility notes; tests actually run; unverified items; risks; rollback; PR link. Never equate generated code with completed or accepted work.

## Agency OS constraints
PostgreSQL remains the source of truth. Provider runtimes do not own business state. External calls remain outside DB transactions. Use persisted executions, attempts and audit. Keep commercial/client data out of runtimes until the Data Protection Gateway and runtime eligibility checks authorize it.

## Provenance
Independently authored for Agency OS after reviewing AI-Native OS (Impact Brussels ASBL), pinned at `49f975689c9141f9bea1164f8db68ce2745943fa`. Reference concepts: agentic build discipline and loop engineering. No source text or scripts copied.
