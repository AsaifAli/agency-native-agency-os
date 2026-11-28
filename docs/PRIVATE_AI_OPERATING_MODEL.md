# Private AI and Business Operations Layer

**Status: approved implementation direction; capabilities are being delivered incrementally.** This document records a selective adaptation of the ReStructure Brief article, "The Private AI Operating System" (reviewed 2026-11-28). Individual capabilities remain unimplemented until their code, tests and acceptance evidence are merged. The Agency OS will use approved hosted model providers only. Local AI runtimes, local model serving and local inference are explicitly out of scope.

## 1. Decision

Adopt the useful operating patterns, not the article's exact product stack.

The Agency OS remains the sole business control plane and source of truth. PostgreSQL owns business records, permissions, approvals, execution state, artifacts and audit. Agents prepare typed drafts and recommendations; backend policy decides whether an action may proceed; the founder approves protected actions; external effects are recorded and reconciled.

Do not add Hermes, Twenty, Invoice Ninja, Firefly III, Akaunting, Chatwoot, Typebot, Qdrant, Langfuse, Mattermost, Ntfy, Cal.com or another orchestration platform merely to reproduce the article. Reconsider a provider only when a specific integration gap is demonstrated and its security, licensing, operational cost and data path are reviewed.

## First implementation tranche — integrated branch, pending CI

The current consolidation branch now contains the first OS-side Private Operations foundation: workspace-scoped versioned knowledge records with source/provenance and classification metadata; founder-authorized knowledge approval; sanitized, source-linked business drafts for front-desk enquiries, meeting-to-proposal preparation and receivables follow-up; read-only receivables aging grouped by currency; a read-only founder count snapshot; audit events; and a Founder Console page with workspace selection and source-record pickers.

The new tables use forced PostgreSQL RLS. Human OS/API access is workspace-scoped. The worker role is explicitly excluded from policy predicates and has all table privileges revoked until a separately designed and tested execution-capability integration exists. This avoids relying on caller-set machine/user GUCs for worker authorization. The migration depends on security revision `e8a1c3d5f7b9`.

This tranche does not generate model content, invoke Claude, send messages, issue proposals/invoices, execute payments, ingest binary files or transcripts, run retention cleanup, or perform external actions. Those capabilities remain planned and require their own lifecycle, approval and integration evidence.

## 2. Patterns worth adopting

### A. Governed business knowledge layer

Create a versioned, workspace-scoped knowledge layer for approved business facts and operating policy. Initial logical collections:

- Services: service descriptions, ideal client profiles, FAQs and approved case studies.
- Commercial: approved price catalogue, discount rules, margin floors and proposal templates.
- Delivery: discovery, onboarding, handoffs, QA, release and support playbooks.
- Client context: client-specific facts, project history, decisions and payment terms, strictly workspace-scoped.
- Governance: access rules, retention, data classes, runtime eligibility and explicit "AI must not do" rules.
- Reporting: KPI definitions, measurement methods and brief templates.

Every item needs an owner, workspace/client scope, classification, source/provenance, version, effective dates, approval state and retention policy. Retrieval must enforce the caller's access rights before content is returned. Drafts and unapproved facts must not silently become authoritative knowledge.

Start with structured PostgreSQL records and controlled document metadata. Add file/object storage and retrieval indexing only after the upload, malware scanning, extraction, DPG, ACL-filtered retrieval, deletion and re-index lifecycle is designed and tested. A vector database is an optional retrieval adapter, never the authority for permissions or canonical content.

Re-indexing is event-driven from committed, versioned knowledge changes. It is idempotent and reconciled; stale indexes are detectable. Deleting or revoking a source must invalidate derived chunks and embeddings under the same workspace policy.

### B. Front desk and lead response preparation

Extend the Revenue Engine around the existing signed website lead-intake boundary and CRM records:

1. Persist and deduplicate the inbound enquiry with source/channel, consent/provenance and correlation ID.
2. Retrieve only approved public business knowledge and the specific lead's authorized context.
3. Draft a short response, qualification questions, fit rationale and suggested next action.
4. Record evidence/source references and confidence; unknown facts become a handoff, not a guess.
5. Route sensitive cases, complaints, existing-client issues, high-value opportunities and requests for a human to the founder.
6. Any outbound message must pass sender authorization, consent/suppression, contact-window, rate-limit, idempotency and stop-on-reply/opt-out/bounce controls. Until the dispatch path is implemented and tested, the OS only prepares drafts.

The article's proposed automatic booking and instant replies are not adopted as defaults. Calendar booking and routine sends require a separately approved policy and tested integration.

### C. Meeting notes to proposal draft

Add a governed preparation path, not autonomous commercial commitment:

1. Ingest an explicitly authorized transcript or notes artifact; default to transcript-only and do not record meetings without consent and policy approval.
2. Extract client, decision maker, scope, quantities, budget as stated, timeline, preferences, dependencies and red flags into a typed schema. Missing facts remain null.
3. Link every extracted statement to a transcript span/source reference where available.
4. Compare scope against the versioned service catalogue, pricing rules and approved proposal examples.
5. Generate a proposal revision with line-item provenance, assumptions, exclusions, timeline, margin estimate and unresolved questions.
6. Flag below-floor margin, unsupported line items, unclear scope and contractual exceptions.
7. Require founder approval for pricing, proposal issue, contract terms and client delivery.

Won proposals may be retrieval examples for structure and tone only. They do not authorize copying client-confidential information or reusing historical prices. Current approved catalogue and policy remain authoritative.

### D. Receivables and payment operations

Build on the existing invoice register and append-only payment receipt ledger. This is agency receivables visibility, not statutory accounting.

- Draft invoice data from the approved proposal/contract and persisted delivery evidence; preserve the commercial source of every line item.
- Require founder approval before issue or sending.
- Track due dates, payment status, partial receipts, unmatched transactions, reminder history and overdue exceptions.
- Prepare reminders from approved templates and client relationship context. Complaints, disputes, overdue-sensitive relationships, fees, write-offs, refunds and payment commitments escalate to the founder.
- Bank/payment matching should produce a proposed match with evidence and confidence. Ambiguous, partial, duplicate or unmatched receipts go to review; do not mark paid on a weak match.
- External payment and accounting systems remain adapters. Persist provider IDs and reconcile provider state back into OS records.

The article's confidence threshold (0.98), fixed reminder days and 07:00 schedule are examples, not adopted policy. Thresholds, schedules, currencies, legal requirements and accounting treatment must be configured and validated for the agency's actual jurisdiction and contracts.

### E. Founder daily brief and operating queue

Produce a concise founder brief from persisted OS records, with a traceable as-of timestamp and links to source records:

- New enquiries and qualified opportunities, including top items and why they rank.
- Proposal drafts awaiting review, sent proposals and signed work.
- Delivery health: blocked tasks, milestone risk, scope changes and QA/release exceptions.
- Receivables: approved/sent invoices, receipts, overdue items and unmatched payments.
- Founder approvals, security exceptions, failed executions and provider/integration health.
- One evidence-backed recommended action, clearly labelled as a recommendation.

This is a read model over OS-owned records, not a second ledger. Missing or stale data must be disclosed; the brief must not invent a KPI or imply a payment/deployment occurred without persisted confirmation.

## 3. Hosted model routing and data eligibility

The Agency OS will use approved hosted model providers only. Do not add Ollama, local model serving, local inference, hybrid local routing or a local-AI fallback.

Provider selection is a governed adapter decision, not a way around the Data Protection Gateway:

- Public/synthetic data may use an explicitly approved external provider.
- Commercial/client-confidential data may use only a hosted runtime and contract explicitly approved for that data class and client.
- Restricted data is blocked unless a specific hosted provider/runtime is explicitly eligible under client policy and verified contractual/security controls.
- If no eligible hosted runtime exists, stop and request a human decision; never silently fall back to another provider.
- Record provider/model, policy decision, data class, prompt/template version, token/cost metadata where available, result reference and audit correlation. Never log raw secrets or unnecessary client content.

A hosted provider is not automatically approved merely because it is configured. Verify data-processing terms, retention/training controls, region, access, egress, observability, support access and client authorization before sending client data. The DPG and tenant authorization remain mandatory for every provider call.

## 4. Runtime and automation boundaries

- The OS remains the orchestrator of record: Agent Registry, tasks, executions, approvals, budgets, sessions, artifacts, audit and outbox.
- Python workers handle controlled, durable jobs. The existing outbox handles integration intent with at-least-once delivery, idempotency, bounded retries, dead letters and reconciliation.
- An external workflow tool may be evaluated for integration glue only. It cannot write core tables, make authorization decisions, own business state or bypass approval.
- A Hermes-like agent orchestrator is not required. If ever evaluated, it must sit behind the runtime adapter and cannot become a parallel control plane.
- Observability should use OS execution/audit records first. A tracing product is optional and must receive only minimized, policy-eligible metadata.

## 5. Approval and stop policy

Always require founder approval for proposals/quotes/contracts, price or discount exceptions, invoices before issue, payments/refunds/write-offs, sensitive client messages, new access to client files, production releases, destructive actions and permission/security changes.

Stop and escalate on client complaint, opt-out, bounce, disputed/partial/unmatched payment, low margin, unsupported price/scope, missing source, uncertain identity, policy denial, data-class mismatch, budget exhaustion, provider timeout with ambiguous outcome or repeated execution failure.

Routine internal preparation can be automated only when explicitly allowlisted and authorized. A prompt instruction is never the enforcement boundary.

## 6. Delivery sequence

1. **Knowledge foundations:** define schema/ownership/versioning/classification/ACL and "AI must not do" policy. Start with structured records; no general file ingestion yet.
2. **Front desk draft path:** connect signed lead intake to knowledge-grounded qualification drafts and founder exception routing; no auto-send.
3. **Meeting-to-proposal:** transcript consent/retention, typed extraction, provenance, proposal revision and margin flags; founder approval remains mandatory.
4. **Receivables:** invoice source linkage, reminder drafts, receipt matching proposals and reconciliation; no payment execution or autonomous write-off.
5. **Founder brief:** source-backed daily summary and unified exception queue.
6. **Hosted provider governance:** inventory approved hosted providers, data-processing terms, retention/training controls, regions, access and client eligibility; fail closed when no eligible provider exists.

Each stage requires additive PostgreSQL migration review, API authorization, cross-workspace negative tests, audit/outbox behavior, idempotency/recovery tests, Founder Console workflows, synthetic end-to-end evidence and a rollback plan. Existing persistent databases and volumes must not be reset or migrated without explicit approval, backup and recovery path.

## 7. Explicit non-goals

- Replacing the OS with a 26-agent bundle or a collection of independent business apps.
- Claiming local-only/private processing before verifying the full data path.
- Autonomous proposal/contract issue, pricing commitments, payment execution or sensitive outreach.
- Replacing statutory accounting, tax, payroll or legal review.
- Adding vector search, file upload, telephony, meeting recording or external workflow infrastructure before the security lifecycle is ready.
- Measuring success by agent count, message volume or dashboard activity instead of agreed client outcomes.

## Source and interpretation

Source: ReStructure Brief, "The Private AI Operating System" (reviewed 2026-11-28). The source describes a proposed local-first stack and example workflows for front desk, proposals and payments. Its stack choices, numeric thresholds, performance targets and claims are not independently validated here and are not adopted as Agency OS requirements. The design above is a selective adaptation constrained by the Agency OS's existing architecture, security policy and implementation status.
