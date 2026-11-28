"""Restrict machine identity and session rows to their owning service identity.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    # A service identity is workspace-scoped for business tools, but it must
    # not enumerate other clients' machine credentials or sessions in that
    # workspace. The lookup GUC is set only after bearer verification; during
    # initial authentication, org/workspace GUCs may still be empty.
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.machine_identities")
    op.execute("""
        CREATE POLICY tenant_isolation ON public.machine_identities
        USING (
            agency_os_private.user_has_workspace_access(
                org_id, workspace_id,
                nullif(current_setting('agency_os.user_id', true), '')
            )
            OR (
                session_user <> 'agency_os_worker'
                AND id = nullif(current_setting('agency_os.machine_identity_lookup_id', true), '')
                AND revoked_at IS NULL
                AND expires_at > clock_timestamp()
                AND (
                    nullif(current_setting('agency_os.machine_org_id', true), '') IS NULL
                    OR org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                )
                AND (
                    nullif(current_setting('agency_os.machine_workspace_id', true), '') IS NULL
                    OR workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                )
            )
            OR (
                session_user = 'agency_os_worker'
                AND subject_type = 'agent'
                AND revoked_at IS NULL
                AND expires_at > clock_timestamp()
                AND EXISTS (
                    SELECT 1
                    FROM public.executions AS e
                    WHERE e.org_id = machine_identities.org_id
                      AND e.workspace_id = machine_identities.workspace_id
                      AND e.agent_id = machine_identities.subject_id
                      AND agency_os_private.worker_has_execution_context(
                            e.org_id, e.workspace_id, e.id
                      )
                )
            )
        )
        WITH CHECK (
            agency_os_private.user_has_workspace_access(
                org_id, workspace_id,
                nullif(current_setting('agency_os.user_id', true), '')
            )
            OR (
                session_user <> 'agency_os_worker'
                AND id = nullif(current_setting('agency_os.machine_identity_lookup_id', true), '')
                AND revoked_at IS NULL
                AND expires_at > clock_timestamp()
                AND (
                    nullif(current_setting('agency_os.machine_org_id', true), '') IS NULL
                    OR org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                )
                AND (
                    nullif(current_setting('agency_os.machine_workspace_id', true), '') IS NULL
                    OR workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                )
            )
            OR (
                session_user = 'agency_os_worker'
                AND subject_type = 'agent'
                AND revoked_at IS NULL
                AND expires_at > clock_timestamp()
                AND EXISTS (
                    SELECT 1
                    FROM public.executions AS e
                    WHERE e.org_id = machine_identities.org_id
                      AND e.workspace_id = machine_identities.workspace_id
                      AND e.agent_id = machine_identities.subject_id
                      AND agency_os_private.worker_has_execution_context(
                            e.org_id, e.workspace_id, e.id
                      )
                )
            )
        )
    """)

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.agent_sessions")
    op.execute("""
        CREATE POLICY tenant_isolation ON public.agent_sessions
        USING (
            agency_os_private.user_has_workspace_access(
                org_id, workspace_id,
                nullif(current_setting('agency_os.user_id', true), '')
            )
            OR (
                session_user <> 'agency_os_worker'
                AND org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                AND machine_identity_id = nullif(current_setting('agency_os.machine_identity_lookup_id', true), '')
            )
            OR (
                session_user = 'agency_os_worker'
                AND (
                    agency_os_private.worker_has_execution_context(org_id, workspace_id, NULL)
                    OR agency_os_private.worker_has_workspace_context(org_id, workspace_id)
                )
            )
        )
        WITH CHECK (
            agency_os_private.user_has_workspace_access(
                org_id, workspace_id,
                nullif(current_setting('agency_os.user_id', true), '')
            )
            OR (
                session_user <> 'agency_os_worker'
                AND org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                AND machine_identity_id = nullif(current_setting('agency_os.machine_identity_lookup_id', true), '')
            )
            OR (
                session_user = 'agency_os_worker'
                AND (
                    agency_os_private.worker_has_execution_context(org_id, workspace_id, NULL)
                    OR agency_os_private.worker_has_workspace_context(org_id, workspace_id)
                )
            )
        )
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Unsafe downgrade refused: restoring workspace-wide machine identity "
        "and session visibility would allow cross-client credential enumeration"
    )

