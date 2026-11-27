"""Fix varchar-to-text result typing in the workspace maintenance claim RPC.

The workspace table stores identifiers as varchar(36), while the SECURITY
DEFINER function declares text result columns. PostgreSQL requires explicit
casts in RETURN QUERY for this composite result contract.
"""
from alembic import op

revision = "f3b7d9e1a5c2"
down_revision = "f2a6c8e0b4d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    # CREATE OR REPLACE preserves the function owner and ACL established by
    # e1f4a6b8c0d2. Only the declared result-type casts differ.
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.claim_worker_maintenance_scope(
            p_worker_id text,
            p_lease_seconds integer,
            p_token_hash bytea,
            p_after_workspace_id text DEFAULT NULL
        )
        RETURNS TABLE(org_id text, workspace_id text)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE
            target public.workspaces%ROWTYPE;
            lease_deadline timestamptz;
        BEGIN
            IF session_user <> 'agency_os_worker'
               OR p_worker_id IS NULL OR length(p_worker_id) NOT BETWEEN 1 AND 160
               OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 15 AND 300
               OR p_token_hash IS NULL OR octet_length(p_token_hash) <> 32 THEN
                RAISE EXCEPTION 'invalid worker maintenance claim'
                    USING ERRCODE = '22023';
            END IF;

            DELETE FROM agency_os_private.worker_workspace_transaction_context AS ctx
            WHERE (ctx.backend_pid = pg_backend_pid() AND ctx.transaction_id <> txid_current())
               OR ctx.established_at < clock_timestamp() - interval '1 day'
               OR NOT EXISTS (
                    SELECT 1 FROM pg_stat_activity AS activity
                    WHERE activity.pid = ctx.backend_pid
               );
            DELETE FROM agency_os_private.worker_workspace_capabilities AS cap
            WHERE cap.expires_at < clock_timestamp() - interval '1 day'
               OR cap.invalidated_at < clock_timestamp() - interval '1 day';

            SELECT w.* INTO target
            FROM public.workspaces AS w
            WHERE (p_after_workspace_id IS NULL OR w.id > p_after_workspace_id)
              AND NOT EXISTS (
                  SELECT 1
                  FROM agency_os_private.worker_workspace_capabilities AS cap
                  WHERE cap.workspace_id = w.id
                    AND cap.invalidated_at IS NULL
                    AND cap.expires_at > clock_timestamp()
              )
            ORDER BY w.id
            LIMIT 1
            FOR UPDATE OF w SKIP LOCKED;

            IF NOT FOUND THEN
                RETURN;
            END IF;

            lease_deadline := clock_timestamp()
                + make_interval(secs => p_lease_seconds);

            INSERT INTO agency_os_private.worker_workspace_capabilities (
                token_hash, org_id, workspace_id, worker_id, expires_at
            ) VALUES (
                p_token_hash, target.org_id, target.id, p_worker_id, lease_deadline
            );

            INSERT INTO public.audit_events (
                id, org_id, workspace_id, actor_user_id, event_type,
                resource_type, resource_id, payload, created_at
            ) VALUES (
                gen_random_uuid()::text, target.org_id, target.id, NULL,
                'worker.maintenance_scope_claimed', 'workspace', target.id,
                jsonb_build_object('worker_id', p_worker_id, 'lease_seconds', p_lease_seconds)::json,
                clock_timestamp()
            );

            RETURN QUERY SELECT target.org_id::text, target.id::text;
        END
        $function$
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        raise RuntimeError(
            "Unsafe downgrade refused: it would restore the varchar/text "
            "return-type mismatch in claim_worker_maintenance_scope."
        )
