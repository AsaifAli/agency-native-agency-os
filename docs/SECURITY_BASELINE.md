# Security baseline — mandatory before client workloads

- Authentication: OIDC/JWKS with MFA-capable identity provider; short-lived sessions; service identities for workers and n8n.
- Authorization: tenant-scoped RBAC plus ABAC policy checks on every resource and action; deny by default.
- Data protection gateway: classify, minimize and redact data; enforce runtime eligibility before sending data to any model provider.
- Runtime routing: Claude Managed Agents only for eligible data. ZDR/BAA-required workloads must use a separately verified eligible route.
- Approval enforcement: backend policy blocks protected side effects until a valid, scoped approval is recorded. Requester cannot approve their own request.
- Secrets: vault/KMS-backed encryption, rotation and scoped credentials. Never store `.env`, API keys or tokens in Git, prompts, logs or artifacts.
- Execution: isolated worker sandboxes, resource quotas, restricted network egress, safe file handling and per-tenant artifact access.
- Lifecycle: session expiry, retention policy, deletion workflows and cleanup of object-store artifacts.
- Audit: append-only/tamper-evident records for access, processing, policy, approvals, runtime routing, security events and usage.
- SDLC: protected branches, CI, unit/integration/E2E tests, SAST, dependency/container/IaC scans, SBOM, backups and restore drills.
- n8n: private network, authenticated webhooks, per-tenant credentials, versioned workflows and audited activation.
