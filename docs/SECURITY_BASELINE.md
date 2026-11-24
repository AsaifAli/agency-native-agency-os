# Security baseline — mandatory before client workloads

- Authentication: OIDC/JWKS with MFA-capable identity provider; short-lived sessions; service identities for workers and provider adapters.
- Authorization: tenant-scoped RBAC plus ABAC policy checks on every resource and action; deny by default.
- Data protection gateway: classify, minimize and redact data; enforce runtime eligibility before sending data to any model provider.
- Runtime routing: Claude Managed Agents only for eligible data. ZDR/BAA-required workloads must use a separately verified eligible route.
- Founder authority: an explicit `FounderAuthority` grant is separate from organization `Role.owner`; organization ownership alone cannot approve protected actions. Grants are provisioned through trusted bootstrap/CLI only.
- Approval enforcement: only an active Founder Authority identity can approve protected side effects. A founder may approve an action they initiated; non-founders cannot approve their own requests. The protected action must consume the scoped approval atomically with its action intent/outbox record.
- Secrets: vault/KMS-backed encryption, rotation and scoped credentials. Never store `.env`, API keys or tokens in Git, prompts, logs or artifacts.
- Execution: isolated worker sandboxes, resource quotas, restricted network egress, safe file handling and per-tenant artifact access.
- Lifecycle: session expiry, retention policy, deletion workflows and cleanup of object-store artifacts.
- Audit: append-only/tamper-evident records for access, processing, policy, approvals, runtime routing, security events and usage.
- SDLC: protected branches, CI, unit/integration/E2E tests, SAST, dependency/container/IaC scans, SBOM, backups and restore drills.
- External providers: signed webhooks, replay protection, scoped credentials, egress allowlists and audited configuration.
