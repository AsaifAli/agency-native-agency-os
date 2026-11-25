# Governed Agent Operating Model

**Status:** Design baseline; the loops and new skills in this document are proposed/reference assets, not enabled runtime capabilities.

## Why these references matter

The public FounderOS and AI-Native OS repositories provide useful operating patterns: stage-aware founder triage, specialist advisor perspectives, structured skills, recurring review loops, spec-first engineering, loop maturity, independent gates, connector blast-radius review and evidence-backed learning. They are not a replacement for Agency OS domain services, authorization, persistence or runtime.

## Adopted principles

1. **One OS, two engines.** Revenue and Delivery remain first-class domain workflows. No second FounderOS runtime or separate agent control plane is introduced.
2. **Skills are instructions, not authority.** A skill may describe a procedure or recommend a tool; it cannot grant a tool, data class, workspace, approval or autonomy level.
3. **Loops are durable workflows, not cron prompts.** The OS owns definitions, versions, executions, attempts, budgets, approvals, state, artifacts, audit and recovery. Schedulers and n8n are triggers/transports only.
4. **Maker-checker separation.** The agent that produces a result cannot be its sole verifier for critical work. Independent evaluation and QA are explicit gates.
5. **Founder triage, not founder bottleneck.** Chief of Staff may classify, recommend and prepare bounded plans. Assignments and protected actions still pass through OS authorization and founder approval.
6. **Learning is evidence-scoped.** Lessons cite source events and retain workspace scope; cross-workspace promotion requires review and founder approval.

## Proposed operating loops

| Loop | Trigger | Automated work | Objective gate | Hard stop / human decision |
|---|---|---|---|---|
| Market intelligence and lead research | Approved schedule or research request | Gather public evidence, normalize records, deduplicate, score and draft a research brief | Source/provenance completeness, schema validation, duplicate checks | No outreach or CRM promotion without policy and review |
| Outreach governance | Reply, opt-out, bounce, sender or queue event | Reconcile event, suppress blocked recipient, update internal queue and audit | Signature verification, event idempotency, recipient/workspace match | Stop on reply/opt-out/bounce; dispatch stays disabled until provider integration and legal review |
| Delivery quality gate | Milestone reaches review state | Trace requirements to tests, collect QA/security evidence, prepare rework tasks | Acceptance criteria, independent test/evaluation result, required evidence | No production release or client handover without required approvals |
| Founder operating review | Weekly cadence | Summarize pipeline, conversion, project health, cost, receivables, risks and blocked work | Source freshness, reconciliation and missing-data disclosure | Recommendations only; pricing, commitments, payments and policy changes need approval |
| Permission and connector review | Scheduled cadence or connector change | Inventory grants, expiry, scope drift, provider changes and audit anomalies | Every grant has owner, scope, purpose and review date | Permission changes remain founder-approved; urgent suspected compromise follows incident containment policy |

These are candidate designs only. They must not be scheduled until each has a supervised manual run, acceptance tests, independent review, budget limits and recovery evidence.

## Loop contract

Every future loop must persist:
- versioned definition and owner;
- trigger/event version and idempotency key;
- scoped inputs, data classification and provenance;
- agent/skill version and explicit tool grants;
- execution, attempts, leases, heartbeat and cancellation;
- max iterations, wall-clock deadline, concurrency and cost budget;
- independent gate, output artifact and acceptance evidence;
- retry, dead-letter, reconciliation and escalation state;
- audit events, retention and deletion linkage.

Use at-least-once delivery and idempotent handlers. External calls stay outside DB transactions. A failed audit or policy check fails closed. A loop must expose why it stopped and what needs human attention.

## Adoption sequence

1. Keep the static skill catalog disabled and tool-free.
2. Finish tenant integrity and the Data Protection Gateway before adding more execution surfaces.
3. Implement machine identity, session lifecycle and the OS Tool Gateway.
4. Add explicit skill assignment records only after assignment authorization, version pinning, expiry and audit exist.
5. Pilot one read-only loop with public/synthetic data and a measurable objective gate.
6. Add reversible writes only after idempotency and recovery tests.
7. Consider bounded autonomy only after repeated accepted runs and founder approval.

## Reference audit and provenance

Reviewed repositories at pinned revisions:
- [FounderOS](https://github.com/impactbrussels/FounderOS), `83067222c3d99b5afed2cb90c4c3dc301a4b0729` — CC-BY-4.0 content; Apache-2.0 code.
- [AI-Native OS](https://github.com/impactbrussels/AINativeOS), `49f975689c9141f9bea1164f8db68ce2745943fa` — CC-BY-4.0 content; Apache-2.0 code.

This integration adds independently authored Agency OS procedures and architectural decisions; it does not copy their skill files, scripts, workflows or assets. Attribution and license details are recorded in `skills/catalog.json`.
