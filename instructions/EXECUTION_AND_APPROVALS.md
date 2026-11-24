# Execution and Approval Rules

## Execution lifecycle
Persist task and execution intent before external work. Track attempts, leases, heartbeats, results, errors, cancellation and audit. Use idempotency keys, deduplication, bounded retries, dead letters and reconciliation. External calls stay outside database transactions.

## Approval gates
Protected actions include contracts, pricing and commitments, payments, sensitive external communications, production releases, destructive actions, permission changes, and client-data deletion or export beyond approved scope.

Validate approval and consume it with the protected action in one transaction. Record actor, approver, scope, decision, evidence and outcome. If approval expires, is revoked or no longer matches the action, stop.

## Stop conditions
Stop on founder instruction, cancellation, opt-out, reply, bounce, policy violation, missing authorization, expired credentials, budget exhaustion, data-class mismatch or unresolved security risk.
