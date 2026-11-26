# Agency Operating Capability Map

**Source:** `ai-engineering-studio-brain-report.md` (2026-11-25)
**Purpose:** Translate the studio's documented operating model into an OS-owned capability catalogue. This is a planning and governance map, not evidence that the listed skills are implemented.

## Operating model

The studio is independent and founder-led. Discovery, architecture, engineering and approval remain founder-led responsibilities. The OS should reduce repetitive coordination and artifact work while preserving explicit founder authority.

The source reports **8 departments, 22 teams and 66 skills switched on**, but it names only the department-level skill groupings below. It does not enumerate all 22 teams or 66 individual skill definitions. Do not invent those missing records; import them only when their definitions, owners, inputs, outputs and permissions are available.

## Department and capability taxonomy

| Department | Source-listed capability groups |
|---|---|
| Sales | Targeting & Scoring; Outreach |
| Deals | Reply Handling; Call Cycle; Deal Artifacts; Pipeline Ops |
| Marketing | Insights; Creation |
| Growth | SEO; Conversion; Email & Launch; Paid & Social |
| Operations | Onboarding; Client Comms; Knowledge |
| Customer | Success; Community |
| Finance | Money In; Margin |
| Leadership | Board of Advisors; Running Your Week; Hand Work to Agents |

These are capability groups/skill families, not necessarily teams, agents or executable workflows. Keep the following entities distinct in the OS: department, team, position, human/agent member, capability, skill version, tool, workflow, task, execution and session.

## Initial priority from the source

### 1. Sales and outreach
- Cold Outreach Sequences
- Proof Library Upkeep

Expected OS support: source-backed target/research records, approved sender identity, consent and suppression checks, reviewed message drafts, delivery event history, reply/bounce/opt-out stop conditions, and audit. No skill may send merely because it generated a draft.

### 2. Deals and deal artifacts
- Proposals & Scopes
- Services Agreements

Expected OS support: versioned proposal/scope artifacts linked to the opportunity, service catalogue revision, assumptions, exclusions, deliverables, acceptance criteria, pricing approvals and agreement review. Contractual commitments and pricing remain approval-gated.

### 3. Deals and call cycle
- Call Prep & Debrief
- Post-Call Follow-Up

Expected OS support: opportunity-linked call brief, authorized notes/transcript, structured outcomes, decisions, risks, action items and founder-reviewed follow-up draft. Recording/transcription requires applicable consent and retention controls.

## Cross-functional capabilities to stage after the first three

- Marketing: Insights, Creation
- Growth: SEO, Conversion, Email & Launch, Paid & Social
- Operations: Onboarding, Client Comms, Knowledge
- Customer: Success, Community
- Finance: Money In, Margin
- Leadership: Board of Advisors, Running Your Week, Hand Work to Agents
- Deals: Reply Handling and Pipeline Ops
- Sales: Targeting & Scoring

These should become governed capability definitions and OS workflows only when their operating procedures and acceptance criteria are specified. Do not activate autonomous actions by default.

## Capability contract

Every capability/skill version should eventually declare:
- Stable capability ID, department/team association and accountable owner.
- Version, lifecycle state (draft, reviewed, active, disabled, retired) and change history.
- Purpose, trigger, required inputs, output schema and completion/acceptance criteria.
- Allowed data classes, workspace scope, tools/actions and required permissions.
- Runtime eligibility/provider adapter, timeout, concurrency and budget limits.
- Human approval requirements, prohibited actions and stop/escalation conditions.
- Idempotency strategy, execution records, audit events and recovery behavior.
- Evaluation cases and release evidence.

The Agent Registry owns agent identity, runtime, grants, budgets, versions and rollback. The capability catalogue owns reusable skill definitions. Tasks and executions are persisted by the OS. Claude Managed Agents/Agent SDK may execute selected reasoning tasks behind the runtime adapter; Claude/MCP must not become the source of truth or authorization layer.

## Founder-led operating loop

1. Capture enquiry and source evidence.
2. Qualify and prepare a discovery brief.
3. Founder leads discovery and confirms constraints/access.
4. Draft scope, proposal and agreement artifacts.
5. Obtain approval for pricing, commitments and sensitive communications.
6. Create delivery project with requirements, milestones, budget and acceptance criteria.
7. Build a bounded pilot; run engineering review, independent QA and evaluation.
8. Obtain acceptance; produce handover and support plan.
9. Reconcile invoice/payment and project cost/margin.
10. Capture reviewed lessons into the proof library and capability/evaluation backlog.

## Open discovery items (explicitly not recorded in source)

- Which workflow prospects most commonly bring first: document intelligence, knowledge search or automation?
- What are the current pilot acceptance criteria and proof points for each flagship build?
- Which internal systems currently hold CRM, invoices and project records?
- The source says volume and hours are not recorded; do not estimate workload or ROI from this report.

## Current implementation boundary

The current OS tool registry has only a health-read tool and a source-backed public lead-research draft capture tool. Therefore, this map is a **planned capability taxonomy**, not a claim that the 8 departments, 22 teams or 66 skills are implemented. Implement in increments, with synthetic-data tests first and evidence recorded against the master production-readiness checklist.
