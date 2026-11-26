# Feature Discovery Adoption Plan

**Source:** `docs/FEATURE_DISCOVERY_AND_ADOPTION.md` (reviewed 24 November 2026)  
**Code snapshot audited:** `feat/agency-os-consolidation` at `ad3e9879eb0f1c834f8abe1c8103884bd5563c7d`  
**Purpose:** Convert the discovery recommendations into a staged, evidence-based adoption plan. This is not a claim that candidate integrations are installed or production-ready.

## Decision summary

Adopt the useful architectural patterns in the Agency OS. Do not add overlapping orchestration engines or external services until a measurable gap justifies them. PostgreSQL remains authoritative for business state, authorization, approvals, executions and audit. Provider runtimes and integration services remain replaceable adapters.

## Existing implementation found in the audited branch

| Discovery recommendation | Existing foundation | Remaining gap |
|---|---|---|
| Supervisor/specialist delegation | Workforce hierarchy, founder-authorized plan drafts, parent/child task plans, dependency scheduling, delegation lineage and founder review | Recursive AI decomposition, dynamic replanning/escalation, distinct per-agent machine identities and live provider-backed delegation remain incomplete |
| Execution trace timeline | Workspace-authorized trace API; Workflows page displays execution lifecycle audit events, attempts and pause/resume/stop controls | Trace is lifecycle/audit-oriented; no provider spans, token/cost/latency telemetry or distributed trace correlation |
| Skill supply-chain governance | 18 curated skills; source repository/revision/license/use; reviewed status; disabled defaults; empty tool grants; public/synthetic-only data; SHA-256 content digest | No persisted reviewer identity/time, scanner evidence, test/evaluation evidence or signed admission record; digest is computed at read time |
| MCP admission/governance | Tool registry and action policy foundations; Managed Agents adapter rejects provider-side tools/MCP/skills/multi-agent configuration | OS MCP gateway, server admission/version lifecycle, invocation proxy, per-tool identity/scope enforcement and egress isolation are not implemented |
| Evaluation release gate | First-party evaluation packs, metrics, persisted evaluation runs and quality thresholds | No complete versioned release manifest binding dataset, prompt, model, evaluator and policy versions; no demonstrated deployment/release blocker wired to those records |
| Engineering change protocol | CI validates migrations, backend tests, PostgreSQL integration, Python compilation and frontend build; reviewed engineering/release skills exist | Independent review/security-scan evidence is not yet a first-class release record; founder-controlled release evidence needs consolidation |
| Operational recovery controls | Execution leases/heartbeats/retries/recovery; outbox leases/retries/dead-letter/reconciliation; outbox health API | Operations UI does not yet surface outbox health/dead letters; no safe replay/re-drive workflow; actual process-kill/restart and long-handler lease behavior need tests |
| Agent identity/delegated authority | Machine identity/session foundations, NOBYPASSRLS worker role, workspace-scoped worker access and founder authority | Distinct short-lived identity per agent/runtime and auditable delegated actor chain are not complete |
| Browser capability isolation | Playwright is available for deterministic tests; browser sessions have auth/session lifecycle controls | No agent-controlled browser capability, task-scoped browser profile, download quarantine or browser egress policy |

## Adopt in this order

### A. Operational visibility — next implementation increment

1. Surface the existing workspace-scoped outbox health API in the Founder Console Operations page.
2. Display pending, processing, retrying, expired-lease, dead-letter and published counts plus oldest pending age where returned by the API.
3. Add clear read-only status and explanatory copy. Do not expose a replay button in this increment.
4. Keep external event handlers disabled unless individually reviewed for authorization, idempotency, data class, timeout and failure behavior.

**Acceptance:** workspace authorization is enforced; counts are scoped to the selected workspace; empty/error states are explicit; no mutation or event dispatch occurs from the dashboard; tests cover authorization and response shape.

### B. Skill supply-chain admission record

Extend the existing catalog contract to record, for each admitted revision:
- Canonical source and pinned revision (already present).
- License and intended use (already present).
- Reviewer identity and review timestamp.
- Content hash captured at admission, not merely calculated when read.
- Static scan tool/profile/version and result, or an explicit reviewed exception.
- Synthetic test/evaluation evidence and status.
- Allowed data classes, tools, lifecycle state and explicit founder enablement (currently fail-closed defaults are present).

Keep this as an admission/governance workflow. Do not execute imported scripts, auto-update skills, or let a skill grant its own tools. External skill content is untrusted input.

**Acceptance:** malformed, unreviewed, changed-hash, failed-scan or missing-evidence entries cannot be enabled; catalog reads remain read-only; all skill use remains disabled until a separate founder-authorized assignment path exists.

### C. Evaluation release manifest and gate

Create versioned evaluation manifests that bind:
- Dataset/case-set revision and data classification.
- Agent/skill/prompt revision.
- Runtime/provider/model identifier and configuration fingerprint (never secrets).
- Evaluator/metric pack revision and thresholds.
- Policy/security test pack revision.
- Run results, reviewer and release decision.

A failed safety, tenant-isolation, regression or quality gate must block the release decision. Persist the evidence in the OS; do not make a third-party evaluation product authoritative.

### D. MCP gateway and delegated machine identity

Only after the above contracts are established:
- Admit MCP servers by pinned version, provenance, owner, license and security review.
- Proxy every invocation through the OS, with machine identity, workspace scope, tool and parameter allowlists, data classification, timeout, cost/concurrency limits, egress policy and audit.
- Resolve delegated authority from the initiating human/agent chain on every call.
- Keep provider-native MCP/tool grants disabled until the OS gateway enforces these controls.

ToolHive is an evaluation candidate for isolation, not a required dependency or substitute for OS authorization.

### E. Provider-neutral observability

Adopt OpenTelemetry GenAI semantic conventions for model/tool/agent spans. Correlate traces with OS execution, attempt, task and workspace IDs. Record model, latency, token counts and cost where available. Redact/minimize prompt and completion bodies by default; apply workspace data classification and retention policy before exporting telemetry.

Choose at most one of Langfuse or Arize Phoenix after a self-hosting, privacy, retention, cost and operational review. Do not install both by default.

### F. Browser capability — later

Keep Playwright for deterministic tests. Agent-driven browsing is a separately authorized capability with task/workspace-scoped profiles, domain allowlists, controlled downloads, malware/content scanning, file isolation and restricted egress. Do not grant arbitrary local file or unrestricted internet access.

## Explicitly defer / reject for now

- **Temporal:** evaluate only if native workers/outbox fail documented durability acceptance tests.
- **Prefect:** do not add; overlaps existing workers/outbox and the planned n8n integration role.
- **LangGraph runtime replacement:** do not replace the existing OS workflow contract; adopt supervisor/dependency/checkpoint patterns behind it.
- **Langfuse + Phoenix together:** mutually exclusive candidates; choose at most one after review.
- **ToolHive:** evaluate only when the OS MCP gateway is ready to integrate.
- **OpenHands:** optional isolated engineering workbench, not an autonomous production-code writer.
- **Sentry:** later, after log redaction, retention and self-hosting requirements are settled.
- **Semgrep / skill scanners:** candidates for deterministic CI/admission checks after rules, pinned versions and false-positive handling are reviewed. No auto-remediation or auto-merge.
- **OPA / Cedar:** defer until application authorization rules become too complex to test and maintain; current backend authorization remains authoritative.

## Release and safety guardrails

- No external platform becomes the source of truth for OS business or authorization state.
- No broad credentials, production access or client data by default.
- No automatic skill updates, autonomous security remediation, auto-merge or unreviewed production changes.
- External calls remain outside database transactions and must be idempotent/reconcilable.
- Replay, deletion, permission changes, production release and other protected actions remain approval-gated.
- Use synthetic/public data until runtime eligibility and end-to-end data controls are verified.
- Every integration must have an owner, purpose, threat/data-flow review, permission scope, cost cap, recovery path and removal plan.

## Current priority

1. Operational visibility for the existing outbox and exception/recovery signals.
2. Skill admission evidence and versioned governance.
3. Evaluation release manifests and enforced gates.
4. OS MCP gateway plus per-agent delegated machine identity.
5. Provider-neutral telemetry and, only if justified, one observability backend.
6. Isolated agent browser capability.

This order favors useful founder visibility and stronger controls before enabling more autonomy. It deliberately avoids adding new infrastructure before the current OS foundations are fully exercised.
