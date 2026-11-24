# Final Agency OS scope and acceptance baseline

**Status:** Scope frozen. This document is the agreed target for implementation, integration, stabilization and validation.
**Product boundary:** Private, founder-controlled internal operating system. It is not a SaaS product.

## 1. Product model

The public agency website is a separate application and remains outside the private OS runtime. The optional signed, idempotent server-to-server lead-intake bridge is implemented and merged in both repositories (website PR #30 and OS intake endpoint). It remains disabled pending external configuration and synthetic end-to-end validation. The website must never access the OS database or private Founder Console.

The Agency OS is the private operational source of truth. The founder remains the final authority for commercial commitments, sensitive communications, production releases, payments and destructive actions.

One primary founder/operator does not remove the need for strict client/workspace isolation. Every client project, document, conversation, execution, artifact and credential reference must remain scoped.

## 2. Final architecture decisions

| Area | Decision |
|---|---|
| Application architecture | Next.js Founder Console + FastAPI modular monolith |
| Source of truth | PostgreSQL |
| Business processes | Native OS domain services and state machines |
| Async execution | Durable Python workers, persisted execution attempts and transactional outbox |
| Queue/cache | Add Redis only when a measured need exists; PostgreSQL remains authoritative |
| Automation platform | No n8n, Activepieces, Temporal or second workflow engine initially |
| AI runtime | Provider adapter; Claude Managed Agents candidate primary runtime, with self-managed alternative where required |
| Voice | Provider-neutral telephony adapter supporting inbound and outbound calls |
| Voice agent media | Separate real-time service/adapter; not ordinary REST request handling |
| Evaluation | Native OS evaluation service using reusable Harness primitives |
| Storage | Private object-storage adapter for recordings, documents and artifacts |
| Deployment | Docker Compose first; separate dev/staging/production |
| Website | Separate public app; future secure intake integration only |
| Client portal/chatbot | Not in current scope |

Existing n8n-related code and legacy workflow exports may remain as migration references, but must not be treated as an enabled production automation engine.

## 3. Revenue Engine

### 3.1 Lead and relationship management

- Leads, contacts, companies/clients, opportunities and pipeline stages.
- Source provenance, original page/campaign, created/updated timestamps and contact preferences.
- Deduplication using normalized email/phone/domain plus reviewable match candidates.
- Lead qualification: problem, service fit, urgency, timeline, budget range when volunteered, decision process and missing information.
- AI-generated score, summary and suggested next action must be labelled as recommendations with evidence and confidence; a model cannot silently overwrite founder decisions.
- Suppression, opt-out, bounce and do-not-contact state must block prohibited outreach.
- A unified relationship timeline links calls, emails, meetings, notes, proposals, decisions, tasks and support interactions to the correct lead/contact/client.

### 3.2 Outreach and communication

- Approved sender identities, consent/provenance, suppression checks, rate limits and local contact windows.
- Stop follow-ups on reply, opt-out, bounce, complaint or manual suppression.
- Routine pre-authorized follow-ups may execute within a founder-approved policy.
- Sensitive messages, commitments, pricing, contracts and unusual outreach require approval.
- Persist outbound intent, provider message ID, delivery status, retries, failures and audit events.
- Do not send messages merely because an AI agent recommends them.

### 3.3 Opportunities, service catalog and proposals

- Opportunity stages: new, qualification, qualified, discovery, proposal, negotiation, won, lost, nurture and suppressed (where applicable).
- A versioned internal service catalog describes capabilities, assumptions, reusable deliverables and estimation inputs.
- Proposal/quotation/SOW drafts may be generated from approved discovery and service-catalog data.
- Store revisions, scope, assumptions, exclusions, price/currency, validity, approval state and client response.
- Founder approval is mandatory before a proposal, price, SOW or contract is sent or accepted.
- Contract execution/signature and legal advice remain external processes unless separately integrated and reviewed.

## 4. Delivery Engine

- Client onboarding checklist and workspace provisioning.
- Discovery records, problem statement, objectives, constraints, stakeholders and success measures.
- Requirements with stable IDs and traceability to design decisions, tasks, code changes, tests and handover evidence.
- Project plans, milestones, tasks, dependencies, owners, risks, budgets, change requests and deliverables.
- Engineering work must include human review; AI-generated code cannot approve itself.
- QA/security gates, test evidence, deployment approvals, rollback plan and handover.
- Client support tickets, incidents, maintenance history, service commitments and renewal reminders.
- Client-specific knowledge and artifacts remain tenant/workspace scoped.

## 5. Telephony and conversation intelligence

The voice agent is an internal telephony capability, not a website chatbot or browser voice widget.

### Inbound
- Receive calls on an approved agency number/provider route.
- Identify/disclose the automated agent and explain recording/transcription handling.
- Handle only approved public agency information and lead-intake actions.
- Escalate to the founder or take a callback request when uncertain or when a human is requested.
- Do not reveal private client/project information without appropriate caller verification and authorization.

### Outbound
- Founder-initiated calls and explicitly authorized callbacks are supported.
- A website enquiry or lead record alone is not permission to call.
- Check consent/provenance, suppression, applicable local rules, approved caller ID, contact time windows and rate limits before dialing.
- Sensitive or unusual calls require founder approval.
- Provider retries must not create duplicate calls.

### Call record and transcription
- Persist call direction, provider identifiers, timestamps, status transitions, participant/lead/contact links, consent/disclosure state, outcome, failure reason and cost metadata.
- Store transcripts and summaries as separate scoped artifacts with access audit and retention controls.
- Generate structured outputs: intent, business problem, requirements, objections, timeline, next steps and follow-up recommendation.
- Distinguish verbatim transcript from AI summary and extracted fields.
- Never fabricate missing transcript content; mark uncertain speaker attribution or transcription confidence.
- Recording is off by default unless legally reviewed and consented. Prefer transcript-only capture where sufficient.
- Call records and transcript updates must be idempotent and auditable.

## 6. Finance and commercial visibility

This is an agency management ledger, not a replacement for statutory accounting, payroll, tax filing or an accountant.

- Track project budgets, estimates, approved fees, invoices/receivables, payments and expenses.
- Track direct project costs and provider/model/telephony usage.
- Calculate estimated project margin and actual margin from recorded data; clearly label incomplete cost allocations.
- Track payment due dates, overdue items and renewal dates.
- Use integer minor currency units and explicit ISO currency codes; never mix currencies in totals without conversion records.
- Financial commitments, payment execution, refunds and write-offs require founder approval.
- Export records for external accounting workflows.

## 7. AI workforce and evaluation

- Keep departments, teams, agents, skills, tools, workers, workflows, tasks, sessions and executions distinct.
- Agent Registry stores versioned instructions, runtime, allowed data classes, tools, scopes, budgets, status and rollback version.
- Enforce least privilege in backend code, not prompts.
- Data Protection Gateway classifies/minimizes/redacts data and checks runtime eligibility before provider dispatch.
- Claude Managed Agents remain an adapter candidate; beta status and contractual restrictions must be reviewed before use with commercial data.
- Persist execution request, attempts, leases, heartbeat, result, errors, cancellation and audit.
- Evaluation Harness primitives cover RAG, agents, regression, safety, security and release gates.
- Failed mandatory quality/security gates block release; model output cannot override deterministic gates.
- Track model/provider usage and cost per execution, task, client/workspace and period where provider data permits.

## 8. Founder control and operating intelligence

Founder Console must ultimately provide:
- Unified inbox for approvals, callbacks, follow-ups, tasks and exceptions.
- CRM pipeline and relationship timeline.
- Project health, milestones, risks, budget and delivery evidence.
- Agent/workflow/execution status, retries, failures, cost and evaluation results.
- Finance overview: receivables, expenses, budgets and profitability.
- Provider/integration health and configuration status without exposing secrets.
- Audit and security-event review.
- Backup age, last successful restore drill and recovery status.

Dashboards are read models. They must not become a second source of business truth.

## 9. Reliability and event contract

- Business record change and outbox event are committed in one PostgreSQL transaction.
- Events are versioned and include event ID, event type, schema version, organization/workspace scope, aggregate ID, correlation ID and idempotency key.
- Delivery is at-least-once. Consumers must be idempotent.
- Implement safe claiming/leases, heartbeat, bounded exponential retry, dead-letter handling, cancellation and reconciliation.
- External provider calls happen outside database transactions.
- Record attempts, provider IDs, outcomes and error classifications.
- Do not claim exactly-once external side effects.
- Report success only after the business outcome is persisted and reconciled.

## 10. Security and governance gates

- Production OIDC/JWKS authentication, MFA-capable identity provider and short-lived sessions.
- Separate founder-wide authority from organization membership/owner role.
- Tenant-scoped RBAC/ABAC and PostgreSQL row-level security where appropriate; test API, worker, files, cache and object storage boundaries.
- Scoped service identities and credentials; secrets manager/KMS, rotation and no secrets in prompts/logs/source.
- Approval request and protected side effect must be consumed atomically.
- Approvals are required for pricing, contracts, payments, sensitive communications, production releases, destructive actions, client-data deletion and permission/security changes.
- Only an active, explicit `FounderAuthority` grant may approve protected actions; organization `Role.owner` alone is insufficient. A founder may approve an action they initiated. Non-founders cannot approve their own requests.
- Data classification, minimization, redaction, runtime eligibility and client authorization.
- Retention, expiry, export, deletion and artifact cleanup cover records, transcripts, recordings, logs and backups.
- Tamper-evident audit of access, processing, policy, approvals, runtime routing, provider actions and security events.
- Isolated worker sandboxes, resource quotas, restricted egress, safe file handling and bounded execution cost/duration.

## 11. Separate website boundary (signed lead intake implemented; activation pending)

The optional bridge is implemented and merged in both repositories. Keep it disabled until both migrations, matching server-only secrets, fixed org/workspace mapping, HTTPS and synthetic end-to-end idempotency/recovery tests are complete.

The integration follows this boundary:
1. Browser submits to a website server-side route/Cloudflare Worker, not directly to the OS.
2. Validate schema, request size, origin, honeypot, rate limits and Turnstile where enabled.
3. Worker signs service-to-service request with timestamp, nonce and replay protection.
4. OS validates signature, idempotency and schema; persists inbound enquiry first.
5. OS deduplicates, links/promotes lead/contact, records source attribution and queues qualification.
6. Website receives a safe acknowledgement and correlation ID, never private CRM data.
7. Retries reconcile by idempotency key. Do not maintain two independent CRMs permanently.

No website chatbot, browser voice widget or client portal is required for this integration.

## 12. Explicitly out of scope

- SaaS multi-customer subscription/billing product.
- Public client registration or general-purpose client portal.
- Website chatbot/AI concierge in the current build.
- Browser voice agent; telephony only.
- Full ERP, payroll, tax filing or statutory accounting.
- Multiple CRMs, agent platforms, workflow engines or voice frameworks.
- Kubernetes, microservices proliferation or event streaming platform without measured need.
- Autonomous sending of proposals/contracts, binding prices, payments or production releases.

## 13. Definition of done

The OS is not ready merely because routes compile or unit tests pass. Each domain is accepted only when its workflow has:

1. Schema and migration tested on PostgreSQL.
2. Authenticated API and authorization tests.
3. Cross-tenant/workspace isolation tests.
4. Audit and event persistence.
5. Idempotency, retry and recovery tests where external actions exist.
6. Founder Console interaction and error states.
7. Synthetic end-to-end test with persisted evidence.
8. Monitoring, bounded cost and operational runbook.
9. Backup/restore and retention/deletion evidence where data is stored.
10. Human approval gates demonstrated for protected actions.

## 14. Founder operating philosophy

The operating model is **founder-in-the-loop, not founder-in-every-loop**. Routine, low-risk internal work may execute autonomously only when explicitly allowlisted and after backend checks for identity, scope, client policy, data classification, budgets, idempotency and audit. High-impact commercial, sensitive communication, financial, production, destructive and security actions require explicit Founder Authority approval. Unknown action types default to manual review. Outbound calls and follow-ups require consent and suppression checks; a lead record alone never authorizes contact. See `FOUNDER_AUTONOMY_MODEL.md`.

## 15. Scope freeze

This is the final feature scope. After this baseline is accepted, do not add speculative features. Work should move to implementation completion, integration, stabilization, testing, security validation, operational readiness and documentation. Any new feature requires a demonstrated business need and explicit scope-change decision.
