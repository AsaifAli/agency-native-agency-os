# Chief of Staff plan-draft workflow

## Purpose

Allow the Chief of Staff to prepare a structured work proposal asynchronously without granting it the authority to assign members, approve work or execute external actions.

## Request and execution

The founder submits a bounded objective through POST /v1/orgs/{org_id}/workforce/plan-drafts. The API requires explicit Founder Authority, an active Chief of Staff workforce member, an enabled Claude Managed Agents definition and an enabled plan.generate grant matching the Agent data class. Draft execution is limited to synthetic or public data and requires a configured runtime. The endpoint persists a task, execution and draft row with an idempotency key; it never calls the provider inside the API transaction.

The existing OS worker claims the durable execution. The Claude adapter uses a dedicated tool-free planning prompt. The model receives no member IDs or assignment authority. It must return a single JSON object, bounded to ten work packages and the allowed sixteen department keys. Each task can have at most one dependency, which must reference an earlier task ordinal. Every task must require founder review.

## Validation and founder approval

The worker parses and validates the result against the Pydantic schema. Valid output transitions to ready_for_review; malformed, oversized or schema-invalid output transitions to invalid_output. The proposed JSON is stored in the OS draft record, not as an executable plan.

The Founder Console displays the summary, tasks, acceptance criteria, risks and founder decisions. The founder explicitly chooses a delegating manager and direct-report assignee for every task. The API revalidates the department, workspace, active/capable assignee, direct-manager relationship, and that the manager is in the Chief of Staff's reporting subtree. The approval record, root task, plan, delegation rows and audit event commit in one database transaction. A proposal cannot approve itself, omit an assignment or disable required task review.

Rejecting a proposal stores the founder's decision and cancels its draft task. Repeated requests with the same idempotency key return the existing draft only when the objective and title match.

## Safety and limits

- Tool/MCP access is not granted to the planning Agent; the provider Agent is still validated as tool-free.
- No client-confidential or regulated data is permitted by the feature's agent data-class check. A lightweight objective guard blocks common contact/credential patterns but is not a full DLP/PII gateway.
- The plan.generate capability is separate from task.execute; a plan-draft execution cannot use a normal task-execution grant.
- Draft generation does not activate agents, create workforce capabilities, or dispatch external actions.
- After founder approval, the already-governed execution worker can queue eligible delegated tasks, subject to their own capability grants, data eligibility and review gates.
- Claude Managed Agents is opt-in and beta. Live provider calls, actual Environment sandbox/egress, ambiguous session-create reconciliation and live-account compatibility were not tested by CI.
- CI uses synthetic/mock results. No Claude API key or live provider session is required for the tests.

## Environment configuration

The default .env.example keeps Managed Agents disabled and provider secrets blank. An authorized operator must separately configure CLAUDE_MANAGED_AGENTS_ENABLED, ANTHROPIC_API_KEY, CLAUDE_MANAGED_AGENT_ID and CLAUDE_MANAGED_ENVIRONMENT_ID for the correct Anthropic account and reviewed environment. Do not turn this on until tool-free provider configuration, data eligibility, budget and sandbox/egress controls are verified.

## Acceptance evidence

Backend CI run [45484628707](https://github.com/AsaifAli/agency-native-agency-os/actions/runs/45484628707) passed **176 tests, 1 warning**, PostgreSQL 16 migrations, Python compilation, TypeScript and Next.js production build. This proves the local/mock lifecycle and schema behavior, not a live Claude deployment.