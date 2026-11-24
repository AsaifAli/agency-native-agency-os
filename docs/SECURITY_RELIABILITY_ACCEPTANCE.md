# Security, reliability and operational acceptance gates

Use this checklist before moving any workflow from synthetic development data to real client data or production side effects.

## Identity and authorization
- [ ] Production OIDC/JWKS validation and MFA-capable identity provider configured.
- [ ] No development token fallback in production frontend or backend.
- [ ] Founder-wide authority is distinct from organization owner membership.
- [ ] Service identities are scoped by workload, organization/workspace and permitted actions.
- [ ] Cross-workspace access denied for APIs, workers, files, transcripts, object storage and caches.
- [ ] PostgreSQL row-level security or equivalent database safeguards tested with non-owner credentials.
- [ ] Only explicit active Founder Authority can approve; organization owner role alone is insufficient.
- [ ] Founder can approve a founder-initiated action; non-founder self-approval is rejected.
- [ ] Approval is consumed atomically with protected action intent/outbox persistence.

## Approval and external actions
- [ ] Approval is consumed atomically with the protected action.
- [ ] Protected endpoint tests cover missing, expired, wrong-scope, replayed and already-consumed approvals.
- [ ] Outbound email/calls enforce consent, suppression, time window and rate limits.
- [ ] Replies, opt-outs, bounces and complaints stop follow-ups.
- [ ] Pricing, proposal/SOW send, contract, payment, production release and destructive action require approval.
- [ ] Provider calls occur outside database transactions and have idempotency/reconciliation.

## Data protection
- [ ] Data classes and client policy are enforced server-side.
- [ ] PII minimization/redaction is tested before provider dispatch.
- [ ] Runtime eligibility and client authorization are checked for every execution.
- [ ] Secrets are stored in a secrets manager/KMS and rotated; no secrets in Git, logs, prompts or artifacts.
- [ ] Recordings are disabled unless consent and retention policy are approved.
- [ ] Transcript/recording access is audited; export/deletion/expiry works end-to-end.
- [ ] Backup retention and deletion policy are documented, including legal hold where relevant.

## Execution and events
- [ ] Outbox event is committed with business mutation in one transaction.
- [ ] Dispatcher uses safe claiming, leases, heartbeats and bounded retry.
- [ ] Consumers are idempotent; duplicate and out-of-order events are tested.
- [ ] Dead-letter review, replay and reconciliation procedures exist.
- [ ] Cancellation, lease expiry, worker crash and provider timeout are tested.
- [ ] Execution duration, concurrency, token/provider cost and file size are bounded.

## Telephony
- [ ] Provider supports intended Indian inbound/outbound use and caller ID requirements.
- [ ] Signed webhook verification, timestamp validation and replay protection pass tests.
- [ ] Call authorization checks consent/provenance and suppression before dialing.
- [ ] Provider status callbacks are idempotent and reconciled.
- [ ] Caller disclosure, recording/transcription consent and human handoff are verified.
- [ ] Transcript and summary are stored separately with provenance and confidence.
- [ ] Call failure, no answer, voicemail, transfer and duplicate webhook cases are tested.

## Operations
- [ ] Separate dev/staging/production configuration and secrets.
- [ ] CI runs lint/type checks, unit/integration tests, dependency and security scans.
- [ ] SBOM generated for releases; container/image scanning enabled.
- [ ] Structured logs, metrics, traces and alerts cover API, worker, provider and database failures.
- [ ] Encrypted backups and offsite copy configured; restore drill completed and timed.
- [ ] Database migrations tested against a production-like PostgreSQL version and backup restored in a test environment.
- [ ] RPO/RTO documented and recovery runbook exercised.
- [ ] Incident register and operational runbooks exist.
- [ ] Deployment has health checks, rollback and release evidence.

## Readiness labels
- **Implemented:** source code exists.
- **Tested:** automated or manual test evidence exists.
- **Externally configured:** provider/account/configuration is complete.
- **Validated:** end-to-end behavior and recovery are demonstrated in the target environment.
- **Production-ready:** all mandatory security, reliability, operational and business acceptance gates have evidence.

Never promote a capability to a stronger label without evidence.
