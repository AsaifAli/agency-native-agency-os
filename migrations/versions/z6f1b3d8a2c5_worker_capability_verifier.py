"""Add database verification for worker execution lease capabilities.

This revision establishes a private transaction context only after validating a
short-lived capability against the live attempt lease. Runtime issuance and RLS
policy cutover are deliberately separate follow-up steps.
"""
from alembic import op

revision = "z6f1b3d8a2c5"
down_revision = "y5e9a2c7d1f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        ALTER TABLE public.execution_attempts
        ADD COLUMN lease_generation integer NOT NULL DEFAULT 1
        CHECK (lease_generation > 0)
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.establish_worker_execution_context(
            p_token bytea,
            p_execution_id text,
            p_attempt_id text,
            p_worker_id text,
            p_lease_generation integer
        ) RETURNS boolean
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE
            capability agency_os_private.worker_lease_capabilities%ROWTYPE;
            attempt_matches boolean;
        BEGIN
            IF session_user <> 'agency_os_worker'
               OR p_token IS NULL OR octet_length(p_token) <> 32
               OR p_execution_id IS NULL OR p_attempt_id IS NULL
               OR p_worker_id IS NULL OR length(p_worker_id) NOT BETWEEN 1 AND 160
               OR p_lease_generation IS NULL OR p_lease_generation < 1 THEN
                RETURN false;
            END IF;

            SELECT c.* INTO capability
            FROM agency_os_private.worker_lease_capabilities AS c
            WHERE c.token_hash = sha256(p_token)
              AND c.execution_id = p_execution_id
              AND c.attempt_id = p_attempt_id
              AND c.worker_id = p_worker_id
              AND c.lease_generation = p_lease_generation
              AND c.invalidated_at IS NULL
              AND c.expires_at > clock_timestamp()
            FOR UPDATE;

            IF NOT FOUND THEN
                RETURN false;
            END IF;

            SELECT EXISTS (
                SELECT 1
                FROM public.executions AS e
                JOIN public.execution_attempts AS a
                  ON a.execution_id = e.id
                WHERE e.id = p_execution_id
                  AND a.id = p_attempt_id
                  AND a.worker_id = p_worker_id
                  AND a.lease_generation = p_lease_generation
                  AND a.lease_expires_at > clock_timestamp()
                  AND a.status::text IN ('claimed', 'running')
                  AND e.status::text IN ('claimed', 'running')
            ) INTO attempt_matches;

            IF NOT attempt_matches THEN
                RETURN false;
            END IF;

            INSERT INTO agency_os_private.worker_transaction_context (
                backend_pid, transaction_id, capability_id,
                execution_id, attempt_id, worker_id, lease_generation
            ) VALUES (
                pg_backend_pid(), txid_current(), capability.id,
                p_execution_id, p_attempt_id, p_worker_id, p_lease_generation
            )
            ON CONFLICT (backend_pid, transaction_id) DO UPDATE SET
                capability_id = EXCLUDED.capability_id,
                execution_id = EXCLUDED.execution_id,
                attempt_id = EXCLUDED.attempt_id,
                worker_id = EXCLUDED.worker_id,
                lease_generation = EXCLUDED.lease_generation,
                established_at = clock_timestamp();

            RETURN true;
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.establish_worker_execution_context(
            bytea, text, text, text, integer
        ) OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION
            agency_os_private.establish_worker_execution_context(
                bytea, text, text, text, integer
            ) FROM PUBLIC, agency_os_app
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION
            agency_os_private.establish_worker_execution_context(
                bytea, text, text, text, integer
            ) TO agency_os_worker
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
        REVOKE ALL ON FUNCTION
            agency_os_private.establish_worker_execution_context(
                bytea, text, text, text, integer
            ) FROM PUBLIC, agency_os_worker, agency_os_app
    """)
    op.execute("""
        DROP FUNCTION IF EXISTS
            agency_os_private.establish_worker_execution_context(
                bytea, text, text, text, integer
            )
    """)
    op.execute("ALTER TABLE public.execution_attempts DROP COLUMN IF EXISTS lease_generation")
