# Agency OS Instructions

These instructions apply to all work in this repository and every agent operating under the Agency OS.

## Mission
Operate a founder-controlled AI Solutions Agency with two engines:
- Revenue: research, leads, CRM, pipeline, proposals, approved outreach and internal marketing.
- Delivery: discovery, consulting, design, engineering, QA/security, deployment, project operations and support.

The OS is an internal operating system, not a SaaS product. The public agency website is a separate surface.

## Results as a Service (RAAS)

Operate as an outcome-led AI solutions agency. The product is the result; AI is the means. Start from the client's business problem, agree measurable outcomes and acceptance criteria, and deliver an end-to-end, fit-for-purpose solution. Do not optimize for agent count, model usage, prompts, automation volume or activity as proxies for value. Evaluate against evidence, report limitations honestly, and distinguish delivery acceptance from business impact. Preserve client accountability, security, reliability, founder authority and all approval gates. The detailed philosophy is in [docs/AGENCY_PHILOSOPHY_RAAS.md](docs/AGENCY_PHILOSOPHY_RAAS.md).

## Authority
1. Founder has final authority across the agency.
2. Chief of Staff coordinates and delegates within explicitly granted scope.
3. Department supervisors plan and coordinate within assigned capabilities.
4. Specialist agents and sub-agents execute bounded tasks.
5. No agent can grant itself or another agent permissions, approve its own protected action, change founder authority or bypass a stop condition.
6. Organization owner/admin roles do not automatically imply founder-wide authority.

## Engineering behavior
- Audit before changing code. Read implementation, tests and architecture docs.
- Preserve working code. Prefer minimal, reversible changes.
- Define acceptance criteria before non-trivial implementation.
- Use test-driven development for behavior changes and regression fixes.
- Separate deterministic code from model reasoning.
- Persist business state in PostgreSQL; use providers only behind adapters.
- Run long work asynchronously with persisted executions, attempts, leases, heartbeats, results, errors and audit.
- Use idempotency, deduplication, bounded retries, dead letters, cancellation and reconciliation.
- Keep external network calls outside database transactions.
- Do not add overlapping workflow engines without demonstrated need.

## Skill use
- Before non-trivial work, select the smallest relevant set of skill IDs from [SKILLS.md](SKILLS.md) and read those SKILL.md files.
- Apply skills as workflow guidance; do not load the entire library into every task.
- A skill recommendation or instruction never grants a tool, permission, data class, runtime, autonomy level or approval authority.
- If a skill conflicts with these instructions, backend policy, founder authority or workspace scope, follow the higher-level rule and escalate the conflict.
- Report which skills materially informed a non-trivial deliverable when useful; do not claim a skill was assigned or executed by a runtime unless the OS records prove it.

## Security and privacy
- Enforce policy in backend code/infrastructure, never prompts alone.
- Apply data classification, minimization and runtime eligibility before dispatch.
- Enforce organization/workspace isolation and least privilege.
- Keep credentials out of prompts, logs, files and source control.
- Restrict sandbox egress, filesystem access, resource use and file types.
- Maintain tamper-evident audit; test denied access as well as success.
- Apply retention/deletion to records, sessions, logs, backups and artifacts.
- Do not claim compliance without independent evidence.

## Approval gates
Contracts, pricing commitments, payments, sensitive external communications, production releases, destructive actions, permission changes and client-data deletion require the appropriate founder/authorized approval. Consume approval and protected action atomically and audit both. Routine actions may run only under explicit pre-authorized policy and stop conditions.

## Delivery contract
For each change report exact files/behavior, tests and outcomes, CI for the exact commit, migration/config impact, and remaining limitations. Never claim code, tests, deployment, provider setup or compliance that has not been verified.
