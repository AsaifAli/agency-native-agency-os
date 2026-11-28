"""Restore machine identity visibility only for its active worker execution."""
from alembic import op

revision = "e8a1c3d5f7b9"
down_revision = "d6f8a0b2c4e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.machine_identities")

    human = """agency_os_private.user_has_workspace_access(
        org_id, workspace_id, nullif(current_setting('agency_os.user_id', true), '')
    )"""
    # Machine authentication first resolves the supplied identity ID before
    # org/workspace GUCs can be trusted. The lookup exception is ID-specific,
    # non-worker-only, and still followed by token digest verification.
    machine = """(
        session_user <> 'agency_os_worker'
        AND (
            (
                org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
            )
            OR (
                id = nullif(current_setting('agency_os.machine_identity_lookup_id', true), '')
                AND revoked_at IS NULL
                AND expires_at > clock_timestamp()
            )
        )
    )"""
    # Worker access exists only while a live execution capability is bound to
    # this exact execution and agent. Maintenance leases do not satisfy this
    # predicate. If an execution already has a session, only that session's
    # identity is visible.
    worker = """(
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
              AND (
                    e.machine_session_id IS NULL
                    OR EXISTS (
                        SELECT 1
                        FROM public.agent_sessions AS s
                        WHERE s.id = e.machine_session_id
                          AND s.org_id = machine_identities.org_id
                          AND s.workspace_id = machine_identities.workspace_id
                          AND s.machine_identity_id = machine_identities.id
                    )
              )
        )
    )"""
    predicate = f"({human} OR {machine} OR {worker})"
    op.execute(
        "CREATE POLICY tenant_isolation ON public.machine_identities "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Unsafe downgrade refused: reverting would disable active execution "
        "identity resolution or broaden worker identity access"
    )
