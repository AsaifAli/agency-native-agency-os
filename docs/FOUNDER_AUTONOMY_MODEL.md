# Founder-in-the-loop operating model

**Principle:** Founder-in-the-loop, not founder-in-every-loop. Agents and workers execute bounded, pre-authorized routine work. The founder reviews exceptions and retains final authority over critical decisions.

## 1. Authority model

- `Role.owner` is an organization membership role. It is not proof of founder-wide authority.
- `FounderAuthority` is a separate, explicit grant scoped to an organization and user.
- Founder grants are provisioned only through the trusted bootstrap or local administrative CLI. There is no public HTTP endpoint to grant founder authority.
- An organization owner without an active `FounderAuthority` record cannot approve protected actions.
- A founder may approve an action they personally initiated. This is intentional: the founder is the final decision-maker, and requiring a fictitious second human reviewer would contradict the single-founder operating model.
- A non-founder cannot approve an action they requested, or any other protected action.
- The protected-action consumer verifies that the approver still has active Founder Authority when the approval is consumed. Revocation therefore invalidates unused approvals.

## 2. Provisioning

New organizations created through `app.bootstrap` grant Founder Authority to the bootstrap founder.

For an existing organization, first apply migration `b4a9e2d1c673`, then provision explicitly from a trusted shell:

```bash
python -m app.founder_admin grant \\
  --org-id YOUR_ORG_ID \\
  --email founder@example.com \\
  --confirm founder@example.com
```

To revoke:

```bash
python -m app.founder_admin revoke \\
  --org-id YOUR_ORG_ID \\
  --email founder@example.com \\
  --confirm founder@example.com
```

The target must already be an active user. The command uses the configured `DATABASE_URL`; it must only be run by a trusted database administrator. Do not put credentials in command arguments or shell history.

## 3. Autonomy classes

`app.autonomy_policy` provides a central classification registry:

| Class | Meaning | Examples |
|---|---|---|
| Autonomous | Routine internal action that may run only after endpoint-level permission, data, budget and idempotency checks | CRM updates, internal task updates, research, transcript processing, internal notifications |
| Founder approval | High-impact action requiring a founder-approved, scoped, single-use approval | Pricing changes, contracts, payments, sensitive external communication, production releases, destructive actions and permission changes |
| Manual review | Unknown or not-yet-authorized action; default for anything not explicitly registered | New action types, outbound dialing until consent and contact policy enforcement exist |

Classification is not itself authorization. Every real side-effect endpoint and worker must enforce the class plus actor scope, workspace access, consent/suppression, data classification, budget, rate limits, idempotency and audit. Unknown actions fail closed to manual review.

## 4. Founder approval checkpoints

Founder approval is mandatory before:

- Sending or accepting proposals, quotations, pricing, SOWs or contracts.
- Making payments, refunds, write-offs or financial commitments.
- Sending sensitive communications or making commitments on behalf of the studio.
- Initiating production releases or high-impact infrastructure changes.
- Deleting client data, destructive resources or changing security permissions.

Routine follow-ups and outbound callbacks are not automatically permitted just because a lead exists. They require explicit consent/provenance, suppression checks, contact windows, approved sender/caller identity, rate limits and an explicit pre-authorized policy. Until those controls are implemented and tested, the action remains manual review.

## 5. Safe execution pattern

1. An agent/worker proposes a typed action with organization/workspace scope, resource, reason, idempotency key and bounded budget.
2. Backend policy classifies the action. Unknown actions stop for review.
3. For autonomous actions, the endpoint enforces permissions, client policy, consent/data eligibility and budget before committing.
4. For protected actions, create an approval request. Only an active Founder Authority identity can approve or reject it.
5. The protected handler consumes the exact scoped approval and persists the authorized action intent/outbox event in the same database transaction.
6. The external provider call runs outside the database transaction with idempotency, bounded retries and reconciliation.
7. Persist outcome, provider IDs, costs, audit and exceptions. Do not report success before durable confirmation.
8. On uncertainty, repeated failure, policy violation, budget exhaustion or missing permission, pause and escalate to the founder.

## 6. Current implementation boundary

Implemented in this bundle:

- Separate `FounderAuthority` model and migration.
- Bootstrap founder grant for newly created organizations.
- Trusted local grant/revoke CLI for existing organizations.
- Approval decision endpoint requires active Founder Authority, not merely `Role.owner`.
- Founder may approve their own initiated request; non-founders cannot approve.
- Approval consumption rechecks the approver's active Founder Authority.
- Unit/API tests cover separation from organization role, founder self-approval, revocation-sensitive consumption behavior and fail-closed action classification.

Still required before production:

- Wire `require_approved_action` into every protected side-effect endpoint.
- Implement endpoint/worker enforcement of the autonomy classification and all actor, workspace, consent, budget and data-policy checks.
- Implement durable outbox dispatch, leases, retries, dead letters and reconciliation.
- Implement production identity/MFA and service identities.
- Prove the full approval + protected action + outbox transaction with PostgreSQL integration and concurrency tests.

This bundle does not claim those remaining controls are already operational.
