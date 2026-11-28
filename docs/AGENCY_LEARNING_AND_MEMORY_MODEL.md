# Agency Learning and Memory Model

**Status:** **Partial implementation.** Workspace-scoped learning candidates, verified source lineage, sanitized capture, idempotency, audit and founder-only promotion into versioned workspace knowledge are implemented. Automatic extraction, retrieval/injection into runtimes, cross-scope promotion, skill proposals and effectiveness measurement remain unimplemented.

## 1. Why the agency learns

We are a RAAS AI solutions agency. Learning exists to improve the quality, speed, reliability and economics of client outcomes—not to make agents modify themselves for its own sake.

The learning loop serves both operating engines.

| Revenue Engine | Delivery Engine |
|---|---|
| Market/account research quality | Discovery and requirements completeness |
| Lead qualification and service fit | Architecture and implementation choices |
| CRM hygiene and next-action quality | Engineering quality and rework |
| Proposal assumptions and estimate accuracy | QA, security and evaluation findings |
| Outreach draft quality and response insights | Deployment, handover and support |
| Win/loss and conversion evidence | Measured client outcomes and delivery margin |

Every lesson must connect to an observable business or delivery result. Agent activity, token use and task completion alone are not evidence of value.

## 2. Four kinds of learning

1. **Session context:** temporary context used while a task is running. It may disappear and is not durable memory.
2. **Skills and instructions:** version-controlled Markdown procedures, domain knowledge, checklists and role guidance. These are the preferred low-cost way to encode stable operating knowledge.
3. **Persistent operational memory:** structured, scoped, searchable facts, preferences, decisions, lessons and references owned by the Agency OS. This requires durable storage, lifecycle, access control and retrieval; a Markdown file or provider memory does not replace it.
4. **Model training/fine-tuning:** a separate, expensive and higher-risk activity. It is not required for our first learning capability and must not be enabled by this design.

Start with skills plus OS-owned memory. Do not build a fine-tuning pipeline or a new learning microservice unless evidence later justifies it.

## 3. The learning loop

Use the existing [operational-learning-capture skill](../skills/operational-learning-capture/SKILL.md) as the capture procedure. This model defines how captured lessons become useful without granting agents self-modification rights.

1. **Observe:** use completed/failed execution records, task outcomes, QA findings, evaluation results, approved client feedback, sales outcomes and founder corrections.
2. **Extract:** produce a candidate lesson that separates observed evidence from interpretation and recommendation.
3. **Classify:** apply data classification, PII minimization/redaction, client policy and runtime eligibility before any durable storage or provider dispatch.
4. **Scope:** assign the narrowest valid memory scope and a source event/artifact reference.
5. **Validate:** assess evidence strength, sample size, recency, counterexamples, confidence and expiry/review date.
6. **Recommend:** propose a change to a checklist, skill, workflow, evaluation pack or reusable memory entry.
7. **Review and promote:** promote only through the authority rules below. A lesson is not a permission, approval or policy.
8. **Measure:** compare later outcomes and mark the lesson confirmed, stale, contradicted or superseded.

### The three operating verbs

- **Remember:** retain an eligible fact or lesson in its authorized scope. Routine, low-risk memory capture can be automated only after the OS has a tested persistence and policy path.
- **Recommend:** prepare a candidate change with evidence, provenance, expected benefit, risk and rollback plan.
- **Change:** publish a versioned change only after required review, evaluation and approval.

Agents may propose; they may not grant themselves authority, approve their own changes or silently edit shared policy.

## 4. Memory scopes and promotion

Use the narrowest applicable scope:

| Scope | Examples | Sharing rule |
|---|---|---|
| Founder | Explicit founder preferences and operating decisions | Founder-controlled; do not expose secrets |
| Organization | Approved agency-wide methods, policies and reusable playbooks | Requires founder approval for promotion |
| Department | Revenue, Engineering, QA/Security, Finance or Delivery practices | Department scope; no implicit client-data access |
| Agent/role | Role-specific operating notes and validated procedures | Only available to authorized role/runtime |
| Client workspace/project | Client requirements, decisions, environment facts, feedback and lessons | Never visible to another client or general memory by default |

A client-specific fact remains client-specific even if it appears useful elsewhere. A generalized method may be proposed for wider use only after removing client identifiers, secrets, personal data and confidential context; checking the client agreement and data policy; validating that the lesson is genuinely generalizable; and obtaining the required review/approval.

No cross-client retrieval, embedding, cache reuse or prompt injection is allowed unless tenant/workspace authorization is enforced at the retrieval boundary. Filtering only after retrieval is insufficient.

## 5. What may be automated

**Eligible for bounded automation after implementation and testing:**
- Capture sanitized execution metadata and references.
- Draft candidate lessons from eligible public/synthetic or explicitly authorized data.
- Detect repeated failure patterns and evaluation regressions.
- Suggest an existing skill/checklist/evaluation pack that should be updated.
- Mark a candidate stale when its evidence expires or is contradicted.

**Always gated or prohibited without explicit authority:**
- Changing founder authority, RBAC/ABAC, tool grants, runtime eligibility or autonomy.
- Promoting client-derived knowledge across workspaces.
- Changing commercial policy, pricing, contracts, payment behavior or outreach policy.
- Publishing a new shared skill or operating instruction without review.
- Modifying source code, production workflows or deployment policy without the normal engineering/release process.
- Treating provider-side memory or Cowork project memory as authoritative Agency OS memory.

## 6. Skills evolution

Prefer editing a Markdown skill over writing a new service when the desired change is procedural knowledge. For every proposed skill change:
- Link source executions, evaluations or approved feedback.
- State the behavior before and after, intended scope and expected outcome.
- Include counterexamples and limitations.
- Run skill admission/security review when external content is involved.
- Check the diff for prompt injection, secret access, tool/permission escalation and accidental client data.
- Run relevant synthetic evaluations/regression checks.
- Publish as a reviewed, version-controlled change with rollback history.

Do not let an agent overwrite the skill that governs its own permissions or approval rules.

## 7. Cowork and provider memory

Cowork Projects can retain project context and memory inside Claude. That is useful as a working surface for a bounded project, but it is not the canonical memory store. It may not be synchronized with OS records, may not enforce our full tenant model, and must not be treated as an audit trail or permission source.

When Cowork produces a reusable insight, bring it back through the same OS learning process: identify source, owner, workspace, data class, evidence, scope and approval. Store only approved, minimized content in the Agency OS.

## 8. Evaluation and observability

Measure learning quality, not just volume:
- Candidate lessons with complete provenance.
- Accepted/rejected/stale/contradicted lessons.
- Skill proposals and approval latency.
- Evaluation pass/fail before and after a change.
- Recurrence rate of previously resolved failures.
- Rework, defect escape, delivery cycle time and estimate variance.
- Revenue research/qualification/proposal quality and conversion where evidence exists.
- Client outcome measurement completeness and verified impact.

A rise in captured lessons is not itself improvement. Track regressions and false lessons as first-class outcomes.

## 9. Implementation boundary

**Already present on main (repository inspection):**
- Curated, read-only skill catalog with provenance and pinned upstream references.
- Skills default disabled, public/synthetic data only and no tool grants.
- Operational-learning-capture skill describing evidence-backed scoped lesson capture.
- Workforce, execution and evaluation foundations that can provide source events and review signals.

**Implemented in this release candidate:**
- `learning_candidates` stores workspace-scoped candidate lessons with evidence summary, source type/reference, data class, confidence, idempotency key and review lifecycle.
- Candidate sources are verified against a completed execution in the same workspace. Evaluation runs are currently excluded because their evidence is self-reported and not independently attested.
- Source data class is derived from the source execution lineage. Commercial, confidential and regulated sources are rejected; callers cannot downgrade a source to synthetic/public.
- Candidate text passes the Data Protection Gateway sanitizer. Candidate creation and promotion/rejection are audited.
- Founder authority is required to promote a candidate. Promotion creates a versioned, approved `KnowledgeItem` in the same workspace only; no cross-workspace or organization-wide promotion exists.
- The table is tenant-RLS protected and inaccessible to the ordinary worker role. Migration joins both existing Alembic heads.
- API: `POST/GET /v1/orgs/{org_id}/learning/candidates` and `POST /v1/orgs/{org_id}/learning/candidates/{candidate_id}/review`.

**Still not implemented:**
- Automatic extraction/capture from completed executions; candidates are explicitly submitted through the API.
- Retrieval/injection of approved knowledge into Claude Code, Cowork or Managed Agents sessions.
- Founder/department/organization-wide memory scopes and cross-scope promotion.
- Skill proposal lifecycle, versioned skill publishing and rollback integration.
- Learning dashboard, effectiveness tracking and regression gates for skill changes.
- Retention/expiry automation specific to learning candidates and effectiveness outcomes.

Do not report these as live until code, migrations, authorization tests, lifecycle behavior and end-to-end evidence prove them.

## 10. Acceptance criteria and current limitations

- Client workspace A cannot retrieve any memory or artifact from workspace B through API, worker, cache, search or provider context.
- A client lesson cannot become organization-wide without de-identification, policy review and founder approval.
- Every lesson has provenance, scope, data class, confidence, validity/review date and source references.
- Duplicate candidate submissions with the same source/title are idempotent; a conflicting payload under the same key returns HTTP 409.
- Source lineage is verified against a completed execution/evaluation record in the same workspace; caller-supplied labels alone are not trusted.
- Retention, expiry, correction and deletion cover memory records, derived indexes, caches and linked artifacts.
- A skill proposal cannot publish itself; failed evaluations block promotion.
- Founder can inspect, approve, reject, supersede and roll back shared learning.
- Routine approved memory capture is low-friction; protected policy/permission changes remain gated.
