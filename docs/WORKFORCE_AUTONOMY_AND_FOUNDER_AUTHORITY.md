# Workforce autonomy and founder authority model

## Governing principle

All agents, sub-agents, supervisors, team members and departments are operational members of the founder's agency, represented as governed workforce records. The founder retains supreme authority. The workforce may act autonomously only inside explicit backend-enforced, revocable boundaries.

The org chart separates organisational structure from runtime identities:
- **Workforce unit:** office, functional group, department or team.
- **Workforce member:** human role, agent, supervisor or sub-agent.
- **Agent definition:** runtime/instruction profile stored by Agency OS.
- **Capability grant:** explicit tool/action/data/scope/budget allowlist.
- **Task/delegation:** work assignment with parent, child, assignee, dependency and review lineage.
- **Execution/session:** provider runtime activity; never the source of business authority or organisational truth.

One Claude supervisor can coordinate many agent definitions. The OS does not need a separate always-on model session per seat. Roles remain distinct even where a single runtime agent temporarily performs work across a small team.

## Reporting and founder authority

Founder / CEO is the supreme authority and is not an autonomous workforce member. Chief of Staff / Claude Agency Supervisor coordinates the workforce and reports directly to the founder. Five functional groups report through the Chief of Staff; each of the sixteen department heads reports to the Chief of Staff. The department specialist reports to its department head. Teams and sub-agents report to their explicit manager. QA/Security remains independent of Engineering for release review; Finance and Legal retain independent escalation paths.

No runtime role can create or modify its own capability grant, change its own autonomy level, enable itself, rewrite founder authority, approve a protected action, delegate to the founder, or bypass a review gate.

## Autonomy model

| Level | Allowed operating pattern |
|---:|---|
| 0 | Observe and report only |
| 1 | Prepare drafts, research, plans and recommendations |
| 2 | Execute allowlisted internal tasks and delegate within the reporting tree |
| 3 | Execute pre-authorized routine external actions only after sender, consent, suppression, rate, idempotency and stop checks are implemented |

Level 4 is deliberately not an agent autonomy level. It is reserved for founder decisions such as pricing, contracts, payments, sensitive external communication, production release, destructive actions, permission changes and client-data deletion.

New workforce members, department agents and capabilities are provisioned disabled/planned. Activation is a separate founder-controlled step after identity, policy, data classification, tools, budgets, testing and recovery are configured.

## Website boundary

The website is a separate public system. Its browser never calls the private OS and it never receives OS credentials. A website server route validates Turnstile, payload, origin, body size and website rate limits, then sends a narrowly scoped signed request to the OS. The OS verifies timestamp, HMAC, key ID, body hash and idempotency; only accepted leads and a minimal provenance envelope are persisted. Existing Supabase lead inbox remains available. No auto outreach or agent execution occurs from lead intake.

## Implementation checkpoint

The workforce foundation provisions the chart with all members and capabilities inactive by default. Founder-only capability enablement and activation remain explicit operations. The orchestration layer adds founder-authorized plan creation, root/child tasks, ordered dependencies, downward direct-manager checks, a durable idempotent worker hand-off, task/delegation lifecycle synchronization, blocked-work recovery and founder review before plan completion.

The backend orchestration implementation passed CI with 168 tests and one existing deprecation warning on commit `a3f3784e8fb5a75efb8212c0de0002b7a741cec5` (run [45477077236](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/45477077236)). The current plan input is still supplied by the founder; the Chief of Staff Agent does not yet autonomously generate the plan. Machine identities for agents and recursive supervisor-generated decomposition are not implemented. No MCP tool grants or external side effects are enabled. The Founder Console production build has not yet been verified.
