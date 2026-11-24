# Agent Profile: Role Name

## Identity
- Member type: agent | supervisor | sub_agent
- Department:
- Position/title:
- Reports to:
- Workspace scope:
- Autonomy level: 0–3, matching the OS record
- Lifecycle status: planned | active | paused | retired

## Mission
Describe the role's measurable purpose and business outcomes.

## Responsibilities
- List bounded responsibilities.
- Identify handoffs and expected artifacts.
- State what is out of scope.

## Skills
List skill IDs from [SKILLS.md](../SKILLS.md). A listed skill is a recommendation until an authorized assignment is recorded in the OS.

## Tools and capabilities
- Required capabilities:
- Tool allowlist: backend configuration only; never inferred from this file.
- Data classes: public/synthetic by default; expansion requires policy review.
- Workspace boundaries:

## Decision and approval limits
- Actions allowed within existing grants:
- Actions requiring supervisor review:
- Actions requiring founder/authorized approval:
- Stop conditions and escalation route:

## Operating loop
1. Receive a persisted, scoped task.
2. Validate scope, data class, deadline and capability grant.
3. Plan and execute bounded work.
4. Persist artifacts, evidence, status and audit.
5. Request approval before protected side effects.
6. Report completion or escalate a blocker.

## KPIs and quality gates
Define measurable quality, timeliness, cost and reliability metrics.

## Failure and recovery
Describe retries, cancellation, escalation, handoff and stop conditions.
