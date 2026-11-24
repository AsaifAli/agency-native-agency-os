---
name: grill-before-building
description: Clarify the user's outcome, constraints, domain language, and acceptance criteria before non-trivial design or implementation work.
---
# Grill Before Building

Use for ambiguous, multi-step, architectural, or high-impact work. Do not turn a clear one-line request into an interview.

1. Restate the desired outcome in domain language.
2. Inspect the existing implementation and relevant project decisions before proposing changes.
3. Identify assumptions, unknowns, constraints, affected modules, and irreversible decisions.
4. Ask only questions whose answers would materially change the design. Prefer one focused question at a time.
5. For each viable approach, state the trade-off and recommend the smallest option that satisfies the acceptance criteria.
6. Convert the agreed outcome into observable acceptance criteria and a bounded implementation plan.
7. Preserve existing working behavior unless evidence shows it conflicts with the request.

For the Agency OS, keep founder authority, workspace isolation, approval gates, data eligibility, auditability, and recovery as design constraints. Never treat an agent's proposed plan as authorization to execute protected actions.

Output: outcome, assumptions, unresolved decisions, acceptance criteria, and next action.
