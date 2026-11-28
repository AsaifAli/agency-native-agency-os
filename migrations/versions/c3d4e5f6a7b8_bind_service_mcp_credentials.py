"""Bind service MCP credential functions to the authenticated machine identity.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    # These functions are SECURITY DEFINER and are callable by the API role.
    # Bind their target identity and workspace to the transaction-local context
    # established only after machine bearer authentication.
    op.execute("""
CREATE OR REPLACE FUNCTION agency_os_private.issue_service_mcp_session_credential(
            p_credential_id text,
            p_org_id text,
            p_workspace_id text,
            p_machine_identity_id text,
            p_session_id text,
            p_token_hash text,
            p_token_prefix text,
            p_expires_at timestamptz,
            p_created_at timestamptz
        ) RETURNS boolean
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        BEGIN
            IF session_user NOT IN ('agency_os_app', 'agency_os_test_app')
               OR nullif(current_setting('agency_os.machine_identity_lookup_id', true), '') IS DISTINCT FROM p_machine_identity_id
               OR nullif(current_setting('agency_os.machine_org_id', true), '') IS DISTINCT FROM p_org_id
               OR nullif(current_setting('agency_os.machine_workspace_id', true), '') IS DISTINCT FROM p_workspace_id
               OR p_credential_id !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
               OR p_token_hash !~ '^[0-9a-f]{64}$'
               OR p_token_prefix IS NULL OR length(p_token_prefix) > 80
               OR p_expires_at IS NULL OR p_created_at IS NULL THEN
                RETURN false;
            END IF;

            PERFORM 1
              FROM public.machine_identities AS mi
              JOIN public.agent_sessions AS s
                ON s.org_id = mi.org_id
               AND s.workspace_id = mi.workspace_id
               AND s.machine_identity_id = mi.id
             WHERE mi.id = p_machine_identity_id
               AND mi.org_id = p_org_id
               AND mi.workspace_id = p_workspace_id
               AND mi.subject_type = 'service'
               AND mi.revoked_at IS NULL
               AND mi.expires_at > clock_timestamp()
               AND mi.scopes::jsonb ? 'sessions:create'
               AND mi.scopes::jsonb ? 'tools:invoke'
               AND mi.allowed_data_classes::jsonb ? s.data_class
               AND s.id = p_session_id
               AND s.status = 'active'
               AND s.expires_at > clock_timestamp()
               AND s.data_class IN ('synthetic', 'public')
               AND p_expires_at > clock_timestamp()
               AND p_expires_at <= LEAST(s.expires_at, mi.expires_at)
             FOR UPDATE OF mi, s;

            IF NOT FOUND THEN
                RETURN false;
            END IF;

            INSERT INTO public.machine_session_credentials (
                id, org_id, workspace_id, machine_identity_id, session_id,
                token_hash, token_prefix, credential_version, expires_at,
                request_window_started_at, request_count_window,
                provider_credential_status, created_at
            ) VALUES (
                p_credential_id, p_org_id, p_workspace_id, p_machine_identity_id,
                p_session_id, p_token_hash, p_token_prefix, 1, p_expires_at,
                p_created_at, 0, 'not_created', p_created_at
            );
            RETURN true;
        EXCEPTION WHEN unique_violation THEN
            RETURN false;
        END
        $function$
    """)
    op.execute("ALTER FUNCTION agency_os_private.issue_service_mcp_session_credential(text,text,text,text,text,text,text,timestamptz,timestamptz) OWNER TO agency_os_migrator")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.issue_service_mcp_session_credential(text,text,text,text,text,text,text,timestamptz,timestamptz) FROM PUBLIC, agency_os_worker")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.issue_service_mcp_session_credential(text,text,text,text,text,text,text,timestamptz,timestamptz) TO agency_os_app")

    op.execute("""
CREATE OR REPLACE FUNCTION agency_os_private.revoke_service_mcp_session_credentials(
            p_org_id text, p_workspace_id text,
            p_machine_identity_id text, p_session_id text
        ) RETURNS integer
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE v_count integer;
        BEGIN
            IF session_user NOT IN ('agency_os_app', 'agency_os_test_app')
               OR nullif(current_setting('agency_os.machine_identity_lookup_id', true), '') IS DISTINCT FROM p_machine_identity_id
               OR nullif(current_setting('agency_os.machine_org_id', true), '') IS DISTINCT FROM p_org_id
               OR nullif(current_setting('agency_os.machine_workspace_id', true), '') IS DISTINCT FROM p_workspace_id THEN
                RETURN -1;
            END IF;
            PERFORM 1
              FROM public.machine_identities AS mi
              JOIN public.agent_sessions AS s
                ON s.org_id = mi.org_id
               AND s.workspace_id = mi.workspace_id
               AND s.machine_identity_id = mi.id
             WHERE mi.id = p_machine_identity_id
               AND mi.org_id = p_org_id
               AND mi.workspace_id = p_workspace_id
               AND mi.subject_type = 'service'
               AND s.id = p_session_id;
            IF NOT FOUND THEN
                RETURN -1;
            END IF;
            -- Match authentication's lock order (credential, identity, session)
            -- to avoid a revoke-vs-call deadlock.
            PERFORM 1 FROM public.machine_session_credentials AS cred
             WHERE cred.org_id = p_org_id
               AND cred.workspace_id = p_workspace_id
               AND cred.machine_identity_id = p_machine_identity_id
               AND cred.session_id = p_session_id
             FOR UPDATE;
            PERFORM 1
              FROM public.machine_identities AS mi
              JOIN public.agent_sessions AS s
                ON s.org_id = mi.org_id
               AND s.workspace_id = mi.workspace_id
               AND s.machine_identity_id = mi.id
             WHERE mi.id = p_machine_identity_id
               AND mi.org_id = p_org_id
               AND mi.workspace_id = p_workspace_id
               AND mi.subject_type = 'service'
               AND s.id = p_session_id
             FOR UPDATE OF mi, s;
            IF NOT FOUND THEN
                RETURN -1;
            END IF;
            UPDATE public.machine_session_credentials AS cred
               SET revoked_at = coalesce(cred.revoked_at, clock_timestamp()),
                   revocation_reason = coalesce(cred.revocation_reason, 'CLIENT_SESSION_REVOKED'),
                   provider_credential_status = CASE
                       WHEN cred.provider_credential_id IS NULL THEN 'deleted'
                       ELSE 'delete_pending'
                   END
             WHERE cred.org_id = p_org_id
               AND cred.workspace_id = p_workspace_id
               AND cred.machine_identity_id = p_machine_identity_id
               AND cred.session_id = p_session_id
               AND cred.revoked_at IS NULL;
            GET DIAGNOSTICS v_count = ROW_COUNT;
            RETURN v_count;
        END
        $function$
    """)
    op.execute("ALTER FUNCTION agency_os_private.revoke_service_mcp_session_credentials(text,text,text,text) OWNER TO agency_os_migrator")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.revoke_service_mcp_session_credentials(text,text,text,text) FROM PUBLIC, agency_os_worker")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.revoke_service_mcp_session_credentials(text,text,text,text) TO agency_os_app")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Unsafe downgrade refused: restoring unbound service credential functions "
        "would remove the authenticated machine-identity boundary"
    )
