"""Allow an active worker transaction to renew its own capability expiry."""
from alembic import op

revision = "d9e3f5a7b2c4"
down_revision = "c8d2e4f6a1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.renew_worker_execution_capability()
        RETURNS boolean
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE
            renewed_count integer;
        BEGIN
            IF session_user <> 'agency_os_worker' THEN
                RETURN false;
            END IF;

            UPDATE agency_os_private.worker_lease_capabilities AS cap
            SET expires_at = a.lease_expires_at
            FROM agency_os_private.worker_transaction_context AS ctx
            JOIN public.execution_attempts AS a
              ON a.id = ctx.attempt_id
             AND a.execution_id = ctx.execution_id
            JOIN public.executions AS e
              ON e.id = a.execution_id
            WHERE ctx.backend_pid = pg_backend_pid()
              AND ctx.transaction_id = txid_current()
              AND cap.id = ctx.capability_id
              AND cap.invalidated_at IS NULL
              AND cap.expires_at > clock_timestamp()
              AND a.worker_id = ctx.worker_id
              AND a.lease_generation = ctx.lease_generation
              AND a.lease_expires_at > clock_timestamp()
              AND a.status::text IN ('claimed', 'running')
              AND e.status::text IN ('claimed', 'running');

            GET DIAGNOSTICS renewed_count = ROW_COUNT;
            RETURN renewed_count = 1;
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.renew_worker_execution_capability()
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION
            agency_os_private.renew_worker_execution_capability()
        FROM PUBLIC, agency_os_app
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION
            agency_os_private.renew_worker_execution_capability()
        TO agency_os_worker
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
        REVOKE ALL ON FUNCTION
            agency_os_private.renew_worker_execution_capability()
        FROM PUBLIC, agency_os_worker, agency_os_app
    """)
    op.execute("""
        DROP FUNCTION IF EXISTS
            agency_os_private.renew_worker_execution_capability()
    """)
