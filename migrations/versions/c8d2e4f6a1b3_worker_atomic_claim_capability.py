"""Add atomic worker execution claiming and capability issuance.

The worker supplies only a one-time token hash. This SECURITY DEFINER function
chooses the next eligible execution itself, claims it, creates its attempt,
persists the hash-bound capability, and writes the claim audit event atomically.
"""
from alembic import op

revision = "c8d2e4f6a1b3"
down_revision = "b1c3d5e7f9a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.claim_worker_execution(
            p_worker_id text,
            p_lease_seconds integer,
            p_token_hash bytea
        )
        RETURNS TABLE(
            execution_id text,
            attempt_id text,
            org_id text,
            workspace_id text,
            lease_generation integer
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE
            target public.executions%ROWTYPE;
            new_attempt_id text;
            next_attempt_number integer;
            lease_deadline timestamptz;
        BEGIN
            IF session_user <> 'agency_os_worker'
               OR p_worker_id IS NULL
               OR length(p_worker_id) NOT BETWEEN 1 AND 160
               OR p_lease_seconds IS NULL
               OR p_lease_seconds NOT BETWEEN 15 AND 3600
               OR p_token_hash IS NULL
               OR octet_length(p_token_hash) <> 32 THEN
                RAISE EXCEPTION 'invalid worker claim request'
                    USING ERRCODE = '22023';
            END IF;

            DELETE FROM agency_os_private.worker_transaction_context AS ctx
            WHERE (ctx.backend_pid = pg_backend_pid() AND ctx.transaction_id <> txid_current())
               OR ctx.established_at < clock_timestamp() - interval '1 day'
               OR NOT EXISTS (
                    SELECT 1 FROM pg_stat_activity AS activity
                    WHERE activity.pid = ctx.backend_pid
               );
            DELETE FROM agency_os_private.worker_lease_capabilities AS cap
            WHERE cap.expires_at < clock_timestamp() - interval '1 day'
               OR cap.invalidated_at < clock_timestamp() - interval '1 day';

            SELECT e.* INTO target
            FROM public.executions AS e
            WHERE e.status::text = 'queued'
              AND e.attempt_count < e.max_attempts
            ORDER BY e.queued_at ASC, e.created_at ASC, e.id ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED;

            IF NOT FOUND THEN
                RETURN;
            END IF;

            next_attempt_number := target.attempt_count + 1;
            new_attempt_id := gen_random_uuid()::text;
            lease_deadline := clock_timestamp()
                + make_interval(secs => p_lease_seconds);

            UPDATE public.executions
            SET status = 'claimed'::executionstatus,
                attempt_count = next_attempt_number,
                updated_at = clock_timestamp()
            WHERE id = target.id;

            INSERT INTO public.execution_attempts (
                id, execution_id, attempt_number, lease_generation,
                worker_id, runtime, status, lease_expires_at,
                heartbeat_at, created_at
            ) VALUES (
                new_attempt_id, target.id, next_attempt_number, 1,
                p_worker_id, target.runtime, 'claimed'::executionattemptstatus,
                lease_deadline, clock_timestamp(), clock_timestamp()
            );

            INSERT INTO agency_os_private.worker_lease_capabilities (
                token_hash, execution_id, attempt_id, worker_id,
                lease_generation, expires_at
            ) VALUES (
                p_token_hash, target.id, new_attempt_id, p_worker_id,
                1, lease_deadline
            );

            INSERT INTO public.audit_events (
                id, org_id, workspace_id, actor_user_id, event_type,
                resource_type, resource_id, payload, created_at
            ) VALUES (
                gen_random_uuid()::text, target.org_id, target.workspace_id,
                NULL, 'execution.claimed', 'execution', target.id,
                jsonb_build_object(
                    'attempt_id', new_attempt_id,
                    'attempt_number', next_attempt_number,
                    'worker_id', p_worker_id,
                    'lease_seconds', p_lease_seconds,
                    'capability_issued', true
                )::json,
                clock_timestamp()
            );

            RETURN QUERY SELECT
                target.id, new_attempt_id, target.org_id,
                target.workspace_id, 1;
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.claim_worker_execution(text, integer, bytea)
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION
            agency_os_private.claim_worker_execution(text, integer, bytea)
        FROM PUBLIC, agency_os_app
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION
            agency_os_private.claim_worker_execution(text, integer, bytea)
        TO agency_os_worker
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("""
        REVOKE ALL ON FUNCTION
            agency_os_private.claim_worker_execution(text, integer, bytea)
        FROM PUBLIC, agency_os_worker, agency_os_app
    """)
    op.execute("""
        DROP FUNCTION IF EXISTS
            agency_os_private.claim_worker_execution(text, integer, bytea)
    """)
