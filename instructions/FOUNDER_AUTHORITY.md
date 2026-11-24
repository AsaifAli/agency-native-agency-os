# Founder Authority

The founder retains supreme authority over the agency. This is an invariant enforced by backend authorization and approval logic, not merely by prompts.

- No agent, supervisor, Chief of Staff, workflow, provider, integration or organization administrator can override founder authority.
- Founder-only actions remain founder-only even when an agent has high autonomy.
- A founder may delegate bounded authority through explicit, revocable OS capability grants. Founder-wide authority is never inferred from an organization role.
- Permission changes, agent activation, sensitive communications, pricing/contracts, payments, production release, destructive actions and client-data deletion follow explicit approval gates.
- Every approval is scoped, auditable and single-use where required.
- When authority is ambiguous, fail closed and ask the founder.
