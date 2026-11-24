# External feature discovery and adoption decisions

**Reviewed:** 24 November 2026  
**Purpose:** Identify proven capabilities that can improve the founder-controlled Agency OS without turning it into a SaaS platform or creating overlapping infrastructure.

This is a design and source-discovery review. A product appearing here does not mean it is installed, connected, licensed, configured or approved for client data.

## Existing baseline to preserve

The OS already owns the organization/workspace model, task and execution records, worker leases and retries, PostgreSQL transactional outbox, founder approvals, audit events, runtime adapters and evaluation foundations. The immediate implementation gap was visibility: the backend persisted execution records and lifecycle audit events, while the Founder Console's Processes and Monitoring pages were placeholders.

## Feature candidates

| Capability | Reference | Useful patterns | Decision |
|---|---|---|---|
| Stateful agent orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) | Explicit supervisor graphs, specialist handoffs, parallel branches, resumable state and human checkpoints | Adopt the orchestration patterns; implement behind an OS-owned workflow contract before choosing a runtime |
| Durable execution | [Temporal](https://github.com/temporalio/temporal) | Durable waits/signals, workflow recovery, retries, long-running approvals and child workflows | Evaluate only if native workers demonstrably fail acceptance tests; do not add alongside the current worker/outbox yet |
| Agent observability and evals | [Langfuse](https://github.com/langfuse/langfuse) | Traces, token/cost/latency tracking, prompt/version lineage, datasets and evaluation feedback | Adopt trace/evaluation concepts; keep OS execution and audit records authoritative. Evaluate self-hosted integration after privacy/retention review |
| LLM tracing and experiments | [Arize Phoenix](https://github.com/Arize-ai/phoenix) | OpenTelemetry-based traces, prompt/model experiments and evaluator traces | Alternative to Langfuse, not an additional platform. Compare operational footprint before selection |
| MCP server isolation and governance | [ToolHive](https://github.com/stacklok/toolhive) | Container isolation, identity-aware access, approved catalog, server lifecycle and observability | Evaluate when OS MCP servers are implemented; require scoped credentials and egress policy |
| Static analysis and security checks | [Semgrep](https://github.com/semgrep/semgrep) | SAST and code policy checks integrated into CI | Add deterministic CI checks using reviewed rules and pinned versions; no automatic remediation |
| Coding agent sandbox | [OpenHands](https://github.com/All-Hands-AI/OpenHands) | Isolated coding workspaces, tool/runtime adapters and controlled engineering tasks | Optional engineering workbench only; never grant production credentials or unreviewed repository write access |
| Workflow orchestration | [Prefect](https://github.com/PrefectHQ/prefect) | Retryable data/automation flows, schedules and concurrency controls | Do not add: overlaps native workers/outbox and n8n's integration role |
| Error monitoring | [Sentry](https://github.com/getsentry/sentry) | Exception grouping, release tracking and alerting | Candidate for later operations hardening; first establish redaction, retention and self-hosting requirements |
| Agent and tool catalog | [MCP Registry / ToolHive Catalog](https://github.com/stacklok/toolhive-catalog) | Curated, versioned server metadata and provenance | Adopt catalog/provenance concepts; external entries remain untrusted until review |

## More patterns worth implementing in the OS itself

1. **Supervisor and specialist delegation:** represent the supervisor's plan as persisted parent/child tasks, explicit dependencies, ownership, review state and escalation. The supervisor may propose and delegate; it cannot approve protected actions.
2. **Execution trace timeline:** expose lifecycle events, attempts, retries and terminal outcomes from OS-owned records. Never store raw prompts, provider secrets or unredacted customer content in trace metadata.
3. **Skill supply-chain governance:** every skill has source URL, license, pinned commit/version, content hash, reviewer, allowed tools/data classes, test status and enablement state. Skills from public hubs are untrusted input.
4. **MCP admission and invocation policy:** register approved server versions and tool schemas; enforce identity, workspace scope, tool/parameter allowlists, timeouts, egress and audit at the backend boundary.
5. **Evaluation release gate:** version datasets, prompts, models and evaluator configurations; block release on failed safety, tenant-isolation, regression or quality checks.
6. **Engineering change protocol:** research → plan → implementation → deterministic tests → independent review → security scan → founder-controlled release.
7. **Operational recovery controls:** dead-letter review, replay with idempotency, stuck lease detection, worker health, reconciliation and restore drills.

## Adoption guardrails

- Prefer one implementation per responsibility. Do not run LangGraph, Temporal, Prefect and n8n as competing orchestrators.
- Keep PostgreSQL as the source of truth for business state, permissions, approvals, execution state and audit.
- External agents and integrations call authenticated OS APIs; they never write core tables.
- No skill, MCP server, agent or code scanner receives broad workspace or production access by default.
- Use synthetic/public data until identity, tenant isolation, data classification, retention, deletion and runtime eligibility are verified.
- Security scanners report findings; remediation is a reviewed code change. No auto-merge or autonomous production patching.
- Any external integration needs an owner, purpose, threat model, data-flow review, cost cap, permission scope, recovery path and removal plan.

## Evidence and limits

- [LangGraph documentation](https://www.langchain.com/langgraph) describes stateful agent orchestration and human-in-the-loop control.
- [Temporal's LangGraph durable-execution integration](https://temporal.io/blog/temporal-langgraph-plugin-durable-execution) describes durable recovery and waits; it is vendor-authored evidence and not proof that this OS needs Temporal.
- [Langfuse repository](https://github.com/langfuse/langfuse) describes self-hosting, tracing, evaluation and cost/usage observability.
- [Arize Phoenix repository](https://github.com/Arize-ai/phoenix) describes OpenTelemetry-based tracing and experiments.
- [ToolHive repository](https://github.com/stacklok/toolhive) describes isolated MCP server execution and identity-aware policy.
- [Semgrep repository](https://github.com/semgrep/semgrep) describes static analysis and security scanning.
- [OpenHands repository](https://github.com/All-Hands-AI/OpenHands) describes a self-hosted coding-agent runtime and sandboxed execution.

Licenses, current maturity, security posture, hosting cost and contractual terms must be checked against the exact versions selected before adoption.
