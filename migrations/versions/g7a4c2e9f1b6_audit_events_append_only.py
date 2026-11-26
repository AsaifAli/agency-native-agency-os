"""Make audit events append-only for all non-superuser database roles.

Application and worker roles cannot rewrite or delete audit history. The
trigger also protects against accidental grants to the table owner/migrator.
Superuser access remains an explicit trusted-administrator boundary.
"""
from alembic import op


revision = "g7a4c2e9f1b6"
down_revision = "f3b7d9e1a5c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.reject_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE
            caller_is_superuser boolean;
        BEGIN
            SELECT r.rolsuper
              INTO caller_is_superuser
              FROM pg_catalog.pg_roles AS r
             WHERE r.rolname = session_user;

            IF coalesce(caller_is_superuser, false) THEN
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END IF;

            RAISE EXCEPTION 'audit_events are append-only'
                USING ERRCODE = '55000';
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.reject_audit_event_mutation()
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION agency_os_private.reject_audit_event_mutation()
        FROM PUBLIC
    """)
    op.execute("""
        DROP TRIGGER IF EXISTS audit_events_append_only
        ON public.audit_events
    """)
    op.execute("""
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON public.audit_events
        FOR EACH ROW
        EXECUTE FUNCTION agency_os_private.reject_audit_event_mutation()
    """)
    op.execute("""
        REVOKE UPDATE, DELETE ON TABLE public.audit_events
        FROM PUBLIC, agency_os_app, agency_os_worker
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Unsafe downgrade refused: removing audit immutability would permit "
        "application and worker roles to rewrite audit history"
    )
