"""Bound active MCP credentials per Anthropic Vault.

A Vault supports at most 20 credentials. Reserve capacity in the OS database
before the external credential call so concurrent workers cannot overbook it.
Ambiguous provider-create outcomes keep their reservation until manual
reconciliation instead of silently freeing a potentially occupied slot.
"""
from alembic import op

revision = "a8c4e6f2b913"
down_revision = "z6f1b3d8a2c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.reserve_mcp_vault_credential_slot(
            p_vault_id text,
            p_max_active_credentials integer DEFAULT 16
        ) RETURNS boolean
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE
            v_active_count integer;
            v_limit integer := greatest(1, least(coalesce(p_max_active_credentials, 16), 20));
        BEGIN
            IF session_user <> 'agency_os_worker'
               OR p_vault_id IS NULL
               OR p_vault_id !~ '^vlt_[A-Za-z0-9_-]{1,150}$' THEN
                RETURN false;
            END IF;

            -- Transaction-scoped lock serializes the count + credential INSERT.
            -- The caller must insert the reservation row and commit in this
            -- same transaction after this function returns true.
            PERFORM pg_advisory_xact_lock(hashtextextended(p_vault_id, 0));

            SELECT count(*)::integer
              INTO v_active_count
              FROM public.machine_session_credentials AS cred
             WHERE cred.provider_vault_id = p_vault_id
               AND cred.provider_credential_status IN ('not_created', 'active', 'delete_pending');

            RETURN v_active_count < v_limit;
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.reserve_mcp_vault_credential_slot(text, integer)
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION agency_os_private.reserve_mcp_vault_credential_slot(text, integer)
        FROM PUBLIC, agency_os_app
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION agency_os_private.reserve_mcp_vault_credential_slot(text, integer)
        TO agency_os_worker
    """)

    # An ambiguous Vault create may have succeeded even when the provider ID
    # was not received. Keep the slot reserved until an operator reconciles it.
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.revoke_mcp_session_credential(
            p_credential_id text, p_reason text
        ) RETURNS boolean
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE v_count integer;
        BEGIN
            IF session_user <> 'agency_os_worker'
               OR p_credential_id IS NULL OR length(p_credential_id) <> 36
               OR p_reason IS NULL OR p_reason !~ '^[A-Z0-9_]{1,80}$' THEN
                RETURN false;
            END IF;
            UPDATE public.machine_session_credentials AS cred
               SET revoked_at = coalesce(revoked_at, clock_timestamp()),
                   revocation_reason = coalesce(revocation_reason, p_reason),
                   provider_credential_status = CASE
                       WHEN provider_credential_id IS NOT NULL THEN 'delete_pending'
                       WHEN p_reason IN ('MCP_VAULT_CREATE_AMBIGUOUS', 'MCP_ORPHANED_CREDENTIAL')
                           THEN 'delete_pending'
                       ELSE 'deleted'
                   END
              FROM public.executions AS e
             WHERE cred.id = p_credential_id
               AND e.org_id = cred.org_id
               AND e.workspace_id = cred.workspace_id
               AND e.machine_session_id = cred.session_id
               AND e.status::text = 'running'
               AND agency_os_private.worker_has_execution_context(e.org_id, e.workspace_id, e.id);
            GET DIAGNOSTICS v_count = ROW_COUNT;
            RETURN v_count = 1;
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.revoke_mcp_session_credential(text, text)
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION agency_os_private.revoke_mcp_session_credential(text, text)
        FROM PUBLIC, agency_os_app
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION agency_os_private.revoke_mcp_session_credential(text, text)
        TO agency_os_worker
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.revoke_mcp_session_credential(
            p_credential_id text, p_reason text
        ) RETURNS boolean
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE v_count integer;
        BEGIN
            IF session_user <> 'agency_os_worker'
               OR p_credential_id IS NULL OR length(p_credential_id) <> 36
               OR p_reason IS NULL OR p_reason !~ '^[A-Z0-9_]{1,80}$' THEN
                RETURN false;
            END IF;
            UPDATE public.machine_session_credentials AS cred
               SET revoked_at = coalesce(revoked_at, clock_timestamp()),
                   revocation_reason = coalesce(revocation_reason, p_reason),
                   provider_credential_status = CASE
                       WHEN provider_credential_id IS NULL THEN 'deleted'
                       ELSE 'delete_pending'
                   END
              FROM public.executions AS e
             WHERE cred.id = p_credential_id
               AND e.org_id = cred.org_id
               AND e.workspace_id = cred.workspace_id
               AND e.machine_session_id = cred.session_id
               AND e.status::text = 'running'
               AND agency_os_private.worker_has_execution_context(e.org_id, e.workspace_id, e.id);
            GET DIAGNOSTICS v_count = ROW_COUNT;
            RETURN v_count = 1;
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.revoke_mcp_session_credential(text, text)
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION agency_os_private.revoke_mcp_session_credential(text, text)
        FROM PUBLIC, agency_os_app
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION agency_os_private.revoke_mcp_session_credential(text, text)
        TO agency_os_worker
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION agency_os_private.reserve_mcp_vault_credential_slot(text, integer)
        FROM PUBLIC, agency_os_worker, agency_os_app
    """)
    op.execute("""
        DROP FUNCTION IF EXISTS agency_os_private.reserve_mcp_vault_credential_slot(text, integer)
    """)
