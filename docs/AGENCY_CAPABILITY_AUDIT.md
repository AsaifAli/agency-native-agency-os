# Agency Capability Audit — Required Operating Capabilities

**Audit date:** 2026-11-25  
**Purpose:** Identify the capabilities required to operate the AI solutions agency end to end, compare them with the current Agency OS implementation, and prioritize safe implementation.  
**Boundary:** This is an audit and proposed implementation plan, not authorization to activate external side effects, spend money, contact prospects, place calls, sign contracts, or process client data.

## Executive assessment

The Agency OS has a substantial foundation: organization/workspace scoping, clients, contacts, leads, opportunities, projects and milestones; workforce governance; founder approvals; execution persistence; selected outbox infrastructure; signed website lead intake; call/transcript record foundations; delivery playbooks; time/cost records; provisional project financial summaries; and evaluation packs.

It is not yet a complete agency operating system. The most important missing operational capabilities are automated prospect acquisition/enrichment, governed communication dispatch, live AI telephony, full CRM deduplication and next-action management, proposal revisioning and external commercial execution, recurring retainer billing/SLA/renewal, campaign analytics, client success, and verified cross-workspace/security/recovery controls.

Department profiles, skills and plan drafts are not proof that those business functions are live.

## Capability inventory

Status meanings:
- **Foundation:** data model/API or partial workflow exists; end-to-end operating capability is not complete.
- **Partial:** useful pieces exist, but essential controls/integrations/workflows are missing.
- **Missing:** no verified working implementation identified in the current source inventory.
- **External:** depends on provider configuration, legal review, credentials or operational policy.

| Domain | Required capability | Current evidence/status | Priority |
|---|---|---|---|
| Market intelligence | ICPs, verticals, geography, buying signals, competitor/service research | Missing as an operational pipeline | P0 |
| Prospect acquisition | Company/contact discovery, enrichment, evidence URLs, source and confidence | Research record schema and source-backed evidence capture exist in PR #28; automated discovery/enrichment connector and deduplication are missing | P0 |
| CRM | Companies, contacts, leads, opportunities, stages | Foundation implemented | P0 |
| CRM integrity | Deduplication, merge review, relationship timeline, activities, next actions | Append-only contact activity timeline implemented; deduplication/merge review and structured next-action queue remain incomplete | P0 |
| Outreach | Personalized email/LinkedIn drafts, approved sender identities, delivery tracking | Agent-prepared email/LinkedIn/call-script drafts and founder review exist in PR #28; no send, schedule, sender identity or delivery tracking | P0 |
| Outreach governance | Consent/provenance, suppression, opt-out, bounce/complaint stop, contact windows, rate limits, idempotency | Required but incomplete | P0 |
| AI phone agent | Inbound answering, outbound authorized callbacks, qualification, transfer/escalation | Call/transcript records only; live telephony missing | P0/P1 |
| Conversation intelligence | Transcription, summaries, requirements, objections, tasks, CRM linkage | Partial foundation; STT/TTS and lifecycle missing | P1 |
| Calendar and meetings | Founder availability, booking links/provider integration, reminders, meeting notes | Not verified | P1 |
| Marketing strategy | Positioning, ICP messaging, offers, content calendar, channel plans | Missing as a governed workflow | P1 |
| Content production | Social posts, blogs, case studies, email sequences, landing-page copy, creative briefs | No integrated workflow verified | P1 |
| Advertising | Campaign drafts, audience/creative variants, budget proposals, tracking and attribution | Missing | P1 |
| Publishing | Approved social scheduling/publishing and post performance | Missing; provider integrations required | P2 |
| Website conversion | Signed website lead intake exists, disabled pending external config and E2E validation | Foundation implemented; activation pending | P0 |
| Sales | Qualification, discovery, objections, follow-up, pipeline forecasting | Partial CRM foundation | P0 |
| Service catalogue | Versioned agency offers, deliverables, assumptions, exclusions, estimation inputs | Founder-governed, draft-first versioned catalogue implemented; proposal snapshot linkage pending PR #26 validation | P0 |
| Proposals | Proposal/quotation/SOW drafts, revisions, approvals, send status | Internal proposal drafts, one-time/retainer terms and single-use founder pricing approval implemented in PR #28; revisioning and governed sending remain missing | P0 |
| Contracts | NDA/MSA/SOW metadata, signature status, obligations, renewals | Internal contract register, founder approval and signed-evidence recording implemented; legal templates, external signature, obligations and renewal workflow remain incomplete | P1 |
| Client onboarding | Won deal to workspace, kickoff, access, requirements, baseline, acceptance | Contract-backed onboarding checklist and founder-approved activation into delivery project implemented; complete workspace provisioning and acceptance/handover remain partial | P0 |
| Project delivery | Projects, milestones, tasks, budgets, time/cost | Foundation implemented; retainer service-period ledger, billable usage snapshots and overage visibility added in PR #28; QA, SLA, recurring billing and handover remain incomplete | P0 |
| Requirements and change control | Requirements traceability, scope change, approval, impact | Partial; scope-change foundation exists | P1 |
| QA and release | Acceptance criteria, evidence, security review, release approval, rollback | Partial; full gates incomplete | P0 |
| Client success | Status updates, satisfaction, issue escalation, renewals, referrals | Partial foundations only; account-health action classification exists, but grounded health scoring, feedback, support and renewal lifecycle are missing | P1 |
| Support | Requests, incidents, priority, SLA/response targets, resolution and knowledge articles | Missing as complete workflow | P1 |
| Finance | Project estimates, budget, time/cost and provisional summaries | Foundation implemented | P0 |
| Invoicing | Invoice numbers, line items, tax fields, due dates, revisions, status | Internal invoice draft, overbilling guard, founder issue approval and issue-evidence recording implemented; tax fields, document generation and sending remain missing | P0 |
| Payments | Payment links/provider adapter, webhook verification, reconciliation, refunds | Append-only manual receipt reconciliation with duplicate/overpayment guards implemented; provider webhooks, collection and refunds remain external/missing | P0/P1 |
| Receivables | Due/overdue tracking, reminders, aging and collection status | Invoice outstanding balances and partial/paid state implemented; aging reports and reminders remain missing | P0 |
| Expenses and profitability | Expenses, provider usage allocation, project/client margin | Partial | P1 |
| Accounting export | Reconciled export for external accounting/tax professional | Missing | P2 |
| Analytics | Lead source, conversion, campaign ROI, pipeline, revenue, margin, delivery health | Partial dashboard/read models; business analytics incomplete | P1 |
| Agency operations | SOPs, recurring internal tasks, operational calendar, exceptions | Partial foundation | P1 |
| Capacity planning | Skills, availability, utilization, workload and delivery forecast | Workforce structure exists; capacity system missing | P2 |
| Knowledge management | Playbooks, case studies, reusable architecture, lessons learned, source/version | Partial via skills/playbooks; agency knowledge base incomplete | P1 |
| Vendor management | Provider registry, data classification, credentials, quotas, renewals, status and spend | Partial integration configuration; full registry absent | P1 |
| Legal/commercial admin | NDA/MSA/SOW register, IP/data clauses, obligations, renewal dates | Missing; legal review remains human/external | P1 |
| Security and privacy | Tenant isolation, DPG, identity, secrets, retention, deletion, audit | Partial; major verification gaps remain | P0 |
| Reliability | Outbox consumers, worker crash recovery, reconciliation, alerts, backup restore | Partial; production handlers and recovery proof incomplete | P0 |
| Business continuity | Backup age, tested restore, incident response, provider outage playbooks | Not verified | P0 |
| Partnerships/referrals | Partner directory, referral source, attribution, commission/obligation tracking | Optional later | P2 |

## AI calling: required capability design

AI calling should be a first-class communications capability integrated with CRM, not a standalone voice bot.

### Inbound use cases
1. Answer calls to an approved agency number.
2. Identify itself clearly as an AI assistant and explain transcription/recording handling.
3. Answer only approved public agency/service questions.
4. Collect a prospective client's name, company, reason for calling, problem, urgency and preferred callback time.
5. Create or update a CRM lead after validation and deduplication.
6. Offer an appointment or callback request using approved calendar availability.
7. Transfer to the founder or take a message when a human is requested, confidence is low, or the request is sensitive.
8. Never disclose private client, project, pricing or account information without caller verification and authorization.

### Outbound use cases
1. Founder-initiated calls.
2. Explicitly authorized callbacks to people who requested them.
3. Scheduled discovery calls after a booking or consent.
4. Follow-up calls only under a defined, legally reviewed contact policy.
5. No cold AI calling by default. A lead record, scraped number, website form or email address alone is not permission to call.

### Conversation intelligence
- Provider call ID, direction, number reference, timestamps, status and duration.
- Consent/disclosure status and legal basis/source.
- Link to CRM lead/contact/client and related opportunity.
- Transcript, summary and extracted facts stored as separate artifacts.
- Distinguish verbatim transcript from model summary and inferred recommendations.
- Extract requirements, objections, urgency, timeline, next steps and follow-up proposal.
- Confidence/uncertainty markers; never fabricate missing transcript content.
- Create follow-up tasks only after deterministic validation and policy checks.
- Retention/deletion, access audit and workspace scoping for transcripts and recordings.
- Recording disabled by default until jurisdiction/provider policy is reviewed and required consent is captured.

### Proposed technical architecture
- Provider-neutral telephony adapter; do not hardwire business logic to one carrier.
- Separate real-time media service for audio streaming and interruption handling; FastAPI REST request handling is not the media loop.
- Speech-to-text, turn detection, LLM reasoning, text-to-speech and telephony transport are replaceable adapters.
- OS owns call records, authorization, call state, consent, budgets, audit and CRM linkage.
- Signed provider webhooks, timestamp/replay checks, provider event deduplication and idempotent status transitions.
- Persist call intent before dialing; use an idempotency key to prevent duplicate calls after retries.
- Tool gateway allows only narrowly scoped operations such as read public service information, create a callback request, create a lead, or request a calendar slot.
- No direct access from voice runtime to database, payment tools, arbitrary URLs or unrestricted CRM records.
- Human transfer, DTMF/secure handoff where supported, interruption, silence, network failure and emergency stop paths.
- Usage/time/cost limits per call and per day; circuit breaker and immediate founder kill switch.
- Synthetic call scenarios and evaluation before real numbers or client calls.

### Telephony release gates
1. Choose provider only after pricing, country coverage, data location, subprocessors, retention, webhook security and contractual review.
2. Validate Indian and any target-market telecom/consent/DND rules with qualified counsel/provider before outbound activation.
3. Start with internal test number and synthetic scenarios.
4. Enable inbound public-information and callback-request handling first.
5. Add outbound founder-initiated callbacks only after consent/provenance and suppression controls pass.
6. Add transcription and CRM extraction only after privacy/retention and access controls pass.
7. Do not enable cold calling, bulk calling or autonomous sales commitments.

## Recommended agency workflow

1. Define service catalogue and ICP.
2. Research target accounts and record source evidence.
3. Enrich and deduplicate prospect records.
4. Qualify and prioritize with explainable evidence.
5. Draft personalized outreach.
6. Founder approves sender, campaign and contact policy.
7. Dispatch through approved providers; track delivery/replies/opt-outs/bounces.
8. AI or human handles inbound response and requested callbacks; create CRM activities.
9. Schedule discovery and prepare structured discovery notes.
10. Draft proposal/estimate/SOW from approved service catalogue.
11. Founder approves price, scope and contract.
12. Mark won and create client workspace/project/onboarding checklist.
13. Deliver with milestones, tasks, QA evidence and founder release approval.
14. Issue invoice and reconcile payment notifications.
15. Track costs, margin, client satisfaction, support and renewal.
16. Use campaign, pipeline, revenue and delivery analytics to improve targeting and operations.

## Priority implementation plan

### P0 — Get first clients and deliver safely
- Complete CRM relationship timeline, source provenance and duplicate review.
- Implement ICP/service catalogue and prospect research record model.
- Build research/qualification agent in read/draft mode with citations and confidence.
- Build outreach draft/review queue, sender registry, suppression list and consent evidence.
- Implement safe provider dispatch only after approval, reply/opt-out/bounce stop rules and idempotency.
- Complete signed website intake external configuration and synthetic E2E test.
- Implement proposal/estimate/SOW drafts and founder approval.
- Implement client onboarding and delivery acceptance checklist.
- Implement invoice/receivable records and payment reconciliation; payment execution/refunds remain approval-gated.
- Close tenant isolation, DPG, identity, session/retention and worker recovery gaps before client confidential data.
- Complete a synthetic end-to-end prospect-to-payment-to-handover test.

### P1 — Make operations efficient
- AI inbound phone agent and authorized callbacks.
- Conversation transcription and structured discovery notes.
- Calendar/meeting scheduling.
- Marketing calendar, content generation and approved social publishing.
- Campaign attribution and revenue analytics.
- Support/incident/renewal workflow.
- Vendor registry, usage budgets and integration health.
- Knowledge base and reusable case studies.
- Contract register and obligations/renewal tracking.

### P2 — Scale only when volume justifies it
- Paid advertising platform execution and advanced attribution.
- Capacity/utilization forecasting and partner/referral management.
- Accounting software export/integration.
- Advanced cohort, margin and forecasting analytics.
- Additional channels, voice languages and multi-provider failover.

## Explicitly avoid for now
- Building a full ERP, payroll, tax filing or statutory accounting product.
- A second CRM or a parallel spreadsheet database as source of truth.
- A website chatbot or browser voice widget; telephony is a separate internal capability.
- Unrestricted autonomous cold email, LinkedIn scraping/automation, cold AI calling or bulk campaigns.
- Automatic ad spend, payment execution, refunds, contract acceptance or binding pricing.
- Adding another workflow engine or multiple agent runtimes before proving a need.
- Treating workforce positions or skills as active provider agents.
- Using client confidential data with an unverified runtime, provider or isolation boundary.

## Definition of done for each capability

A capability is not complete because a schema, UI, role prompt or route exists. It must have:
1. PostgreSQL migration and rollback/recovery plan.
2. Authenticated API and explicit authorization.
3. Organization/workspace isolation tests.
4. Audit and versioned event persistence.
5. Idempotency, retries, reconciliation and failure tests for external actions.
6. Founder Console review, approval and exception handling.
7. Synthetic end-to-end workflow with persisted evidence.
8. Monitoring, provider budgets, retention and operational runbook.
9. Human approval gates for sensitive/commercial/financial actions.
10. Explicit status in implementation documentation: implemented, tested, partial, planned or unverified.

## Audit conclusion

The highest-value gap is not another dashboard. It is a complete, governed revenue-to-delivery loop: find prospects, communicate with permission, convert opportunities, contract and invoice, deliver reliably, collect payment, support clients and measure the business.

AI calling belongs in that loop, with inbound qualification and requested callbacks before any broader outbound automation. The immediate next action should be to approve this audit as the capability baseline, then implement P0 in small tested slices without activating external side effects prematurely.


## Implementation reconciliation (2026-11-25)
Merged code includes contact relationship activities, Leads/Opportunities Founder Console workflows, proposal drafts with founder pricing approval, a founder-governed service catalogue, a contract register requiring approved proposal and signed evidence, contract-backed onboarding with checklist/activation approval, and an invoice/receivables register with founder issue approval and append-only payment receipt reconciliation. These are internal control-plane workflows, not external delivery: there is no proposal/contract/invoice sending, payment collection, or autonomous outreach. PR #26 proposes immutable service-offering snapshots on linked proposals and remains unvalidated until CI passes.


## 2026-11-25 implementation checkpoint
The current integration branch adds one-time/retainer proposal and contract terms, source-backed lead research records, founder-reviewed outreach drafts, and a retainer service-period usage ledger with founder closeout. These changes are in PR #28 and are **not merged or validated**. See [Production Readiness Checklist](PRODUCTION_READINESS_CHECKLIST.md) for weighted progress, verification state, release gates and remaining work.
