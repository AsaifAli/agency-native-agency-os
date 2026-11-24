# Baseline reconciliation: v4 versus current-clean archive

## Decision

The v5 bundle is based on the supplied `agency-os-founder-governance-bundle-v4.zip`. The supplied `agency-os-current-clean(2).zip` was used as a comparison source, not overlaid wholesale.

## Why v4 was retained as the baseline

The current-clean archive differs in shared files in ways that remove or weaken v4 governance and architecture decisions:

- `app/models.py`, `app/auth.py`, `app/bootstrap.py`, `app/main.py`, `app/action_policy.py` and approval tests in current-clean remove explicit `FounderAuthority`, founder bootstrap provisioning and founder-only approval decisions.
- Current-clean approval logic reverts to organization-owner approval and rejects requester self-approval, which does not fit the agreed single-founder authority model.
- Current-clean `frontend/lib/api.ts` unconditionally constructs a `dev:` bearer token when no token is stored. v4 gates development-token behavior behind `NEXT_PUBLIC_ALLOW_DEV_AUTH=true` and non-production mode. v4 is retained.
- Current-clean `frontend/app/workflows/page.tsx` describes an n8n-backed workflow catalogue. v4 correctly treats n8n as a legacy reference and keeps native OS services, workers and outbox as the initial architecture.
- Current-clean removes telephony route registration, call history navigation and the Founder Authority notice from the UI. v4 is retained.
- Current-clean changes some dashboard copy to imply approval API work is still missing even though the v4 backend includes approval endpoints.

## Preserved current-clean content

The v5 archive retains the shared baseline files where v4 remains the more secure and coherent implementation. No current-clean change was found that justified replacing the v4 founder-governance behavior. The current-clean archive's useful domain and worker foundation is already represented in the v4 source snapshot.

## Verification

The v4 source snapshot passed its recorded baseline tests during this review: 95 passed, 1 skipped. The v5 consolidated tree adds the delivery-operations vertical slice and passed 102 tests, 1 skipped. PostgreSQL migration upgrade and frontend production build remain unverified.
