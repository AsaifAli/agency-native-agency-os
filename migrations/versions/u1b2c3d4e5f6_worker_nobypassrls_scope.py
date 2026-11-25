"""Constrain worker access to explicitly selected workspaces.

The worker login is NOBYPASSRLS. A SECURITY DEFINER inventory function exposes
only organization/workspace identifiers needed for fair queue polling; normal
worker queries remain subject to the existing tenant RLS policies.
"""
from alembic import op

revision = "u1b2c3d4e5f6"
down_revision = "t0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The worker must be able to evaluate policies that reference this helper,
    # but must never use it as a membership oracle.
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.user_has_org_access(
            target_org_id text, actor_user_id text
        ) RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
            SELECT actor_user_id IS NOT NULL
               AND session_user <> 'agency_os_worker'
               AND EXISTS (
                    SELECT 1 FROM public.memberships AS m
                    WHERE m.org_id = target_org_id
                      AND m.user_id = actor_user_id
               )
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.user_has_org_access(text, text)
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.worker_workspace_scopes()
        RETURNS TABLE(org_id text, workspace_id text)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
            SELECT w.org_id::text, w.id::text
            FROM public.workspaces AS w
            ORDER BY w.org_id, w.id
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.worker_workspace_scopes()
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION agency_os_private.worker_workspace_scopes()
        FROM PUBLIC
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION agency_os_private.worker_workspace_scopes()
        TO agency_os_worker
    """)

    # Org-level outbox events (workspace_id IS NULL) are visible only while
    # the worker has selected the matching organization. Workspace events
    # remain restricted to the exact selected workspace.
    op.execute("""
        DROP POLICY IF EXISTS tenant_isolation ON public.outbox_events
    """)
    op.execute("""
        CREATE POLICY tenant_isolation ON public.outbox_events
        USING (
            agency_os_private.user_has_org_access(
                org_id, nullif(current_setting('agency_os.user_id', true), '')
            )
            OR (
                org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                AND (
                    workspace_id IS NULL
                    OR workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                )
            )
        )
        WITH CHECK (
            agency_os_private.user_has_org_access(
                org_id, nullif(current_setting('agency_os.user_id', true), '')
            )
            OR (
                org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                AND (
                    workspace_id IS NULL
                    OR workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                )
            )
        )
    """)

    # Browser sessions have no workspace context. Retention is therefore a
    # bounded, audited SECURITY DEFINER operation rather than a worker-wide
    # table privilege or RLS bypass.
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.prune_expired_browser_sessions(
            p_retention_days integer,
            p_limit integer
        ) RETURNS integer
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
        DECLARE
            session_row record;
            deleted_count integer := 0;
            cutoff_at timestamptz;
        BEGIN
            IF p_retention_days < 1 OR p_retention_days > 3650
               OR p_limit < 1 OR p_limit > 1000 THEN
                RAISE EXCEPTION 'invalid browser-session retention bounds'
                    USING ERRCODE = '22023';
            END IF;
            cutoff_at := now() - make_interval(days => p_retention_days);

            FOR session_row IN
                SELECT s.id, s.user_id
                FROM public.browser_sessions AS s
                WHERE s.expires_at <= cutoff_at
                   OR s.revoked_at <= cutoff_at
                ORDER BY s.created_at, s.id
                LIMIT p_limit
                FOR UPDATE SKIP LOCKED
            LOOP
                INSERT INTO public.audit_events (
                    id, org_id, workspace_id, actor_user_id,
                    event_type, resource_type, resource_id, payload, created_at
                )
                SELECT
                    gen_random_uuid()::text, m.org_id, NULL, NULL,
                    'auth.browser_session_pruned', 'browser_session',
                    session_row.id,
                    json_build_object('reason_code', 'SESSION_RETENTION_ELAPSED'),
                    now()
                FROM public.memberships AS m
                WHERE m.user_id = session_row.user_id;

                DELETE FROM public.browser_sessions
                WHERE id = session_row.id;
                deleted_count := deleted_count + 1;
            END LOOP;
            RETURN deleted_count;
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.prune_expired_browser_sessions(integer, integer)
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION agency_os_private.prune_expired_browser_sessions(integer, integer)
        FROM PUBLIC
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION agency_os_private.prune_expired_browser_sessions(integer, integer)
        TO agency_os_worker
    """)
    op.execute("GRANT USAGE ON SCHEMA agency_os_private TO agency_os_worker")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.user_has_org_access(text, text) TO agency_os_worker")

    # Execution attempts have no org_id of their own; inherit the scope of
    # their parent execution so they cannot become an unprotected side table.
    op.execute("ALTER TABLE public.execution_attempts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.execution_attempts FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY execution_attempt_tenant_isolation
        ON public.execution_attempts
        USING (
            EXISTS (
                SELECT 1 FROM public.executions AS e
                WHERE e.id = execution_id
                  AND (
                    agency_os_private.user_has_org_access(
                        e.org_id, nullif(current_setting('agency_os.user_id', true), '')
                    )
                    OR (
                        e.org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                        AND e.workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                    )
                  )
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM public.executions AS e
                WHERE e.id = execution_id
                  AND (
                    agency_os_private.user_has_org_access(
                        e.org_id, nullif(current_setting('agency_os.user_id', true), '')
                    )
                    OR (
                        e.org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                        AND e.workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                    )
                  )
            )
        )
    """)
    op.execute("""
        REVOKE ALL ON TABLE public.users, public.browser_sessions,
            public.memberships, public.founder_authorities,
            public.machine_identities
        FROM agency_os_worker
    """)


def downgrade() -> None:
    op.execute("""
        DROP FUNCTION IF EXISTS agency_os_private.prune_expired_browser_sessions(integer, integer)
    """)
    op.execute("""
        DROP FUNCTION IF EXISTS agency_os_private.worker_workspace_scopes()
    """)
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.outbox_events")
    op.execute("""
        CREATE POLICY tenant_isolation ON public.outbox_events
        USING (
            agency_os_private.user_has_org_access(
                org_id, nullif(current_setting('agency_os.user_id', true), '')
            )
            OR (
                org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
            )
        )
        WITH CHECK (
            agency_os_private.user_has_org_access(
                org_id, nullif(current_setting('agency_os.user_id', true), '')
            )
            OR (
                org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
            )
        )
    """)
