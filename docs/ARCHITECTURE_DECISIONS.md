# Architecture decision register

This register freezes the choices for the current Agency OS build. Revisit only when evidence shows a real limitation.

| Decision | Chosen approach | Reason / constraint |
|---|---|---|
| Product | Private founder-controlled Agency OS | Not a SaaS product |
| Frontend | Next.js Founder Console | Internal operator interface |
| Backend | FastAPI modular monolith | Fewer deployment and security boundaries to operate |
| Database | PostgreSQL | Canonical business state and transactional outbox |
| Async work | Native durable workers | Persisted execution lifecycle and recovery |
| Workflow engine | None initially | Native state machines/outbox are sufficient until proven otherwise |
| Redis | Optional, not source of truth | Add only for measured queue/cache need |
| AI runtime | Adapter-based | Keep provider replaceable; enforce data eligibility |
| Voice | Provider-neutral PSTN/SIP adapter | Both inbound and outbound calling; no browser voice |
| Telephony media | Separate real-time service boundary | Do not run real-time media in ordinary API workers |
| Website | Separate app, later integration | Public website cannot reach private OS database |
| Website chatbot | Deferred | No generic chatbot in current scope |
| CRM | Native OS domain | Avoid duplicate CRM and split relationship history |
| Finance | Agency management ledger | Not statutory accounting or payroll |
| Evaluation | OS-owned evaluation service | Reuse generic harness primitives, no separate platform |
| Deployment | Docker Compose first | No Kubernetes absent demonstrated need |
| Client isolation | Workspace-scoped records and artifacts | One founder does not remove client confidentiality obligations |

## Operational rules

- PostgreSQL owns business truth, permissions, approvals, execution records and audit.
- Provider services own only their external provider-side objects; store provider IDs and reconcile outcomes into the OS.
- No external worker or automation tool writes core database tables directly.
- Every external side effect has authorization, idempotency, bounded retries and reconciliation.
- No provider/runtime is eligible for a data class merely because it is technically available.
- Existing legacy integration snapshots are migration references, not separately deployed products.
- Do not enable n8n or another automation platform as part of this baseline.
- Do not enable real telephony until provider, consent, webhook, retention and recovery controls pass the acceptance tests.
