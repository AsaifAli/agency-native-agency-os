"""Allow founder-provisioned service identities to use session-bound MCP credentials.

Revision ID: b7d4c9a2e6f1
Revises: a8c4e6f2b913
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b7d4c9a2e6f1"
down_revision: Union[str, Sequence[str], None] = "a8c4e6f2b913"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    # Interactive service clients do not have a worker execution lease. They
    # receive a separate, founder-provisioned identity and one credential per
    # bounded OS session. The function is the only app-role insert path.
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
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.issue_service_mcp_session_credential(text,text,text,text,text,text,text,timestamptz,timestamptz) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.issue_service_mcp_session_credential(text,text,text,text,text,text,text,timestamptz,timestamptz) TO agency_os_app")

    # Preserve execution binding for agent identities; permit service identities
    # only when their own machine grant explicitly allows session creation and
    # tool invocation. Worker identities remain execution-bound.
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.authenticate_mcp_session_credential(
            p_credential_id text,
            p_token_hash text,
            p_requests_per_minute integer DEFAULT 120
        )
        RETURNS TABLE(
            auth_status text, org_id text, workspace_id text,
            machine_identity_id text, session_id text, credential_id text
        )
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE
            c record;
            v_now timestamptz := clock_timestamp();
            v_limit integer := greatest(1, least(coalesce(p_requests_per_minute, 120), 1000));
        BEGIN
            IF p_credential_id IS NULL OR length(p_credential_id) <> 36
               OR p_token_hash IS NULL OR p_token_hash !~ '^[0-9a-f]{64}$' THEN
                RETURN;
            END IF;

            SELECT cred.id, cred.org_id, cred.workspace_id,
                   cred.machine_identity_id, cred.session_id,
                   cred.request_window_started_at, cred.request_count_window,
                   mi.subject_type
              INTO c
              FROM public.machine_session_credentials AS cred
              JOIN public.machine_identities AS mi
                ON mi.id = cred.machine_identity_id
               AND mi.org_id = cred.org_id
               AND mi.workspace_id = cred.workspace_id
              JOIN public.agent_sessions AS s
                ON s.id = cred.session_id
               AND s.org_id = cred.org_id
               AND s.workspace_id = cred.workspace_id
               AND s.machine_identity_id = mi.id
             WHERE cred.id = p_credential_id
               AND cred.token_hash = p_token_hash
               AND cred.revoked_at IS NULL
               AND cred.expires_at > v_now
               AND mi.revoked_at IS NULL
               AND mi.expires_at > v_now
               AND s.status = 'active'
               AND s.expires_at > v_now
               AND s.data_class IN ('synthetic', 'public')
               AND mi.subject_type IN ('agent', 'worker', 'service')
               AND (
                    mi.subject_type IN ('agent', 'worker')
                    OR (mi.subject_type = 'service'
                        AND mi.scopes::jsonb ? 'sessions:create'
                        AND mi.scopes::jsonb ? 'tools:invoke'
                        AND mi.allowed_data_classes::jsonb ? s.data_class)
               )
             FOR UPDATE OF cred, mi, s;

            IF NOT FOUND THEN
                RETURN;
            END IF;
            IF c.subject_type IN ('agent', 'worker') THEN
                PERFORM 1 FROM public.executions AS e
                 WHERE e.org_id = c.org_id
                   AND e.workspace_id = c.workspace_id
                   AND e.machine_session_id = c.session_id
                   AND e.status::text = 'running'
                 FOR UPDATE;
                IF NOT FOUND THEN RETURN; END IF;
            END IF;

            IF c.request_window_started_at IS NULL
               OR c.request_window_started_at <= v_now - interval '1 minute' THEN
                UPDATE public.machine_session_credentials
                   SET request_window_started_at = v_now,
                       request_count_window = 1,
                       last_used_at = v_now
                 WHERE id = c.id;
            ELSIF c.request_count_window >= v_limit THEN
                RETURN QUERY SELECT 'rate_limited'::text, c.org_id::text,
                    c.workspace_id::text, c.machine_identity_id::text,
                    c.session_id::text, c.id::text;
                RETURN;
            ELSE
                UPDATE public.machine_session_credentials
                   SET request_count_window = request_count_window + 1,
                       last_used_at = v_now
                 WHERE id = c.id;
            END IF;

            UPDATE public.machine_identities SET last_used_at = v_now
             WHERE id = c.machine_identity_id;
            UPDATE public.agent_sessions SET last_seen_at = v_now
             WHERE id = c.session_id;

            RETURN QUERY SELECT 'ok'::text, c.org_id::text, c.workspace_id::text,
                c.machine_identity_id::text, c.session_id::text, c.id::text;
        END
        $function$
    """)
    op.execute("ALTER FUNCTION agency_os_private.authenticate_mcp_session_credential(text,text,integer) OWNER TO agency_os_migrator")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.authenticate_mcp_session_credential(text,text,integer) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.authenticate_mcp_session_credential(text,text,integer) TO agency_os_app")

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.is_mcp_session_credential_active(
            p_credential_id text, p_token_hash text, p_org_id text,
            p_workspace_id text, p_machine_identity_id text, p_session_id text
        ) RETURNS boolean
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE v_subject_type text;
        BEGIN
            SELECT mi.subject_type INTO v_subject_type
              FROM public.machine_session_credentials AS cred
              JOIN public.machine_identities AS mi
                ON mi.id = cred.machine_identity_id
               AND mi.org_id = cred.org_id
               AND mi.workspace_id = cred.workspace_id
              JOIN public.agent_sessions AS s
                ON s.id = cred.session_id
               AND s.org_id = cred.org_id
               AND s.workspace_id = cred.workspace_id
               AND s.machine_identity_id = mi.id
             WHERE cred.id = p_credential_id
               AND cred.token_hash = p_token_hash
               AND cred.org_id = p_org_id
               AND cred.workspace_id = p_workspace_id
               AND cred.machine_identity_id = p_machine_identity_id
               AND cred.session_id = p_session_id
               AND cred.revoked_at IS NULL
               AND cred.expires_at > clock_timestamp()
               AND mi.revoked_at IS NULL
               AND mi.expires_at > clock_timestamp()
               AND s.status = 'active'
               AND s.expires_at > clock_timestamp()
               AND s.data_class IN ('synthetic', 'public')
               AND mi.subject_type IN ('agent', 'worker', 'service')
               AND (
                    mi.subject_type IN ('agent', 'worker')
                    OR (mi.subject_type = 'service'
                        AND mi.scopes::jsonb ? 'sessions:create'
                        AND mi.scopes::jsonb ? 'tools:invoke'
                        AND mi.allowed_data_classes::jsonb ? s.data_class)
               )
             FOR UPDATE OF cred, mi, s;
            IF NOT FOUND THEN RETURN false; END IF;
            IF v_subject_type IN ('agent', 'worker') THEN
                PERFORM 1 FROM public.executions AS e
                 WHERE e.org_id = p_org_id
                   AND e.workspace_id = p_workspace_id
                   AND e.machine_session_id = p_session_id
                   AND e.status::text = 'running'
                 FOR UPDATE;
                RETURN FOUND;
            END IF;
            RETURN v_subject_type = 'service';
        END
        $function$
    """)
    op.execute("ALTER FUNCTION agency_os_private.is_mcp_session_credential_active(text,text,text,text,text,text) OWNER TO agency_os_migrator")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.is_mcp_session_credential_active(text,text,text,text,text,text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.is_mcp_session_credential_active(text,text,text,text,text,text) TO agency_os_app")

    # App can revoke credentials only for the exact service identity/session
    # it authenticated. It cannot enumerate or mutate the credential table.
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
            IF session_user NOT IN ('agency_os_app', 'agency_os_test_app') THEN
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
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.revoke_service_mcp_session_credentials(text,text,text,text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.revoke_service_mcp_session_credentials(text,text,text,text) TO agency_os_app")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        UPDATE public.machine_session_credentials AS cred
           SET revoked_at = coalesce(cred.revoked_at, clock_timestamp()),
               revocation_reason = coalesce(cred.revocation_reason, 'MIGRATION_ROLLBACK'),
               provider_credential_status = 'deleted'
          FROM public.machine_identities AS mi
         WHERE mi.id = cred.machine_identity_id
           AND mi.org_id = cred.org_id
           AND mi.workspace_id = cred.workspace_id
           AND mi.subject_type = 'service'
           AND cred.revoked_at IS NULL
    """)
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.revoke_service_mcp_session_credentials(text,text,text,text) FROM PUBLIC, agency_os_app")
    op.execute("DROP FUNCTION IF EXISTS agency_os_private.revoke_service_mcp_session_credentials(text,text,text,text)")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.issue_service_mcp_session_credential(text,text,text,text,text,text,text,timestamptz,timestamptz) FROM PUBLIC, agency_os_app")
    op.execute("DROP FUNCTION IF EXISTS agency_os_private.issue_service_mcp_session_credential(text,text,text,text,text,text,text,timestamptz,timestamptz)")

    # Restore the execution-bound Managed Agents-only authentication functions.
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.authenticate_mcp_session_credential(
            p_credential_id text, p_token_hash text,
            p_requests_per_minute integer DEFAULT 120
        ) RETURNS TABLE(
            auth_status text, org_id text, workspace_id text,
            machine_identity_id text, session_id text, credential_id text
        )
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE
            c record;
            v_now timestamptz := clock_timestamp();
            v_limit integer := greatest(1, least(coalesce(p_requests_per_minute, 120), 1000));
        BEGIN
            IF p_credential_id IS NULL OR length(p_credential_id) <> 36
               OR p_token_hash IS NULL OR p_token_hash !~ '^[0-9a-f]{64}$' THEN
                RETURN;
            END IF;
            SELECT cred.id, cred.org_id, cred.workspace_id,
                   cred.machine_identity_id, cred.session_id,
                   cred.request_window_started_at, cred.request_count_window
              INTO c
              FROM public.machine_session_credentials AS cred
              JOIN public.machine_identities AS mi
                ON mi.id = cred.machine_identity_id
               AND mi.org_id = cred.org_id AND mi.workspace_id = cred.workspace_id
              JOIN public.agent_sessions AS s
                ON s.id = cred.session_id AND s.org_id = cred.org_id
               AND s.workspace_id = cred.workspace_id AND s.machine_identity_id = mi.id
              JOIN public.executions AS e
                ON e.org_id = cred.org_id AND e.workspace_id = cred.workspace_id
               AND e.machine_session_id = cred.session_id AND e.status::text = 'running'
             WHERE cred.id = p_credential_id AND cred.token_hash = p_token_hash
               AND cred.revoked_at IS NULL AND cred.expires_at > v_now
               AND mi.revoked_at IS NULL AND mi.expires_at > v_now
               AND s.status = 'active' AND s.expires_at > v_now
               AND s.data_class IN ('synthetic', 'public')
             FOR UPDATE OF cred, mi, s, e;
            IF NOT FOUND THEN RETURN; END IF;
            IF c.request_window_started_at IS NULL
               OR c.request_window_started_at <= v_now - interval '1 minute' THEN
                UPDATE public.machine_session_credentials
                   SET request_window_started_at = v_now,
                       request_count_window = 1, last_used_at = v_now
                 WHERE id = c.id;
            ELSIF c.request_count_window >= v_limit THEN
                RETURN QUERY SELECT 'rate_limited'::text, c.org_id::text,
                    c.workspace_id::text, c.machine_identity_id::text,
                    c.session_id::text, c.id::text;
                RETURN;
            ELSE
                UPDATE public.machine_session_credentials
                   SET request_count_window = request_count_window + 1,
                       last_used_at = v_now WHERE id = c.id;
            END IF;
            UPDATE public.machine_identities SET last_used_at = v_now WHERE id = c.machine_identity_id;
            UPDATE public.agent_sessions SET last_seen_at = v_now WHERE id = c.session_id;
            RETURN QUERY SELECT 'ok'::text, c.org_id::text, c.workspace_id::text,
                c.machine_identity_id::text, c.session_id::text, c.id::text;
        END
        $function$
    """)
    op.execute("ALTER FUNCTION agency_os_private.authenticate_mcp_session_credential(text,text,integer) OWNER TO agency_os_migrator")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.authenticate_mcp_session_credential(text,text,integer) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.authenticate_mcp_session_credential(text,text,integer) TO agency_os_app")

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.is_mcp_session_credential_active(
            p_credential_id text, p_token_hash text, p_org_id text,
            p_workspace_id text, p_machine_identity_id text, p_session_id text
        ) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        BEGIN
            PERFORM 1
              FROM public.machine_session_credentials AS cred
              JOIN public.machine_identities AS mi
                ON mi.id = cred.machine_identity_id
               AND mi.org_id = cred.org_id AND mi.workspace_id = cred.workspace_id
              JOIN public.agent_sessions AS s
                ON s.id = cred.session_id AND s.org_id = cred.org_id
               AND s.workspace_id = cred.workspace_id AND s.machine_identity_id = mi.id
              JOIN public.executions AS e
                ON e.org_id = cred.org_id AND e.workspace_id = cred.workspace_id
               AND e.machine_session_id = cred.session_id AND e.status::text = 'running'
             WHERE cred.id = p_credential_id AND cred.token_hash = p_token_hash
               AND cred.org_id = p_org_id AND cred.workspace_id = p_workspace_id
               AND cred.machine_identity_id = p_machine_identity_id
               AND cred.session_id = p_session_id
               AND cred.revoked_at IS NULL AND cred.expires_at > clock_timestamp()
               AND mi.revoked_at IS NULL AND mi.expires_at > clock_timestamp()
               AND s.status = 'active' AND s.expires_at > clock_timestamp()
               AND s.data_class IN ('synthetic', 'public')
             FOR UPDATE OF cred, mi, s, e;
            RETURN FOUND;
        END
        $function$
    """)
    op.execute("ALTER FUNCTION agency_os_private.is_mcp_session_credential_active(text,text,text,text,text,text) OWNER TO agency_os_migrator")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.is_mcp_session_credential_active(text,text,text,text,text,text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.is_mcp_session_credential_active(text,text,text,text,text,text) TO agency_os_app")
