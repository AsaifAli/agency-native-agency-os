---
name: claude-runtime-engineering
description: Implement Claude API or Managed Agents integrations through current official documentation, explicit adapter contracts, and fail-closed runtime eligibility checks.
---
# Claude Runtime Engineering

Use when changing Anthropic API, Claude Agent SDK, or Managed Agents integration.

1. Identify the exact API product and version. Do not conflate Claude Code, Claude Cowork, Claude API, Agent SDK, and Managed Agents.
2. Read current official documentation and SDK types for the selected API before writing code.
3. Keep provider-specific requests and responses behind the existing runtime adapter. OS records remain authoritative.
4. Persist OS execution/session intent before external work; use idempotency and reconciliation for ambiguous provider outcomes.
5. Apply data classification and runtime eligibility before dispatch. Never send client or confidential data to a runtime unless policy and contractual eligibility are verified.
6. Keep tools, MCP servers, skills, subagents, filesystem access, and network egress disabled unless each has a reviewed OS-owned authorization path.
7. Bound duration, concurrency, token/cost budgets, retries, and cancellation. Persist sanitized status and provider identifiers.
8. Treat provider events as untrusted input. Validate schema, correlate to the correct execution, and make handlers idempotent.
9. Do not report success until the OS has persisted a terminal result and required evaluations have passed.
10. Document beta limitations and unsupported features. Managed Agents is a beta product; do not claim ZDR or HIPAA BAA eligibility.

If the provider cannot satisfy the adapter contract safely, fail closed and retain the mock/runtime-independent path.
