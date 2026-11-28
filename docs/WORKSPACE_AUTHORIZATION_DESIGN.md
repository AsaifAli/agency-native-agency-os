# Human Workspace Authorization — Design and Implementation Plan

**Status:** Design baseline; implementation not yet applied  
**Scope:** Human API principals and PostgreSQL row-level security  
**Security objective:** An organization membership must not, by itself, grant access to every workspace in that organization.

## Confirmed current-state finding

The current authorization boundary is organization membership:

- `get_principal()` sets the transaction-local `agency_os.user_id` context.
- `require_membership()` verifies an organization membership and returns its role.
- Workspace route helpers in Revenue/Delivery, Operations, Outreach, Workforce and Telephony verify that a workspace belongs to the organization, but do not verify a user-to-workspace grant.
- The current tenant RLS migration applies `user_has_org_access(org_id, user_id)` to workspace-owned tables. For tables with `workspace_id`, this still grants every organization member row visibility across all workspaces in that organization.
- Workspace listing is currently organization-membership scoped.
- Some resource-by-ID handlers load the row by organization before checking its workspace. Once RLS becomes workspace-grant aware, those handlers must continue to return safe 404s for inaccessible objects without requiring broad access.

This is a cross-cutting authorization issue. Adding a Python check alone is insufficient because direct SQL and missed routes would remain exposed.

## Target authorization model

Keep organization membership and workspace access as separate concepts:

1. **Organization membership** establishes that a human belongs to an organization and supplies the organization-level role.
2. **Workspace grant** establishes access to one workspace. It is independently revocable and auditable.
3. **Founder authority** remains a separate explicit grant. Neither organization role `owner` nor a workspace grant implies founder authority.
4. **Machine principals** retain their separate, narrowly scoped worker/machine authorization path. Human workspace grants must not widen machine access.
5. **Workspace creation** and the creator's initial grant must commit atomically.

### Proposed grant record

Add a `workspace_grants` table with:

- `id`
- `org_id`
- `workspace_id`
- `user_id`
- `granted_by`
- `created_at`
- `revoked_at` (or an equivalent active/revoked state with retained history)

Enforce a composite workspace/org foreign key and a unique active grant per `(org_id, workspace_id, user_id)`. Retain grant/revoke history rather than deleting authorization evidence. Grant and revoke operations must emit tamper-evident audit events in the same transaction.

### Migration compatibility

The migration must preserve current access rather than silently locking existing users out:

- Backfill one active grant for every currently active organization membership × workspace pair in that organization.
- Do not infer grants for future memberships or future workspaces.
- New memberships receive no workspace access until a founder-authorized grant is created.
- Workspace creation inserts the workspace and creator grant in one transaction.
- If existing membership provisioning code is retained, explicitly decide whether the inviter must also grant one or more workspaces; do not restore implicit organization-wide access.

## PostgreSQL RLS design

Introduce a narrowly owned SECURITY DEFINER predicate:

`agency_os_private.user_has_workspace_access(target_org_id, target_workspace_id, actor_user_id)`

It must return true only when:

- the actor is non-null and active;
- the actor has an active membership in the organization; and
- an active grant exists for that exact organization, workspace and user.

Use a fixed safe search_path, revoke PUBLIC execution, grant only the API role what it needs, and ensure the function owner is a non-login migration/security role with the minimum required privileges.

For every workspace-scoped table in the authoritative migration inventory, change the human branch of USING and WITH CHECK from organization membership to the workspace predicate. Keep org-only tables (for example memberships and other genuinely organization-wide records) governed by their intended organization-level policy. Keep machine predicates separate and exact-workspace scoped.

For tables whose `workspace_id` is nullable (for example, an explicitly organization-wide record), define the null case deliberately: allow `workspace_id IS NULL` only under the intended organization-level predicate, and require the exact workspace predicate for every non-null workspace row. Never let a nullable column turn a workspace-scoped row into an organization-wide bypass. Inventory nullability per table before writing policies.

The `workspaces` table needs command-specific policies:
- SELECT: only workspaces for which the human has an active grant (plus the existing exact machine workspace path).
- INSERT: organization member with the required workspace-creation role; the application must create the creator grant in the same transaction. Prefer a narrow database function if needed to make the invariant impossible to bypass.
- UPDATE/DELETE: explicit policy aligned to the intended founder/admin lifecycle; do not silently infer this from SELECT access.
- Workspace grant creation and revocation require both explicit Founder Authority and a matching, single-use `security.permission.change` approval. The approval resource ID is the stable UUIDv5 returned by `app.action_policy.workspace_access_resource_id(workspace_id, user_id, operation)` (with `operation` set to `grant` or `revoke`); approval consumption, grant mutation, and audit commit in one database transaction. A no-op revoke rolls back approval consumption.

The `workspace_grants` table needs its own restrictive policies. A user may read their own grants; grant administration must require explicit founder authority in the API and must not be made possible by a broad organization-member policy. Evaluate a narrow SECURITY DEFINER write function if direct table grants would undermine the boundary.

Execution attempts and other child records must inherit the parent execution's exact workspace authorization. Org-level outbox events remain organization-scoped only where their payload is genuinely org-wide; workspace events must require the matching workspace grant.

## API and lifecycle changes

Create centralized helpers with consistent semantics:

- `require_workspace_access(org_id, workspace_id, principal, db)`: require active organization membership, then an active exact workspace grant, then establish any request-local context needed by the application. Return a safe 404 for inaccessible workspace IDs to avoid disclosing their existence.
- A founder-only grant/revoke service that checks explicit founder authority, validates target membership and workspace ownership, serializes concurrent changes, and writes the grant state plus audit event atomically.
- A workspace list endpoint that returns only granted workspaces.
- Workspace creation that atomically creates the workspace, creator grant and audit event.
- Membership invitation/provisioning that does not automatically grant all workspaces.
- All workspace-scoped route families must call the centralized guard before reading or mutating workspace data. Resource-by-ID routes must not perform an unscoped read first; either require an explicit workspace identifier or use a narrowly scoped lookup that proves the grant before returning the row.

Route families found during the initial audit include core workspace/bootstrap and execution routes in `app/main.py`; Revenue/Delivery in `app/domain_routes.py`; commercial and delivery operations in `app/operations_routes.py`; Outreach in `app/outreach/routes.py`; Workforce and orchestration in `app/workforce_routes.py`; Telephony in `app/telephony/routes.py`; and founder/security routes in `app/security_routes.py` and `app/revenue_research_routes.py`. The existing `tests/test_route_auth_inventory.py` proves that routes have an authentication boundary and that workspace routes reference a workspace identifier; it does **not** prove workspace authorization. Extend it to fail when any workspace-scoped route lacks the centralized workspace guard (or a documented, reviewed equivalent). The final implementation must build and test a complete endpoint inventory rather than relying on this initial list.

## Required regression and integration tests

### Migration and data integrity
- Backfill grants for every existing active membership/workspace pair.
- No grants for inactive/non-member users.
- Composite FK rejects a grant whose workspace belongs to another organization.
- Duplicate active grants are rejected.
- Revoked grants remain auditable and cannot be reactivated through an unauthorized path.
- New memberships do not gain implicit access to existing or future workspaces.

### API authorization
- Member with a grant can read/write only according to their organization role.
- Member without a grant receives a safe denial for list, detail, create, update and delete operations.
- A grant to workspace A never authorizes workspace B in the same organization.
- Founder grant/revoke requires explicit founder authority; an organization owner without founder authority is denied.
- Workspace creator receives access atomically.
- Revocation takes effect on the next transaction/request and cannot be bypassed by pooled session reuse.
- Resource-by-ID endpoints do not leak object existence or data across workspaces.
- Every workspace route is covered by an authorization inventory test.

### PostgreSQL RLS
- Under one user context, workspace A rows are visible and workspace B rows are invisible.
- INSERT/UPDATE/DELETE outside granted workspaces fail at the database boundary.
- Direct SQL cannot bypass grant policy using the API role.
- Workspace listing reveals only granted workspaces.
- Grant-table policies do not expose other users' grants to ordinary members.
- Child rows, executions, approvals, audit events, files/artifacts and workspace-scoped outbox rows cannot cross workspace boundaries.
- Transaction rollback, commit, pooled connection reuse and revocation are tested.
- Worker/machine scope remains exact-workspace and is not widened by human grant changes.

## Rollout and acceptance gates

1. Complete endpoint/schema inventory and threat review.
2. Add failing API and PostgreSQL tests first.
3. Implement grant model, migration/backfill, policies, lifecycle services and route guards as one coordinated change.
4. Run unit, API, isolated PostgreSQL and full backend suites; verify migration upgrade/downgrade in disposable databases.
5. Review generated SQL and policy semantics independently.
6. Only then mark the PR ready. Do not enable production rollout until a production migration plan, backup/restore evidence and an approved rollback path exist.

## Explicit non-goals

- Do not change founder authority semantics.
- Do not merge human and machine authorization.
- Do not grant workspace access based only on organization role.
- Do not apply migrations to the separate website Supabase database.
- Do not claim production isolation from unit tests or policy-presence checks alone.

- Machine identity provisioning and revocation also require a matching, single-use `security.permission.change` approval. Provisioning approvals bind the exact identity name, subject, scopes, allowed data classes and TTL; revocation approvals bind the exact identity ID. The approval is consumed in the same transaction as the identity mutation and audit event.
- Workforce capability configuration, capability enablement, and workforce-member activation require matching single-use `security.permission.change` approvals. The approved payload is an exact snapshot of the proposed scope/actions/tools/data classes/budget (and, for activation, the linked agent plus enabled capability set). Pausing a member remains immediately available to founders as a restrictive containment action.
