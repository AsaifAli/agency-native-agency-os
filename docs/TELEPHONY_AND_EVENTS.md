# Telephony and event foundation

## Current behavior

- `CallSession` stores inbound/outbound call records, CRM associations, provider references, consent status, outcome and summary.
- `CallTranscript` stores transcript text with language, source and redaction-review status.
- Authenticated APIs are scoped by organization and workspace.
- Call and transcript mutations create audit records and `OutboxEvent` rows in the same database transaction.
- `UnconfiguredTelephonyProvider` fails closed. It does not place calls or report fake success.
- The Founder Console has a read-only call-history page.

## API

- `GET /v1/orgs/{org_id}/telephony/calls?workspace_id=...`
- `POST /v1/orgs/{org_id}/telephony/calls`
- `PATCH /v1/orgs/{org_id}/telephony/calls/{call_id}`
- `POST /v1/orgs/{org_id}/telephony/calls/{call_id}/transcripts`
- `GET /v1/orgs/{org_id}/telephony/calls/{call_id}/transcripts`

Call creation records intent only. An outbound record starts as `planned`; an inbound record starts as `queued`. This API does not dial, answer, record audio, run speech recognition, or invoke an agent.

## Required before live telephony

1. Select a provider with Indian number availability, inbound routing, outbound caller ID, SIP/WebRTC support, signed webhooks, call status events, recording controls and exportable billing records.
2. Implement provider adapter and webhook signature verification. Verify timestamp, signature, provider account and event replay/idempotency before processing callbacks.
3. Add outbound authorization: consent/provenance, suppression and do-not-call checks, local time windows, rate limits, approved caller IDs and backend approval for sensitive calls.
4. Add inbound routing, caller identification and safe handoff to the founder.
5. Add speech-to-text and conversation extraction behind provider-neutral interfaces. Do not send confidential client data to a runtime until data-classification and provider eligibility policy permits it.
6. Implement recording disclosure/consent and store recordings only in private object storage. The database stores an object key, never a public URL.
7. Add retention, transcript redaction, access audit, deletion and export workflows before storing real client conversations.
8. Build a durable outbox dispatcher with row claiming/leases, bounded retries, idempotent consumers, dead-letter handling and reconciliation. The current release persists outbox events but does not dispatch them.
9. Add PostgreSQL concurrency, replay, webhook-signature and cross-workspace security tests.

## Outbox contract

Each event has an event ID, event type, schema version, organization/workspace scope, aggregate type/ID, idempotency key and JSON payload. Business record and event are committed in one transaction. Delivery is intended to be at-least-once; consumers must be idempotent. Exactly-once external side effects are not promised.

## Suggested provider-neutral voice architecture

Telephony provider (PSTN/SIP) -> signed webhook/media bridge -> voice session adapter -> speech/LLM/TTS providers -> authenticated OS actions -> call record/transcript/outbox -> CRM timeline.

A LiveKit Agents integration is a candidate for the media/agent layer, not yet installed or configured. A telephony carrier/provider remains a separate choice. Do not add multiple voice frameworks.
