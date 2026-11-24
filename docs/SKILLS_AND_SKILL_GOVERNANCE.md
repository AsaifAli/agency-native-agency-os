# Skills Library and Governance

## Purpose

The OS ships a curated, version-pinned library of reusable agent instructions in the open Agent Skills directory format. Skills are operating procedures and specialist knowledge; they are not identities, permissions, tools, workflows, or runtime sessions.

The curated set contains 18 cross-functional skills for planning, engineering, Revenue, Delivery, finance, communication, governance and quality. It adapts useful patterns from Superpowers, Matt Pocock's skills, Everything Claude Code (ECC), Karpathy Guidelines, Ponytail, Anthropic's Agent Skills, and CodeRabbit's skills. The Claude Skills Hub is treated as a discovery index only. See skills/catalog.json for exact source revisions, licenses, intended use, and role recommendations.

## What is included

- Planning and clarification: grill-before-building.
- Engineering discipline: test-driven-development, systematic-debugging, karpathy-engineering-discipline, ponytail-minimal-change, research-first-engineering.
- Independent quality: independent-code-review and release-readiness.
- Governance and runtime: secure-skill-admission, risk-and-policy-review and claude-runtime-engineering.
- Revenue and client work: market-research-briefing, client-discovery-requirements, proposal-sow-drafting, client-communication-drafting, marketing-content-planning and finance-operations-analysis.
- Delivery: project-delivery-coordination.

These are curated adaptations written for this repository, not wholesale mirrors of upstream skill repositories. Source revisions are pinned in the catalog. Review upstream licenses and notices again before importing any original scripts, hooks, assets, or verbatim skill content.

## Runtime boundary

The catalog is currently read-only and exposes skill metadata and instructions through authenticated organization-scoped GET endpoints. It does not assign skills to workforce members, create provider-side Claude skills, grant tools, start sessions, or enable autonomous execution.

Every entry is disabled by default, has an empty tool allowlist, and is limited to public/synthetic data until a founder-authorized assignment and runtime-specific policy path exists. A skill can recommend a tool but cannot authorize it. Backend authorization, Data Protection Gateway, Tenant Security Manager, approval checks, and audit remain authoritative.

The Managed Agents adapter currently fails closed on provider-side skills, tools, MCP, and multi-agent features. This library does not bypass that boundary.

## Admission and update policy

1. Record canonical source, publisher, pinned commit/tag, license, retrieval date, and imported paths.
2. Inspect all instructions, references, scripts, hooks, and package metadata. Treat external content as untrusted.
3. Review prompt-injection, secret access, network egress, shell commands, destructive operations, and permission escalation.
4. Rewrite or exclude unsafe/unneeded content. Keep required attribution and license notices.
5. Run static checks and isolated tests with synthetic data, no secrets, and restricted egress.
6. Record a SHA-256 digest for each admitted skill file. The registry computes and returns the current digest.
7. Do not auto-update or execute imported scripts. Re-admission requires review and a new pinned revision.
8. Keep skills disabled until explicit founder authorization is implemented and recorded for a specific workforce member, scope, data class, and runtime.

## CodeRabbit

The independent-code-review skill defines how to consume an optional CodeRabbit review signal. The hosted CodeRabbit service is not connected by this change. Before connecting it, review GitHub permissions, data retention, subprocessors, pricing, repository scope, and whether private code is sent to the service. CodeRabbit findings must be verified; it cannot replace CI, QA/Security, or founder approval.

## API

- GET /v1/orgs/{org_id}/skills — authenticated catalog metadata.
- GET /v1/orgs/{org_id}/skills/{skill_name} — authenticated skill instructions and provenance.

Both endpoints require organization membership. They are read-only. No workspace or client data is included.

## Verification

The registry validates the manifest, safe relative paths, required Agent Skills frontmatter, source references, disabled defaults, empty tool grants, and content hashes. Tests should fail closed on malformed or unsafe catalog entries.
