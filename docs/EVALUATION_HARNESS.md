# Agency OS Evaluation Harness

The Evaluation Harness is a separate, versioned quality and safety boundary. It records deterministic evaluation runs in the OS database, scoped to an organization and workspace. A recorded passing run is evidence for the supplied test input; it is not proof that unexecuted controls work in production.

## Current registered packs

- `rag`: retrieval ranking, citation completeness/correctness, answer relevance and groundedness.
- `agent_workflow`: task completion, required-step recall, tool validity, policy pass rate, approval compliance, execution reliability and fallback rate.
- `safety_security`: explicit evidence for required controls, required approval actions, forbidden outcomes, tenant isolation and data-policy compliance.\n- `regression`: required API-contract, migration and workflow regression checks; missing or false checks fail the gate.

## Safety/security evidence contract

Submit `safety_security` with:

```json
{
  "required_controls": ["authorization", "redaction"],
  "required_approval_actions": ["send_email"],
  "forbidden_outcomes": ["cross_workspace_read"],
  "control_results": {
    "authorization": true,
    "redaction": true
  },
  "approved_actions": ["send_email"],
  "observed_outcomes": [],
  "tenant_isolation_passed": true,
  "data_policy_passed": true
}
```

The `expected` object contains the required control names, approval action names and forbidden outcomes. The `actual` object contains the observed evidence.

The pack fails closed:
- Every required control must have an explicit boolean `true` result.
- Every required approval action must appear in the approved action evidence.
- Any observed forbidden outcome fails its gate.
- Tenant isolation and data-policy checks must be explicitly `true`; missing values fail.
- An empty required-control list scores zero and fails its gate, preventing a vacuous pass.

The pack only evaluates evidence supplied by a test runner. It does not perform cross-tenant tests, inspect RLS, validate approval transactions, or enforce data policy itself. Those controls must be exercised by integration/security tests and their results supplied by a trusted, authenticated evaluation runner. At present, the API accepts evaluation payloads from authorized workspace members; a signed test-runner attestation and immutable release manifest are not yet implemented. Therefore this pack is an evaluation primitive, not yet an automatic production release blocker.

## API

- `GET /v1/evaluations/packs?org_id=<org>` lists registered packs (organization membership required).
- `POST /v1/orgs/{org_id}/evaluations` persists an evaluation result and audit event after workspace authorization.
- `GET /v1/orgs/{org_id}/evaluations?workspace_id=<workspace>` lists persisted results for the authorized workspace.

## Required next steps before release gating

1. Define immutable evaluation dataset and test-suite revisions.
2. Add a signed runner identity/attestation so caller-supplied booleans cannot self-certify release safety.
3. Bind evaluations to a commit, migration head, agent/prompt/tool-policy versions and environment.
4. Require all mandatory safety/security packs to pass before release approval can be consumed.
5. Preserve evaluation inputs/results and audit under retention policy; restrict sensitive payloads and redact PII.
6. Add negative cross-workspace, worker/session, approval race, outbox replay and data-protection integration suites.
7. Prove the release gate blocks a failed candidate and cannot be bypassed by a normal workspace member.

## Verification status

The deterministic pack and unit tests are source-added on the integration branch. Tests have not yet been executed in the repository environment. PostgreSQL RLS, actual tenant isolation, worker recovery, and release blocking remain runtime verification items.


## Regression evidence contract

Submit `regression` with a required test/check list and explicit results:

```json
{
  "required_checks": ["api_contract", "migration_compatibility"],
  "check_results": {
    "api_contract": true,
    "migration_compatibility": true
  }
}
```

Every named required check must be explicitly `true`. Missing keys, false values, malformed result objects, and an empty required-check set fail the gate. This evaluates supplied check evidence only; a trusted CI/test-runner attestation and immutable commit/environment binding remain future work.
