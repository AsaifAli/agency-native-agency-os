# Reference integration decisions

Reviewed 2026-11-24. This is a fit assessment; it does not mean any third-party service is installed, connected or tested.

| Reference | Adopt | Do not adopt |
|---|---|---|
| ECC (Everything Claude Code) | Research-first planning, skills, engineering rules, testing/review loops and security hygiene | Entire harness, arbitrary hooks, duplicate orchestration or unrestricted shell/network tools |
| Strix | Optional isolated security assessment for explicitly authorized repositories/staging | Unrestricted scans, production exploitation or autonomous remediation |
| Claude Skills Hub | Discovery of candidate public skills | Treating listings, popularity or install counts as trust/licensing/security proof |
| CodeRabbit | Optional independent PR review signal | Auto-merge or replacing deterministic CI, internal QA and founder release approval |

## ECC
Use the loop: research → plan → implement → test → independent review → verify → capture reusable learning. Maintain Agency OS-owned project-local skills with publisher, source URL, license, pinned commit, checksum, dependencies, owner, approved data scope, tool permissions and review date. Inspect every hook/script before use. Hooks are developer safeguards, not backend authorization. Do not install every agent or add another orchestrator.

## Strix
Strix is a security-testing tool with Docker isolation, reconnaissance, SAST/DAST and proof-of-concept validation. Treat it as a separate QA/Security worker/container adapter, not part of the API process. Before each run require asset owner, written authorization reference, registered repository/domain allowlist, scope/exclusions, permitted tests, time window, rate limit and expiry. Pin source/target; enforce CPU/memory/time/network quotas; block cloud metadata, private ranges and unrelated internal services; provide no production credentials; scrub PII/secrets from artifacts. Findings remain untrusted until reproduced. Remediation is a separate reviewed PR followed by retest. No arbitrary target selection, lateral movement, persistence, exfiltration, denial-of-service or destructive tests. Founder approval for external live testing or expanded scope.

## Claude Skills Hub
Use as a search index only. Prefer official publisher collections. Inspect exact repository/path, publisher, license, commit history, scripts, dependencies, network/file behavior, MCP requirements and supported host. Perform static review and synthetic sandbox test. Pin commit and checksum; install project-locally only after approval; re-review updates. Useful candidate skill categories map to all departments: TDD, security, FastAPI, PostgreSQL, Next.js, AI evaluation, RAG, market research, SEO, sales research, proposal drafting, finance operations, PMO and client support.

## CodeRabbit
Potential flow: GitHub PR check → record reviewed commit SHA, status, timestamp, findings summary and URL → internal deterministic CI/security/migration/tenant checks → separate founder release decision. No auto-merge. Before connecting private code, review the applicable DPA, retention/cache terms, subprocessors/model routing, residency, training/telemetry controls, pricing/limits and GitHub permission scope. AI review is advisory and cannot certify safety or grant release approval.

## Baseline tools
Prefer deterministic pytest, Ruff, mypy, Playwright, SAST, secret scanning, dependency/license audit, container scanning and SBOM generation. AI review augments these. Every integration needs measurable need, owner, threat model, cost cap, scoped credentials, failure/recovery plan and removal path.

## References
- https://github.com/affaan-m/ECC
- https://github.com/usestrix/strix
- https://claudeskills.info
- https://www.coderabbit.ai
