# Business lifecycle and canonical record map

This document defines how the final domains connect. It is a target contract; it does not claim every listed module is implemented in the current source.

## Revenue lifecycle

```text
Enquiry / Research
    -> Lead + Contact
    -> Qualification
    -> Opportunity
    -> Discovery
    -> Proposal / Quotation / SOW
    -> Negotiation
    -> Won / Lost / Nurture
    -> Client onboarding (when won)
```

Canonical relationships:
- `InboundEnquiry` records the original submission and provenance.
- `Lead` represents a potential engagement and owns qualification/stage.
- `Contact` represents a person and may be associated with a `Client`.
- `Opportunity` represents a commercial engagement, value, probability and expected close.
- `Interaction`/relationship timeline links emails, calls, meetings, notes and decisions.
- `ProposalVersion` records each proposal revision and approval/send state.
- `ConsentRecord` and `SuppressionRecord` govern communication eligibility.

A lead can exist without a client. A client is created/activated only when the relationship is established. Never duplicate a person merely because a new enquiry or call arrives; link to an existing record when the match is verified.

## Telephony lifecycle

```text
Authorized call request / inbound provider event
    -> Call session created
    -> Provider event verification + deduplication
    -> Ringing / answered / in-progress / completed / failed
    -> Transcript artifact (if permitted)
    -> Summary + structured extraction
    -> Relationship timeline entry
    -> Follow-up task / founder review
```

- Provider event IDs and idempotency keys prevent duplicate state transitions.
- Inbound and outbound calls use the same canonical call record with direction-specific authorization.
- Outbound requests require consent/provenance and suppression checks before the provider is called.
- A call record is not proof that a call was actually placed or answered.
- A transcript is not the same as a summary; retain provenance and review status separately.
- Human handoff, provider failure, no-answer and voicemail are explicit outcomes.

## Delivery lifecycle

```text
Won opportunity
    -> Client onboarding
    -> Discovery + requirements
    -> Solution design
    -> Project + milestones + tasks
    -> Engineering + review
    -> QA/security + acceptance
    -> Approved deployment
    -> Handover + support/maintenance
```

Every requirement should have a stable identifier and links to its design decision, implementation task, test evidence and handover item. Scope changes require an impact assessment and approval when commercial scope or price changes.

## Commercial and finance lifecycle

```text
Opportunity estimate
    -> Approved proposal / SOW
    -> Project budget
    -> Invoice / receivable record
    -> Payment / expense record
    -> Provider and direct-cost allocation
    -> Project margin and cash visibility
```

All monetary values use integer minor units and ISO currency codes. Do not add different currencies together without an explicit conversion record and timestamp. Financial summaries are management views, not statutory books.

## Support lifecycle

```text
Client issue
    -> Ticket / incident
    -> Severity + owner + workspace
    -> Investigation + activity history
    -> Resolution + evidence
    -> Client communication
    -> Closure / follow-up / recurring maintenance
```

Client support data is always scoped to the correct client workspace. Private project details must not be disclosed to an unverified caller or contact.

## Canonical timeline

The relationship timeline is a read model over canonical records, not a second editable CRM. Each entry references its source record, actor, timestamp, workspace, visibility classification and correlation ID. Edits to source records remain auditable.
