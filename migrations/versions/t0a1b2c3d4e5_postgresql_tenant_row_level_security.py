"""Enable PostgreSQL RLS for organization-scoped Agency OS records.

API connects as non-owner NOBYPASSRLS; worker connects with a separate
non-superuser BYPASSRLS role to claim jobs across tenants. Migrations run as
agency_os_migrator, a non-superuser BYPASSRLS table owner.
"""
from alembic import op

revision = "t0a1b2c3d4e5"
down_revision = "s9b5d7f1a204"
branch_labels = None
depends_on = None

ORG_TABLES = {
    "agent_sessions": True, "agents": True, "approvals": True,
    "audit_events": True, "call_sessions": True, "call_transcripts": True,
    "client_onboardings": True, "clients": True,
    "communication_blocks": True, "communication_consents": True,
    "contact_activities": True, "contacts": True, "contract_records": True,
    "delegations": True, "evaluation_runs": True, "executions": True,
    "founder_authorities": False, "invoice_records": True,
    "lead_research_drafts": True, "lead_research_records": True, "leads": True,
    "machine_identities": True, "memberships": False, "milestones": True,
    "onboarding_checklist_items": True, "opportunities": True,
    "orchestration_plan_drafts": True, "orchestration_plans": True,
    "outbound_message_events": True, "outbound_messages": True,
    "outbound_senders": True, "outbox_events": True, "outreach_drafts": True,
    "payment_receipts": True, "project_costs": True, "projects": True,
    "proposals": True, "retainer_service_periods": True,
    "scope_change_requests": True, "service_offerings": True,
    "service_playbooks": True, "tasks": True, "time_entries": True,
    "tool_invocations": True, "workforce_capabilities": True,
    "workforce_members": True, "workforce_positions": True,
    "workforce_units": True, "workspaces": False,
}


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS agency_os_private")
    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.user_has_org_access(
            target_org_id text, actor_user_id text
        ) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
            SELECT actor_user_id IS NOT NULL AND EXISTS (
                SELECT 1 FROM public.memberships AS m
                WHERE m.org_id = target_org_id AND m.user_id = actor_user_id
            )
        $function$
    """)
    op.execute("ALTER FUNCTION agency_os_private.user_has_org_access(text, text) OWNER TO agency_os_migrator")
    op.execute("REVOKE ALL ON SCHEMA agency_os_private FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA agency_os_private TO agency_os_app")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.user_has_org_access(text, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.user_has_org_access(text, text) TO agency_os_app")

    for table, has_workspace in ORG_TABLES.items():
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public."{table}" FORCE ROW LEVEL SECURITY')

        user_access = (
            "agency_os_private.user_has_org_access("
            "org_id, nullif(current_setting('agency_os.user_id', true), ''))"
        )
        if table == "memberships":
            # Machine principals never inherit human membership visibility.
            predicate = user_access
        elif has_workspace:
            machine_access = (
                "(org_id = nullif(current_setting('agency_os.machine_org_id', true), '') "
                "AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), ''))"
            )
            predicate = f"{user_access} OR {machine_access}"
        elif table == "workspaces":
            machine_access = (
                "(org_id = nullif(current_setting('agency_os.machine_org_id', true), '') "
                "AND id = nullif(current_setting('agency_os.machine_workspace_id', true), ''))"
            )
            predicate = f"{user_access} OR {machine_access}"
        else:
            # Founder authority is needed only by the fixed, signed website
            # intake integration; other machine access is scoped by workspace.
            predicate = (
                f"{user_access} OR org_id = "
                "nullif(current_setting('agency_os.machine_org_id', true), '')"
            )
        if table == "machine_identities":
            predicate += " OR id = nullif(current_setting('agency_os.machine_identity_lookup_id', true), '')"

        op.execute(
            f'CREATE POLICY tenant_isolation ON public."{table}" '
            f'USING ({predicate}) WITH CHECK ({predicate})'
        )

    # Browser sessions have no org_id; isolate them to the authenticated user
    # or the exact token digest being presented for login/refresh/logout.
    op.execute("ALTER TABLE public.browser_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.browser_sessions FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY browser_session_isolation ON public.browser_sessions
        USING (
            user_id = nullif(current_setting('agency_os.user_id', true), '')
            OR token_hash = nullif(current_setting('agency_os.browser_session_token_hash', true), '')
        )
        WITH CHECK (
            user_id = nullif(current_setting('agency_os.user_id', true), '')
        )
    """)

    op.execute("ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.organizations FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY tenant_isolation ON public.organizations
        USING (
            agency_os_private.user_has_org_access(
                id, nullif(current_setting('agency_os.user_id', true), '')
            ) OR id = nullif(current_setting('agency_os.machine_org_id', true), '')
        )
        WITH CHECK (
            agency_os_private.user_has_org_access(
                id, nullif(current_setting('agency_os.user_id', true), '')
            ) OR id = nullif(current_setting('agency_os.machine_org_id', true), '')
        )
    """)
    op.execute("GRANT USAGE ON SCHEMA public TO agency_os_app, agency_os_worker")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agency_os_app, agency_os_worker")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agency_os_app, agency_os_worker")
    op.execute("""
        ALTER DEFAULT PRIVILEGES FOR ROLE agency_os_migrator IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agency_os_app, agency_os_worker
    """)
    op.execute("""
        ALTER DEFAULT PRIVILEGES FOR ROLE agency_os_migrator IN SCHEMA public
        GRANT USAGE, SELECT ON SEQUENCES TO agency_os_app, agency_os_worker
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS browser_session_isolation ON public.browser_sessions")
    op.execute("ALTER TABLE public.browser_sessions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.browser_sessions DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.organizations")
    op.execute("ALTER TABLE public.organizations NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.organizations DISABLE ROW LEVEL SECURITY")
    for table in reversed(list(ORG_TABLES)):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON public."{table}"')
        op.execute(f'ALTER TABLE public."{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')
    op.execute("DROP FUNCTION IF EXISTS agency_os_private.user_has_org_access(text, text)")
    op.execute("DROP SCHEMA IF EXISTS agency_os_private")
