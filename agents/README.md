# Agent Profiles

Agent profiles are human-readable role definitions. They do not provision runtime identities or grant tools.

Create one Markdown file per role using [AGENT_TEMPLATE.md](AGENT_TEMPLATE.md). The OS database remains authoritative for identity, manager relationship, workspace scope, status, autonomy and capability grants.

## Initial leadership profiles
- [Chief of Staff](CHIEF_OF_STAFF.md)
- [Department Supervisor](DEPARTMENT_SUPERVISOR.md)
- [Specialist Agent](SPECIALIST_AGENT.md)

Add department-specific profiles as workflows, acceptance criteria and authorization policies are implemented.

## Department charters

See [departments/README.md](departments/README.md) for the 16 department charters aligned with the agency organization blueprint.


## Claude specialist source catalogue

The curated specialist definitions in [specialists/catalog.py](specialists/catalog.py) are reserved source material for the future Claude runtime adapter. They describe specialist missions, responsibilities, inputs, outputs, boundaries and review expectations. They are not executable agents and do not provision runtime identities or grant tools.

The Agency OS stores only stable specialist keys, department association, profile references, runtime ownership and governance status. It owns task plans, permissions, approvals, budgets, execution records and audit. Claude will own detailed prompts, skills, reasoning, collaboration and delegation when that adapter is implemented. All Claude tool access must pass through the OS Tool Gateway/MCP boundary.
