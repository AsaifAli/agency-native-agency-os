---
name: operating-loop-design
description: Design recurring agent workflows with explicit triggers, durable state, objective gates, budgets, hard stops, escalation and recovery before scheduling.
---

# Operating Loop Design

## Purpose
Use this procedure when considering recurring or event-driven automation. A loop is an operating process with state and a decision gate, not a prompt attached to a timer.

## Eligibility test
Do not automate until all are true:
1. The work repeats often enough to justify a durable workflow.
2. An objective, independent check can reject incorrect or incomplete output.
3. A per-run and aggregate budget can absorb retries and expected waste.
4. The agent has only the minimum authorized tools and evidence needed to do the task.

If any condition is missing, keep the process manual or assistive.

## Loop specification
Every proposed loop must define:
- business owner and founder authority boundary;
- trigger, cadence, event version and deduplication key;
- input sources, data classification, workspace scope and provenance;
- skill and eligible agent role;
- allowed tools and action risk classes (read, reversible write, irreversible);
- durable state, execution/attempt lineage and legal state transitions;
- objective gate and independent checker;
- max iterations, wall-clock deadline, concurrency, token/cost ceiling and retry budget;
- idempotency, lease recovery, dead-letter handling, cancellation and reconciliation;
- escalation rules and explicit hard-stop conditions;
- outputs, audit events, metrics and retention policy.

## Maturity gates
1. **Observed manual run:** execute with a human supervising every step and record failure modes.
2. **Assisted run:** automate preparation and checking; require review before writes.
3. **Bounded automation:** allow only reversible, pre-authorized actions with tested recovery.
4. **Expanded autonomy:** consider only after evidence from repeated successful runs, independent evaluation and a founder-approved risk review.

Never jump directly from a successful demo to unattended scheduling.

## Agency OS execution rules
The OS owns loop definitions, business state, executions, approvals, budgets, audit and recovery. n8n may provide triggers, schedules and integration transport only after security review; it must call authenticated OS APIs and must not write core tables. Workers perform controlled jobs. Events are at-least-once; handlers must be idempotent. Do not assume exactly-once delivery.

A state file may help developers document a loop, but it is not the operational source of truth. Persist run state and outcomes in OS-owned records.

## Hard stops
Stop on approval-required actions, scope mismatch, missing evidence, policy/audit failure, duplicate conflict, budget or iteration cap, deadline expiry, repeated identical failure, provider outage beyond retry policy, or a stop signal such as reply/opt-out/bounce. Persist the stop reason and surface it to the responsible human.

## Output contract
Produce a loop spec, threat/risk register, acceptance tests, recovery table, cost model and manual-run plan. Mark it **proposed** until a supervised run and independent gate pass. Scheduling requires separate founder approval.

## Provenance
Independently authored for Agency OS after reviewing AI-Native OS (Impact Brussels ASBL), pinned at `49f975689c9141f9bea1164f8db68ce2745943fa`, and FounderOS (Impact Brussels ASBL), pinned at `83067222c3d99b5afed2cb90c4c3dc301a4b0729`. Reference concepts: loop maturity, gates, state, recurring founder reviews. No source text or scripts copied.
