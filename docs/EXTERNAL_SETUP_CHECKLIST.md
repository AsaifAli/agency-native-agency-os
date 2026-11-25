# External configuration and founder setup checklist

**Purpose:** Consolidate the account, credential, domain and operational tasks that cannot be completed safely from repository code alone.

**Important:** This checklist does not mean the OS is production-ready. Some code-side gates remain open and are marked below. Do not enable client data, outbound communication, live calling, payment execution or production autonomy merely because credentials have been added.

## 1. Founder decisions and access

- [ ] Confirm the production organization and workspace IDs; keep development/staging separate.
- [ ] Provision Authentik and create the confidential OIDC provider/client using `docs/AUTHENTIK_SETUP.md`; register the exact `/v1/auth/callback` URI.
- [ ] Configure verified-email mapping (Authentik 2025.10+ defaults `email_verified` to false) and a real verification process.
- [ ] Configure phishing-resistant MFA for founder/admin in Authentik; add the `agency_os_assurance` OIDC scope mapping and verify the actual flow emits the exact `OIDC_REQUIRED_ACR` claim before considering MFA closed.
- [ ] Inject OIDC issuer, client ID/secret, independent state secret, redirect URI and frontend URL into the secret manager. Do not commit these values.
- [ ] Provision the founder identity and verify explicit Founder Authority separately from organization-owner membership.
- [ ] Decide approved sender identities, business contact hours, communication channels and escalation destination.
- [ ] Approve the initial service catalogue, ICPs, pricing boundaries and proposal approval rules.
- [ ] Define data classes allowed for each AI runtime and provider.

## 2. Website lead intake bridge

**Code status:** Website forwarding/admin retry and OS signed intake are implemented; the bridge remains disabled pending configuration and end-to-end validation.

- [ ] Apply the OS database migrations in the target environment.
- [ ] Apply the website Supabase migrations in the target environment.
- [ ] Configure the same high-entropy bridge secret on the website server-side runtime and OS API secret store; never expose it to browser code.
- [ ] Configure the fixed organization/workspace mapping on the OS side.
- [ ] Configure HTTPS origins, allowed request sizes, rate limits and Turnstile keys where enabled.
- [ ] Submit synthetic enquiries and verify signature rejection, timestamp/replay rejection, idempotent retries, deduplication, audit and outbox persistence.
- [ ] Confirm website responses expose only a safe acknowledgement/correlation ID.
- [ ] Keep the bridge disabled until all checks pass.

## 3. AI runtime

**Code status:** Mock runtime and a constrained Managed Agents adapter exist. Live account, environment and provider compatibility are not validated; Claude Agent SDK fallback and OS MCP gateway are not implemented.

- [ ] Confirm Anthropic account/project, billing and Managed Agents availability.
- [ ] Create a dedicated non-production environment with minimal permissions and restricted egress.
- [ ] Verify pre-created Agent configuration has no unapproved tools, MCP servers, skills or multi-agent access.
- [ ] Configure runtime credentials in the secret manager.
- [ ] Run synthetic-only session create/resume/timeout/cancel/reconciliation tests.
- [ ] Do not route confidential client data until runtime eligibility, data processing terms, retention and workspace isolation are reviewed.

## 4. Telephony / AI calling

**Code status:** Call and transcript records plus provider-neutral boundary exist. Live media service, signed provider webhooks, consent evidence lifecycle, provider adapter implementation and real-time STT/TTS are not complete.

- [ ] Select a telephony provider only after country coverage, local number availability, data residency, subprocessors, retention, security and pricing review.
- [ ] Obtain the approved inbound agency number and configure routing to a non-production endpoint first.
- [ ] Configure webhook signing secret and verify timestamp, replay and event deduplication behavior.
- [ ] Confirm AI identity disclosure and recording/transcription notices.
- [ ] Keep recording disabled until consent and retention requirements are reviewed.
- [ ] Validate India and target-market telecom, consent, DND and AI-call rules with the provider and qualified counsel.
- [ ] Start with synthetic/internal inbound calls and human transfer; do not enable cold outbound calling.
- [ ] Enable callbacks only after a complete consent-evidence model, suppression checks, contact windows, rate limits, founder stop control and audit pass.
- [ ] Configure per-call and daily usage budgets and an emergency disable mechanism.

## 5. Email, calendar and publishing

**Code status:** Governed dispatch, reply/opt-out/bounce processing and campaign workflows are not yet implemented end to end.

- [ ] Select an email provider and configure verified sending domain, SPF, DKIM and DMARC.
- [ ] Create least-privilege API credentials and webhook signing secrets.
- [ ] Configure a calendar provider and dedicated booking calendar.
- [ ] Configure social publishing integrations only after draft review and approval workflows are implemented.
- [ ] Keep outbound sending and publishing disabled until sender authorization, suppression, reply/opt-out/bounce stop logic, idempotency and audit are tested.

## 6. Payments and finance

**Code status:** Project cost/time foundations exist; invoice, receivable and payment reconciliation workflows remain incomplete.

- [ ] Select payment provider and business account only after legal, fee and supported-country review.
- [ ] Configure webhook signing and settlement notification credentials.
- [ ] Define invoice numbering, tax fields, currency and accounting handoff with an accountant.
- [ ] Keep payment execution, refunds, write-offs and autonomous collection actions disabled until approval and reconciliation code is complete.
- [ ] Never store card or bank credentials in the OS.

## 7. Storage, observability and recovery

**Code status:** Private artifact storage, complete retention/deletion lifecycle, production alerting and tested restore evidence remain incomplete or unverified.

- [ ] Provision private object storage with encryption, scoped access and lifecycle policies.
- [ ] Configure KMS/secret manager and credential rotation.
- [ ] Configure error monitoring, logs, metrics, traces and alert routing; redact PII and secrets.
- [ ] Configure encrypted database and object backups.
- [ ] Perform a restore drill in an isolated environment and record actual RPO/RTO.
- [ ] Configure production/staging separation, resource quotas and restricted egress.
- [ ] Verify domain, TLS, DNS, firewall and deployment secrets.

## 8. Code-side gates still required before client-ready operation

These are **not** external setup tasks and cannot be closed by entering credentials:

- [ ] Full cross-workspace authorization tests across APIs, workers, sessions, files and caches; PostgreSQL RLS review.
- [x] Authentik OIDC code path, verified issuer/subject account binding, HttpOnly session cookie and CSRF protection are implemented.
- [ ] Live OIDC/JWKS/MFA assurance (`acr`/`amr`), token revocation and actual browser session lifecycle verification.
- [ ] Data Protection Gateway, PII minimization/redaction and retention/deletion implementation.
- [ ] OS MCP gateway and narrowly scoped tools for agents.
- [ ] Outbound email dispatch, sender registry, consent provenance, suppression, reply/opt-out/bounce stop, idempotency and audit.
- [ ] CRM relationship activities/timeline, source evidence and duplicate review/merge workflow.
- [ ] Proposal/estimate/SOW and contract approval lifecycle.
- [ ] Invoice/receivable and payment reconciliation workflows.
- [ ] AI telephony real-time media service, provider adapter, signed webhooks, consent-evidence lifecycle and synthetic evaluation.
- [ ] Client onboarding, acceptance, support and renewal workflows.
- [ ] Production outbox consumers, worker crash/restart recovery, monitoring, backup restore and end-to-end synthetic journey.

## 9. Safe first activation order

1. Development/staging identity and founder authority.
2. Synthetic website lead intake.
3. Synthetic CRM and delivery journey.
4. Internal-only AI runtime tests with public/synthetic data.
5. Inbound telephony with synthetic/internal callers and human transfer.
6. Founder-approved, consented callback workflow after legal/provider review.
7. Approved email sending after all dispatch and suppression gates pass.
8. Client data only after security, privacy, recovery and workspace-isolation acceptance.

**Never interpret an unchecked item as implicitly complete. Record the configuration owner, environment, verification evidence and date for each completed item.**
