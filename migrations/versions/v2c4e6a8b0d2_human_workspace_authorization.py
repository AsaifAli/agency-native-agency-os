"""Introduce explicit, auditable human workspace grants and RLS enforcement.

Existing active organization members are backfilled into every workspace they
could previously access. Future membership/workspace changes do not imply grants.
Machine authorization remains on its independent exact-workspace path.
"""
from alembic import op
import sqlalchemy as sa

revision = "v2c4e6a8b0d2"
down_revision = "u1b2c3d4e5f6"
branch_labels = None
depends_on = None


ORG_LEVEL_NULLABLE_WORKSPACE_TABLES = ("audit_events", "outbox_events")


WORKSPACE_TABLES = (
    "agent_sessions", "agents", "approvals", "audit_events", "call_sessions",
    "call_transcripts", "client_onboardings", "clients",
    "communication_blocks", "communication_consents", "contact_activities",
    "contacts", "contract_records", "delegations", "evaluation_runs",
    "executions", "invoice_records", "lead_research_drafts", "lead_research_records",
    "leads", "machine_identities", "milestones",
    "onboarding_checklist_items", "opportunities", "orchestration_plan_drafts",
    "orchestration_plans", "outbound_message_events", "outbound_messages",
    "outbound_senders", "outbox_events", "outreach_drafts", "payment_receipts",
    "project_costs", "projects", "proposals", "retainer_service_periods",
    "scope_change_requests", "service_offerings", "service_playbooks", "tasks",
    "time_entries", "tool_invocations", "workforce_capabilities",
    "workforce_members", "workforce_positions", "workforce_units",
)


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("created_by", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_workspaces_created_by_users", "workspaces", "users",
        ["created_by"], ["id"],
    )
    op.create_table(
        "workspace_grants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("granted_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_workspace_grants_workspace_org",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"]),
        sa.UniqueConstraint("id", "org_id", "workspace_id", name="uq_workspace_grants_scope_id"),
    )
    op.create_index(
        "uq_workspace_grants_active", "workspace_grants",
        ["org_id", "workspace_id", "user_id"], unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_workspace_grants_user_active", "workspace_grants",
        ["user_id", "revoked_at"],
    )

    # Preserve the exact access users had immediately before this migration.
    op.execute("""
        INSERT INTO public.workspace_grants
            (id, org_id, workspace_id, user_id, granted_by, created_at)
        SELECT gen_random_uuid()::text, w.org_id, w.id, m.user_id, m.user_id, now()
        FROM public.workspaces AS w
        JOIN public.memberships AS m ON m.org_id = w.org_id
        JOIN public.users AS u ON u.id = m.user_id
        WHERE u.active IS TRUE
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.user_has_workspace_access(
            target_org_id text, target_workspace_id text, actor_user_id text
        ) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
            SELECT actor_user_id IS NOT NULL
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
    op.execute("""
        ALTER FUNCTION agency_os_private.user_has_workspace_access(text, text, text)
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON FUNCTION
            agency_os_private.user_has_workspace_access(text, text, text)
        FROM PUBLIC
    """)
    op.execute("""
        GRANT EXECUTE ON FUNCTION
            agency_os_private.user_has_workspace_access(text, text, text)
        TO agency_os_app, agency_os_worker
    """)

    # Grant and revoke are SECURITY DEFINER transactions. The actor argument
    # must equal the transaction-local authenticated identity; clients cannot
    # impersonate a founder by supplying another user ID.
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.grant_workspace_access(
            target_org_id text, target_workspace_id text,
            target_user_id text, actor_user_id text
        ) RETURNS text
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
        DECLARE
            grant_id text;
            is_creator boolean;
            is_founder boolean;
            inserted boolean := false;
        BEGIN
            IF actor_user_id IS NULL OR actor_user_id <>
               nullif(current_setting('agency_os.user_id', true), '') THEN
                RAISE EXCEPTION 'workspace grant actor mismatch' USING ERRCODE = '42501';
            END IF;

            SELECT (w.created_by = actor_user_id AND target_user_id = actor_user_id)
              INTO is_creator
            FROM public.workspaces AS w
            WHERE w.id = target_workspace_id AND w.org_id = target_org_id
            FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'workspace not found' USING ERRCODE = 'P0002';
            END IF;

            SELECT EXISTS (
                SELECT 1 FROM public.founder_authorities AS f
                JOIN public.memberships AS m
                  ON m.org_id = f.org_id AND m.user_id = f.user_id
                JOIN public.users AS u ON u.id = f.user_id
                WHERE f.org_id = target_org_id AND f.user_id = actor_user_id
                  AND f.active IS TRUE AND u.active IS TRUE
            ) INTO is_founder;

            IF NOT coalesce(is_creator, false) AND NOT is_founder THEN
                RAISE EXCEPTION 'explicit founder authority required' USING ERRCODE = '42501';
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM public.memberships AS m
                JOIN public.users AS u ON u.id = m.user_id
                WHERE m.org_id = target_org_id AND m.user_id = target_user_id
                  AND u.active IS TRUE
            ) THEN
                RAISE EXCEPTION 'active organization membership required' USING ERRCODE = '42501';
            END IF;

            grant_id := gen_random_uuid()::text;
            INSERT INTO public.workspace_grants
                (id, org_id, workspace_id, user_id, granted_by, created_at)
            VALUES
                (grant_id, target_org_id, target_workspace_id, target_user_id,
                 actor_user_id, now())
            ON CONFLICT (org_id, workspace_id, user_id)
                WHERE revoked_at IS NULL
            DO NOTHING
            RETURNING id INTO grant_id;

            inserted := grant_id IS NOT NULL;
            IF NOT inserted THEN
                SELECT g.id INTO grant_id
                FROM public.workspace_grants AS g
                WHERE g.org_id = target_org_id
                  AND g.workspace_id = target_workspace_id
                  AND g.user_id = target_user_id
                  AND g.revoked_at IS NULL;
                RETURN grant_id;
            END IF;

            INSERT INTO public.audit_events
                (id, org_id, workspace_id, actor_user_id, event_type,
                 resource_type, resource_id, payload, created_at)
            VALUES
                (gen_random_uuid()::text, target_org_id, target_workspace_id,
                 actor_user_id, 'workspace.access_granted', 'workspace_grant',
                 grant_id, json_build_object('user_id', target_user_id), now());
            RETURN grant_id;
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.grant_workspace_access(text, text, text, text)
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.revoke_workspace_access(
            target_org_id text, target_workspace_id text,
            target_user_id text, actor_user_id text
        ) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
        DECLARE
            grant_row public.workspace_grants%ROWTYPE;
        BEGIN
            IF actor_user_id IS NULL OR actor_user_id <>
               nullif(current_setting('agency_os.user_id', true), '') THEN
                RAISE EXCEPTION 'workspace grant actor mismatch' USING ERRCODE = '42501';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM public.founder_authorities AS f
                JOIN public.memberships AS m
                  ON m.org_id = f.org_id AND m.user_id = f.user_id
                JOIN public.users AS u ON u.id = f.user_id
                WHERE f.org_id = target_org_id AND f.user_id = actor_user_id
                  AND f.active IS TRUE AND u.active IS TRUE
            ) THEN
                RAISE EXCEPTION 'explicit founder authority required' USING ERRCODE = '42501';
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM public.workspaces
                WHERE org_id = target_org_id AND id = target_workspace_id
            ) THEN
                RAISE EXCEPTION 'workspace not found' USING ERRCODE = 'P0002';
            END IF;

            SELECT * INTO grant_row
            FROM public.workspace_grants
            WHERE org_id = target_org_id AND workspace_id = target_workspace_id
              AND user_id = target_user_id AND revoked_at IS NULL
            FOR UPDATE;
            IF NOT FOUND THEN
                RETURN false;
            END IF;

            UPDATE public.workspace_grants
            SET revoked_at = now()
            WHERE id = grant_row.id;

            INSERT INTO public.audit_events
                (id, org_id, workspace_id, actor_user_id, event_type,
                 resource_type, resource_id, payload, created_at)
            VALUES
                (gen_random_uuid()::text, target_org_id, target_workspace_id,
                 actor_user_id, 'workspace.access_revoked', 'workspace_grant',
                 grant_row.id, json_build_object('user_id', target_user_id), now());
            RETURN true;
        END
        $function$
    """)
    op.execute("""
        ALTER FUNCTION agency_os_private.revoke_workspace_access(text, text, text, text)
        OWNER TO agency_os_migrator
    """)
    for signature in (
        "agency_os_private.grant_workspace_access(text, text, text, text)",
        "agency_os_private.revoke_workspace_access(text, text, text, text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO agency_os_app")

    # The grant table is read-only to the API role. Writes occur only through
    # the narrowly scoped audited SECURITY DEFINER functions above.
    op.execute("ALTER TABLE public.workspace_grants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.workspace_grants FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY workspace_grants_read ON public.workspace_grants
        FOR SELECT
        USING (
            user_id = nullif(current_setting('agency_os.user_id', true), '')
        )
    """)
    op.execute("REVOKE ALL ON TABLE public.workspace_grants FROM agency_os_app")
    op.execute("GRANT SELECT ON public.workspace_grants TO agency_os_app")

    # Workspace reads are exact-grant scoped. Creation remains membership/role
    # gated by the API and creator-grant insertion is atomic with that request.
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.workspaces")
    op.execute("""
        CREATE POLICY workspace_select ON public.workspaces
        FOR SELECT
        USING (
            agency_os_private.user_has_workspace_access(
                org_id, id, nullif(current_setting('agency_os.user_id', true), '')
            )
            OR (
                org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                AND id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
            )
        )
    """)
    op.execute("""
        CREATE POLICY workspace_insert ON public.workspaces
        FOR INSERT
        WITH CHECK (
            agency_os_private.user_has_org_access(
                org_id, nullif(current_setting('agency_os.user_id', true), '')
            )
        )
    """)
    op.execute("""
        CREATE POLICY workspace_update ON public.workspaces
        FOR UPDATE
        USING (EXISTS (
            SELECT 1 FROM public.founder_authorities AS f
            WHERE f.org_id = workspaces.org_id
              AND f.user_id = nullif(current_setting('agency_os.user_id', true), '')
              AND f.active IS TRUE
        ))
        WITH CHECK (EXISTS (
            SELECT 1 FROM public.founder_authorities AS f
            WHERE f.org_id = workspaces.org_id
              AND f.user_id = nullif(current_setting('agency_os.user_id', true), '')
              AND f.active IS TRUE
        ))
    """)
    op.execute("""
        CREATE POLICY workspace_delete ON public.workspaces
        FOR DELETE
        USING (EXISTS (
            SELECT 1 FROM public.founder_authorities AS f
            WHERE f.org_id = workspaces.org_id
              AND f.user_id = nullif(current_setting('agency_os.user_id', true), '')
              AND f.active IS TRUE
        ))
    """)

    # Apply the human workspace predicate to every tenant table that actually
    # has workspace_id. Nullable workspace rows remain explicitly org-scoped;
    # non-null workspace rows require the exact grant. Machine scope is intact.
    for table in WORKSPACE_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON public."{table}"')
        if table in ORG_LEVEL_NULLABLE_WORKSPACE_TABLES:
            human_predicate = """
                (
                    (workspace_id IS NULL AND agency_os_private.user_has_org_access(
                        org_id, nullif(current_setting('agency_os.user_id', true), '')
                    ))
                    OR
                    (workspace_id IS NOT NULL AND agency_os_private.user_has_workspace_access(
                        org_id, workspace_id,
                        nullif(current_setting('agency_os.user_id', true), '')
                    ))
                )
            """
            machine_predicate = """
                (
                    org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                    AND (
                        workspace_id IS NULL
                        OR workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                    )
                )
            """ if table == "outbox_events" else """
                (
                    org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                    AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                )
            """
        else:
            human_predicate = """
                agency_os_private.user_has_workspace_access(
                    org_id, workspace_id,
                    nullif(current_setting('agency_os.user_id', true), '')
                )
            """
            machine_predicate = """
                (
                    org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                    AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                )
            """
        policy = f"({human_predicate}) OR ({machine_predicate})"
        op.execute(f'''
            CREATE POLICY tenant_isolation ON public."{table}"
            USING ({policy})
            WITH CHECK ({policy})
        ''')

    # Machine authentication begins with only an opaque identity ID. Permit
    # SELECT of that exact row before org/workspace context is known. This
    # policy grants no INSERT/UPDATE/DELETE access; normal writes still require
    # the exact machine workspace predicate in tenant_isolation.
    op.execute("""
        CREATE POLICY machine_identity_lookup
        ON public.machine_identities
        FOR SELECT
        USING (
            id = nullif(current_setting('agency_os.machine_identity_lookup_id', true), '')
        )
    """)

    # Attempts inherit exact workspace authorization from their parent.
    op.execute("DROP POLICY IF EXISTS execution_attempt_tenant_isolation ON public.execution_attempts")
    op.execute("""
        CREATE POLICY execution_attempt_tenant_isolation
        ON public.execution_attempts
        USING (
            EXISTS (
                SELECT 1 FROM public.executions AS e
                WHERE e.id = execution_id
                  AND (
                    agency_os_private.user_has_workspace_access(
                        e.org_id, e.workspace_id,
                        nullif(current_setting('agency_os.user_id', true), '')
                    )
                    OR (
                        e.org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                        AND e.workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                    )
                  )
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM public.executions AS e
                WHERE e.id = execution_id
                  AND (
                    agency_os_private.user_has_workspace_access(
                        e.org_id, e.workspace_id,
                        nullif(current_setting('agency_os.user_id', true), '')
                    )
                    OR (
                        e.org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                        AND e.workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                    )
                  )
            )
        )
    """)


def downgrade() -> None:
    # Restore the original organization-wide policies before removing the
    # workspace predicate and grant data model.
    op.execute("DROP POLICY IF EXISTS workspace_select ON public.workspaces")
    op.execute("DROP POLICY IF EXISTS workspace_insert ON public.workspaces")
    op.execute("DROP POLICY IF EXISTS workspace_update ON public.workspaces")
    op.execute("DROP POLICY IF EXISTS workspace_delete ON public.workspaces")
    op.execute("DROP POLICY IF EXISTS machine_identity_lookup ON public.machine_identities")
    op.execute("CREATE POLICY tenant_isolation ON public.workspaces USING (agency_os_private.user_has_org_access(org_id, nullif(current_setting('agency_os.user_id', true), '')) OR (org_id = nullif(current_setting('agency_os.machine_org_id', true), '') AND id = nullif(current_setting('agency_os.machine_workspace_id', true), '')) WITH CHECK (agency_os_private.user_has_org_access(org_id, nullif(current_setting('agency_os.user_id', true), '')) OR (org_id = nullif(current_setting('agency_os.machine_org_id', true), '') AND id = nullif(current_setting('agency_os.machine_workspace_id', true), '')))")
    for table in WORKSPACE_TABLES:
        identity_lookup = (
            " OR id = nullif(current_setting('agency_os.machine_identity_lookup_id', true), '')"
            if table == "machine_identities" else ""
        )
        machine_workspace = (
            "(workspace_id IS NULL OR workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), ''))"
            if table == "outbox_events"
            else "workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')"
        )
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON public."{table}"')
        op.execute(f'''
            CREATE POLICY tenant_isolation ON public."{table}"
            USING (
                agency_os_private.user_has_org_access(
                    org_id, nullif(current_setting('agency_os.user_id', true), '')
                )
                OR (
                    org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                    AND ({machine_workspace})
                )
                {identity_lookup}
            )
            WITH CHECK (
                agency_os_private.user_has_org_access(
                    org_id, nullif(current_setting('agency_os.user_id', true), '')
                )
                OR (
                    org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                    AND ({machine_workspace})
                )
                {identity_lookup}
            )
        ''')

    op.execute("DROP POLICY IF EXISTS execution_attempt_tenant_isolation ON public.execution_attempts")
    op.execute("""
        CREATE POLICY execution_attempt_tenant_isolation ON public.execution_attempts
        USING (EXISTS (
            SELECT 1 FROM public.executions AS e
            WHERE e.id = execution_id AND (
                agency_os_private.user_has_org_access(
                    e.org_id, nullif(current_setting('agency_os.user_id', true), '')
                )
                OR (
                    e.org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                    AND e.workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                )
            )
        ))
        WITH CHECK (EXISTS (
            SELECT 1 FROM public.executions AS e
            WHERE e.id = execution_id AND (
                agency_os_private.user_has_org_access(
                    e.org_id, nullif(current_setting('agency_os.user_id', true), '')
                )
                OR (
                    e.org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                    AND e.workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                )
            )
        ))
    """)
    op.execute("DROP POLICY IF EXISTS workspace_grants_read ON public.workspace_grants")
    op.execute("REVOKE ALL ON public.workspace_grants FROM agency_os_app")
    op.execute("DROP FUNCTION IF EXISTS agency_os_private.grant_workspace_access(text, text, text, text)")
    op.execute("DROP FUNCTION IF EXISTS agency_os_private.revoke_workspace_access(text, text, text, text)")
    op.execute("DROP FUNCTION IF EXISTS agency_os_private.user_has_workspace_access(text, text, text)")
    op.drop_index("ix_workspace_grants_user_active", table_name="workspace_grants")
    op.drop_index("uq_workspace_grants_active", table_name="workspace_grants")
    op.drop_table("workspace_grants")
    op.drop_constraint("fk_workspaces_created_by_users", "workspaces", type_="foreignkey")
    op.drop_column("workspaces", "created_by")
