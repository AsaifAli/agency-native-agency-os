# Revenue Agent Research Capture and Founder Review

## Purpose

The Revenue Engine can capture public-source company research as a durable draft without creating a CRM lead, contact, or outbound message. The founder decides whether the draft is suitable for CRM promotion.

## Agent tool

- Tool key: `revenue.lead.research.capture`
- Version: `1.0.0`
- Risk: `write_draft`
- Eligible data class: `public` only
- Required grants: `tools:invoke` and `tool:revenue.lead.research.capture`
- Requires a machine identity and active public-data session.

Required input:
- Company name and concise research summary.
- 1–10 source references, each a public HTTPS URL.
- Fit and confidence scores (0–100).
- Optional buying signals and risks.

The schema rejects contact fields and arbitrary extra properties. It rejects non-HTTPS, localhost, private/local hostnames and private/reserved IP source references. The OS stores source URLs supplied by the research agent; it does not fetch or independently verify those sources in this tool.

All input is passed through the Data Protection Gateway before schema validation and persistence. Secret-like values are blocked and PII patterns are redacted. The draft stores the machine identity, workspace, source references, scores, evidence, idempotency key and review status. It does not store email addresses, phone numbers or contact records.

## Founder-controlled workflow

1. An authorized machine identity captures a public research draft.
2. The draft is stored with status `pending_review`; no CRM lead or contact is created.
3. Founder Authority lists and reviews pending drafts.
4. The founder explicitly approves or rejects the draft. Review notes pass through DPG.
5. Only an approved draft can be promoted.
6. Promotion creates a CRM lead and its `LeadResearchRecord` in one database transaction, attributes the CRM creation to the approving founder, marks the draft `promoted`, and writes an audit event.
7. Repeated promotion requests return the existing lead rather than creating a duplicate.

No step sends email, calls prospects, adds contact details, changes consent, or dispatches external communications.

## Founder API

- `GET /v1/orgs/{org_id}/workspaces/{workspace_id}/lead-research-drafts`
- `POST /v1/orgs/{org_id}/workspaces/{workspace_id}/lead-research-drafts/{draft_id}/review`
- `POST /v1/orgs/{org_id}/workspaces/{workspace_id}/lead-research-drafts/{draft_id}/promote`

All three routes require Founder Authority in the target organization. Promotion is separate from approval so review and CRM creation remain explicit actions.

## Remaining work

- [x] Founder review and promotion UI added at `/research-drafts` in PR #37; frontend build verification remains pending.
- Add approved public-source research connectors/agent workflows; this tool itself does not browse or verify sources.
- Add broader company deduplication across different source references.
- Add client-specific data policy and runtime eligibility before any commercial/client data is admitted.
- Add controlled Revenue tools for CRM updates, opportunity creation and proposal preparation.
- Keep outbound communication, pricing, contracts and payments behind their existing approval and suppression controls.
