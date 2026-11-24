# Security and Data Handling

## Defaults
- Public/synthetic data only until policy and runtime eligibility explicitly permit more.
- No secrets in prompts, logs, Markdown, code, tickets or artifacts.
- No cross-organization or cross-workspace access.
- No provider-side tools, MCP, filesystem or network access without OS-owned authorization.

## Required controls
- Data Protection Gateway: classify, minimize, redact and check runtime eligibility.
- Tenant Security Manager: enforce RBAC/ABAC, tenant/workspace scope and least privilege.
- Session Lifecycle Manager: retention, expiry, deletion, cleanup and recovery.
- Sandboxes: restricted egress, safe file handling and resource limits.
- Audit: tamper-evident events for access, decisions, execution and protected actions.

## Incident behavior
Stop the affected execution, preserve sanitized evidence, revoke affected credentials through the approved path, notify the responsible supervisor and founder, and follow incident response procedures. Do not destroy evidence or silently retry a suspected security incident.
