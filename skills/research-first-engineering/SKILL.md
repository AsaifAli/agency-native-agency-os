---
name: research-first-engineering
description: Research unfamiliar libraries, APIs, security-sensitive behavior, and architecture choices using primary sources before implementation.
---
# Research-First Engineering

Use when the task depends on changing APIs, unfamiliar dependencies, provider behavior, security controls, or a consequential architecture decision.

1. Search official documentation, source repositories, release notes, and issue discussions from the maintainers.
2. Confirm version compatibility and distinguish stable, beta, deprecated, and preview features.
3. Prefer primary sources. Use community posts only as supplementary evidence.
4. Capture the exact source URL, version/commit, access date, and the claim it supports.
5. Separate verified facts, vendor claims, community reports, and engineering inference.
6. Compare the smallest viable options against the existing architecture and operational burden.
7. Do not introduce a new service or dependency unless a measurable requirement justifies it.
8. Save a concise decision record for material choices, including rejected alternatives and re-evaluation triggers.

Never copy secrets, private user data, or unreviewed code into external research tools.
