"""Add execution-bound MCP bearer credentials with database-owned authentication.

Revision ID: r4b8d2f6a103
Revises: aa1b2c3d4e5f
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "r4b8d2f6a103"
down_revision: Union[str, Sequence[str], None] = ("aa1b2c3d4e5f", "a7b2c9d4e1f6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch:
        batch.create_unique_constraint(
            "uq_agent_session_identity_scope_id",
            ["org_id", "workspace_id", "machine_identity_id", "id"],
        )

    op.create_table(
        "machine_session_credentials",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("machine_identity_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_prefix", sa.String(80), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revocation_reason", sa.String(80)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("request_window_started_at", sa.DateTime(timezone=True)),
        sa.Column("request_count_window", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_vault_id", sa.String(160)),
        sa.Column("provider_credential_id", sa.String(160)),
        sa.Column("provider_credential_status", sa.String(24), nullable=False, server_default="not_created"),
        sa.Column("provider_credential_created_at", sa.DateTime(timezone=True)),
        sa.Column("provider_credential_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("token_hash", name="uq_machine_session_credential_token_hash"),
        sa.UniqueConstraint(
            "org_id", "workspace_id", "session_id", "credential_version",
            name="uq_machine_session_credential_version",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id", "machine_identity_id", "session_id"],
            [
                "agent_sessions.org_id",
                "agent_sessions.workspace_id",
                "agent_sessions.machine_identity_id",
                "agent_sessions.id",
            ],
            ondelete="CASCADE",
            name="fk_machine_session_credential_session_identity_scope",
        ),
        sa.CheckConstraint("credential_version >= 1", name="ck_machine_session_credential_version"),
        sa.CheckConstraint("request_count_window >= 0", name="ck_machine_session_credential_request_count"),
        sa.CheckConstraint(
            "provider_credential_status IN ('not_created','active','delete_pending','deleted','failed')",
            name="ck_machine_session_credential_provider_status",
        ),
    )
    op.create_index(
        "ix_machine_session_credential_session_revoked",
        "machine_session_credentials",
        ["org_id", "workspace_id", "session_id", "revoked_at"],
    )

    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE public.machine_session_credentials ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.machine_session_credentials FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY worker_mcp_credential_insert
        ON public.machine_session_credentials
        FOR INSERT TO agency_os_worker
        WITH CHECK (
            session_user = 'agency_os_worker'
            AND EXISTS (
                SELECT 1
                FROM public.executions AS e
                JOIN public.machine_identities AS mi
                  ON mi.org_id = e.org_id
                 AND mi.workspace_id = e.workspace_id
                 AND mi.subject_type = 'agent'
                 AND mi.subject_id = e.agent_id
                 AND mi.id = machine_session_credentials.machine_identity_id
                JOIN public.agent_sessions AS s
                  ON s.org_id = e.org_id
                 AND s.workspace_id = e.workspace_id
                 AND s.id = e.machine_session_id
                 AND s.machine_identity_id = mi.id
                 AND s.id = machine_session_credentials.session_id
                WHERE e.org_id = machine_session_credentials.org_id
                  AND e.workspace_id = machine_session_credentials.workspace_id
                  AND agency_os_private.worker_has_execution_context(
                      e.org_id, e.workspace_id, e.id
                  )
                  AND e.status::text = 'running'
                  AND s.status = 'active'
                  AND s.expires_at > clock_timestamp()
                  AND mi.revoked_at IS NULL
                  AND mi.expires_at > clock_timestamp()
            )
        )
    """)

    # The app role cannot SELECT token hashes or enumerate credentials. It can
    # authenticate one presented credential through this fixed, bounded function.
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.authenticate_mcp_session_credential(
            p_credential_id text,
            p_token_hash text,
            p_requests_per_minute integer DEFAULT 120
        )
        RETURNS TABLE(
            auth_status text,
            org_id text,
            workspace_id text,
            machine_identity_id text,
            session_id text,
            credential_id text
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
                   cred.request_window_started_at, cred.request_count_window
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
             FOR UPDATE OF cred, mi, s;

            IF NOT FOUND THEN
                RETURN;
            END IF;

            IF c.request_window_started_at IS NULL
               OR c.request_window_started_at <= v_now - interval '1 minute' THEN
                UPDATE public.machine_session_credentials
                   SET request_window_started_at = v_now,
                       request_count_window = 1,
                       last_used_at = v_now
                 WHERE id = c.id;
            ELSIF c.request_count_window >= v_limit THEN
                RETURN QUERY SELECT
                    'rate_limited'::text, c.org_id::text, c.workspace_id::text,
                    c.machine_identity_id::text, c.session_id::text, c.id::text;
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

            RETURN QUERY SELECT
                'ok'::text, c.org_id::text, c.workspace_id::text,
                c.machine_identity_id::text, c.session_id::text, c.id::text;
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.authenticate_mcp_session_credential(text, text, integer)
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION agency_os_private.authenticate_mcp_session_credential(text, text, integer)
        FROM PUBLIC
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION agency_os_private.authenticate_mcp_session_credential(text, text, integer)
        TO agency_os_app
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.is_mcp_session_credential_active(
            p_credential_id text,
            p_token_hash text,
            p_org_id text,
            p_workspace_id text,
            p_machine_identity_id text,
            p_session_id text
        ) RETURNS boolean
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        BEGIN
            PERFORM 1
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
             FOR UPDATE OF cred, mi, s;
            RETURN FOUND;
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.is_mcp_session_credential_active(text, text, text, text, text, text)
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION agency_os_private.is_mcp_session_credential_active(text, text, text, text, text, text)
        FROM PUBLIC
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION agency_os_private.is_mcp_session_credential_active(text, text, text, text, text, text)
        TO agency_os_app
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.attach_mcp_provider_credential(
            p_credential_id text, p_vault_id text, p_provider_credential_id text
        ) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE v_count integer;
        BEGIN
            IF session_user <> 'agency_os_worker'
               OR p_credential_id IS NULL OR length(p_credential_id) <> 36
               OR p_vault_id IS NULL OR length(p_vault_id) > 160
               OR p_provider_credential_id IS NULL OR length(p_provider_credential_id) > 160 THEN
                RETURN false;
            END IF;
            UPDATE public.machine_session_credentials AS cred
               SET provider_vault_id = p_vault_id,
                   provider_credential_id = p_provider_credential_id,
                   provider_credential_status = 'active',
                   provider_credential_created_at = coalesce(provider_credential_created_at, clock_timestamp())
              FROM public.executions AS e
             WHERE cred.id = p_credential_id
               AND e.org_id = cred.org_id
               AND e.workspace_id = cred.workspace_id
               AND e.machine_session_id = cred.session_id
               AND e.status::text = 'running'
               AND agency_os_private.worker_has_execution_context(e.org_id, e.workspace_id, e.id)
               AND cred.revoked_at IS NULL
               AND cred.provider_credential_status IN ('not_created', 'active')
               AND (cred.provider_vault_id IS NULL OR cred.provider_vault_id = p_vault_id)
               AND (cred.provider_credential_id IS NULL OR cred.provider_credential_id = p_provider_credential_id);
            GET DIAGNOSTICS v_count = ROW_COUNT;
            RETURN v_count = 1;
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.attach_mcp_provider_credential(text, text, text)
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION agency_os_private.attach_mcp_provider_credential(text, text, text)
        FROM PUBLIC, agency_os_app
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION agency_os_private.attach_mcp_provider_credential(text, text, text)
        TO agency_os_worker
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.revoke_mcp_session_credential(
            p_credential_id text, p_reason text
        ) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE v_count integer;
        BEGIN
            IF session_user <> 'agency_os_worker'
               OR p_credential_id IS NULL OR length(p_credential_id) <> 36
               OR p_reason IS NULL OR p_reason !~ '^[A-Z0-9_]{1,80}
    op.execute("GRANT INSERT ON public.machine_session_credentials TO agency_os_worker")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            REVOKE ALL ON FUNCTION agency_os_private.authenticate_mcp_session_credential(text, text, integer)
            FROM PUBLIC, agency_os_app
        """)
        op.execute("""
            DROP FUNCTION IF EXISTS agency_os_private.authenticate_mcp_session_credential(text, text, integer)
        """)
        op.execute("""
            DROP FUNCTION IF EXISTS agency_os_private.is_mcp_session_credential_active(text, text, text, text, text, text)
        """)
        op.execute("""
            DROP FUNCTION IF EXISTS agency_os_private.attach_mcp_provider_credential(text, text, text)
        """)
        op.execute("""
            DROP FUNCTION IF EXISTS agency_os_private.revoke_mcp_session_credential(text, text)
        """)
        op.execute("""
            DROP FUNCTION IF EXISTS agency_os_private.mark_mcp_provider_credential_archived(text, text)
        """)
        op.execute("""
            DROP POLICY IF EXISTS worker_mcp_credential_insert
            ON public.machine_session_credentials
        """)
        op.execute("REVOKE ALL ON public.machine_session_credentials FROM agency_os_worker, agency_os_app")
    op.drop_index(
        "ix_machine_session_credential_session_revoked",
        table_name="machine_session_credentials",
    )
    op.drop_table("machine_session_credentials")
    with op.batch_alter_table("agent_sessions") as batch:
        batch.drop_constraint("uq_agent_session_identity_scope_id", type_="unique")
 THEN
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
        CREATE OR REPLACE FUNCTION agency_os_private.mark_mcp_provider_credential_archived(
            p_credential_id text, p_provider_credential_id text
        ) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
        DECLARE v_count integer;
        BEGIN
            IF session_user <> 'agency_os_worker'
               OR p_credential_id IS NULL OR length(p_credential_id) <> 36
               OR p_provider_credential_id IS NULL OR length(p_provider_credential_id) > 160 THEN
                RETURN false;
            END IF;
            UPDATE public.machine_session_credentials AS cred
               SET provider_credential_status = 'deleted',
                   provider_credential_deleted_at = coalesce(provider_credential_deleted_at, clock_timestamp()),
                   revoked_at = coalesce(revoked_at, clock_timestamp()),
                   revocation_reason = coalesce(revocation_reason, 'PROVIDER_CREDENTIAL_ARCHIVED')
              FROM public.executions AS e
             WHERE cred.id = p_credential_id
               AND cred.provider_credential_id = p_provider_credential_id
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
        ALTER FUNCTION agency_os_private.mark_mcp_provider_credential_archived(text, text)
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION agency_os_private.mark_mcp_provider_credential_archived(text, text)
        FROM PUBLIC, agency_os_app
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION agency_os_private.mark_mcp_provider_credential_archived(text, text)
        TO agency_os_worker
    """)

    op.execute("REVOKE ALL ON public.machine_session_credentials FROM PUBLIC, agency_os_app, agency_os_worker")
    op.execute("GRANT INSERT ON public.machine_session_credentials TO agency_os_worker")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
            REVOKE ALL ON FUNCTION agency_os_private.authenticate_mcp_session_credential(text, text, integer)
            FROM PUBLIC, agency_os_app
        """)
        op.execute("""
            DROP FUNCTION IF EXISTS agency_os_private.authenticate_mcp_session_credential(text, text, integer)
        """)
        op.execute("""
            DROP POLICY IF EXISTS worker_mcp_credential_insert
            ON public.machine_session_credentials
        """)
        op.execute("REVOKE ALL ON public.machine_session_credentials FROM agency_os_worker, agency_os_app")
    op.drop_index(
        "ix_machine_session_credential_session_revoked",
        table_name="machine_session_credentials",
    )
    op.drop_table("machine_session_credentials")
    with op.batch_alter_table("agent_sessions") as batch:
        batch.drop_constraint("uq_agent_session_identity_scope_id", type_="unique")
