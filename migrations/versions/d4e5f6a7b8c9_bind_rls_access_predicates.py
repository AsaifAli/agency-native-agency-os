"""Bind SECURITY DEFINER access predicates to the authenticated transaction user.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.user_has_org_access(
            target_org_id text, actor_user_id text
        ) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
            SELECT actor_user_id IS NOT NULL
               AND actor_user_id = nullif(current_setting('agency_os.user_id', true), '')
               AND session_user <> 'agency_os_worker'
               AND EXISTS (
                    SELECT 1 FROM public.memberships AS m
                    WHERE m.org_id = target_org_id
                      AND m.user_id = actor_user_id
               )
        $function$
    """)
    op.execute("ALTER FUNCTION agency_os_private.user_has_org_access(text, text) OWNER TO agency_os_migrator")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.user_has_org_access(text, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.user_has_org_access(text, text) TO agency_os_app, agency_os_worker")

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.user_has_workspace_access(
            target_org_id text, target_workspace_id text, actor_user_id text
        ) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
            SELECT actor_user_id IS NOT NULL
               AND actor_user_id = nullif(current_setting('agency_os.user_id', true), '')
               AND target_workspace_id IS NOT NULL
               AND session_user <> 'agency_os_worker'
               AND EXISTS (
                    SELECT 1
                    FROM public.users AS u
                    JOIN public.memberships AS m
                      ON m.user_id = u.id AND m.org_id = target_org_id
                    JOIN public.workspace_grants AS g
                      ON g.org_id = target_org_id
                     AND g.workspace_id = target_workspace_id
                     AND g.user_id = u.id
                     AND g.revoked_at IS NULL
                    WHERE u.id = actor_user_id AND u.active IS TRUE
               )
        $function$
    """)
    op.execute("ALTER FUNCTION agency_os_private.user_has_workspace_access(text, text, text) OWNER TO agency_os_migrator")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.user_has_workspace_access(text, text, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.user_has_workspace_access(text, text, text) TO agency_os_app, agency_os_worker")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Unsafe downgrade refused: unbound access predicates would restore a "
        "cross-user membership/workspace access oracle"
    )
