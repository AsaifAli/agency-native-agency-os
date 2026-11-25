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

The website is a separate public system. Its browser never calls the private OS and it never receives OS credentials. The signed lead-intake bridge is implemented and merged to both repositories (website PR #30 and OS endpoint); the website quality workflow passed lint, typecheck, dependency audit, structure, build, Playwright and Lighthouse. The website route validates Turnstile, payload, body size and rate limits, then sends a narrowly scoped signed request to the OS. The OS verifies timestamp, HMAC, key ID, body and idempotency; only accepted leads and a minimal provenance envelope are persisted. Existing Supabase lead inbox remains available. The bridge remains disabled pending external secrets, migrations, fixed workspace mapping, HTTPS and synthetic end-to-end validation. No auto outreach or agent execution occurs from lead intake.

## Implementation checkpoint

The workforce foundation provisions the chart with all members and capabilities inactive by default. Founder-only capability enablement and activation remain explicit operations. The orchestration layer adds founder-authorized plan creation, root/child tasks, ordered dependencies, downward direct-manager checks, a durable idempotent worker hand-off, task/delegation lifecycle synchronization, blocked-work recovery and founder review before plan completion.

The orchestration authorization hardening is merged to OS `main` as commit `387d283bfe65f470cacc9b9a2785de8fce141b78`; CI run [45481253037](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/45481253037) passed **168 backend tests, 1 warning**, PostgreSQL 16 migrations, Python compilation, frontend TypeScript checking and Next.js production build. Plan creation requires active Chief of Staff/supervisor planning authority and constrains delegation to the creator's reporting subtree; refresh remains founder-only. The current plan input is still supplied by the founder; the Chief of Staff Agent does not yet autonomously generate the plan. Machine identities for agents and recursive supervisor-generated decomposition are not implemented. No MCP tool grants or external side effects are enabled.


The Claude Chief of Staff planning-draft workflow is now integrated as a proposal-only layer: the founder queues a synthetic/public-data objective, a tool-free Managed Agents execution returns bounded JSON, and the OS persists the result for founder review. The founder must select and approve every direct-manager assignment before plan/task/delegation records are materialized in one transaction. Invalid output cannot be approved. This does not provision machine identities, MCP tools, recursive supervisor sessions or live client-data access; those remain separate security milestones.

## Agentic revenue, retainer and delivery operating patterns

The agency is AI-native: Claude-backed agents are intended to perform research, reasoning, drafting, qualification, analysis, planning, coordination and execution of allowlisted internal work. The Agency OS remains the authority plane and durable system of record. A provider session never grants permissions by itself.

### Revenue agents
- Market Research / Intelligence agents discover target accounts, research public company context, capture source references and timestamps, identify fit signals and uncertainty, and recommend prospects. They must not invent contacts, facts, consent or provenance.
- Business Development agents qualify leads, maintain CRM records, propose deduplication/merge candidates for review, map buying committees, identify service fit and recommend next actions.
- Outreach agents draft and personalize email/social/call scripts, propose cadence and follow-up timing, and summarize replies. Dispatch is a separate OS action subject to sender identity, consent/source policy, suppression, rate limits, idempotency and stop-on-reply/opt-out/bounce. Scraped contact data is not consent. Outbound dialing remains manual review until jurisdictional/provider controls are proven.
- Sales/solutions agents prepare discovery briefs, estimates, proposal drafts, assumptions, exclusions and risk notes. Pricing, proposals sent to a client, SOWs and contracts remain approval-gated.

### One-time and retainer engagements
- One-time projects have a fixed scoped deliverable, agreed milestones, acceptance criteria, change-control path, budget and completion/handover state.
- Retainers have a defined billing cadence, initial term, included service hours/allowance per period, rollover policy, response target, renewal terms and explicit service boundaries. They also need period-by-period usage, capacity, SLA/response tracking, overage/change approval, invoice reconciliation, renewal/termination notice and final handover/knowledge export.
- Auto-renewal is a proposed contract term only; it must never execute automatically without an explicit authorized policy and legal review. Retainer overages, unused-hour rollover, service credits, scope changes and renewal pricing are not inferred by an agent.
- Proposal records now distinguish one-time vs retainer terms and contract creation snapshots those terms. The current PR adds a founder-governed service-period ledger, billable usage aggregation, rollover snapshots and overage visibility. Period closeout does not authorize extra charges. Automated recurring invoice drafts, overage approval, renewal notices, termination workflow and SLA measurement remain subsequent implementation work.

### Delivery and client success agents
- Discovery agents turn conversations and documents into traceable requirements, decisions, assumptions and acceptance criteria.
- PMO agents coordinate milestones, dependencies, risks, status reports and client update drafts.
- Engineering agents implement only assigned work in isolated sandboxes; AI code requires review.
- QA/Security agents independently evaluate requirements, regression, data protection and release readiness. They can block a release recommendation but cannot approve production deployment.
- Client Success agents monitor project/retainer health, feedback, unresolved risks, usage, upcoming renewals and support requests; sensitive client communications and commercial concessions remain gated.

### Current action classifications
Research, lead qualification, outreach drafting/personalization, internal account-health assessment, retainer usage analysis, delivery QA preparation and project status summaries are eligible for autonomous internal execution after endpoint-level grants and data/budget checks. Sending outreach, outbound calls, auto-renewal, pricing, contracts, payments, production release, permission changes and destructive actions remain manual-review or founder-approval actions. The classification registry is not a tool gateway; no provider tool may bypass the OS authorization layer.
