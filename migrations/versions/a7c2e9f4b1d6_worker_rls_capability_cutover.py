"""Require a database-verified execution capability for worker tenant reads.

Caller-controlled machine tenant GUCs remain available to the API role, but are
never an authorization source for agency_os_worker. Worker access is fail-closed
until a transaction has established a live execution capability.
"""
from alembic import op

revision = "a7c2e9f4b1d6"
down_revision = "z6f1b3d8a2c5"
branch_labels = None
depends_on = None

ORG_WORKSPACE_TABLES = (
    "agent_sessions", "agents", "approvals", "audit_events", "call_sessions",
    "call_transcripts", "client_onboardings", "clients", "communication_blocks",
    "communication_consents", "contact_activities", "contacts", "contract_records",
    "delegations", "evaluation_runs", "executions", "invoice_records",
    "lead_research_drafts", "lead_research_records", "leads", "milestones",
    "onboarding_checklist_items", "opportunities", "orchestration_plan_drafts",
    "orchestration_plans", "outbound_message_events", "outbound_messages",
    "outbound_senders", "outbox_events", "outreach_drafts", "payment_receipts",
    "project_costs", "projects", "proposals", "retainer_service_periods",
    "scope_change_requests", "service_offerings", "service_playbooks", "tasks",
    "time_entries", "tool_invocations", "workforce_capabilities", "workforce_members",
    "workforce_positions", "workforce_units",
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        CREATE OR REPLACE FUNCTION agency_os_private.worker_has_execution_context(
            target_org_id text, target_workspace_id text, target_execution_id text DEFAULT NULL
        ) RETURNS boolean
        LANGUAGE sql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public, agency_os_private
        AS $function$
            SELECT session_user = 'agency_os_worker' AND EXISTS (
                SELECT 1
                FROM agency_os_private.worker_transaction_context AS ctx
                JOIN agency_os_private.worker_lease_capabilities AS cap
                  ON cap.id = ctx.capability_id
                JOIN public.executions AS e ON e.id = ctx.execution_id
                JOIN public.execution_attempts AS a
                  ON a.id = ctx.attempt_id AND a.execution_id = e.id
                WHERE ctx.backend_pid = pg_backend_pid()
                  AND ctx.transaction_id = txid_current()
                  AND e.org_id = target_org_id
                  AND e.workspace_id = target_workspace_id
                  AND (target_execution_id IS NULL OR e.id = target_execution_id)
                  AND cap.invalidated_at IS NULL
                  AND cap.expires_at > clock_timestamp()
                  AND cap.execution_id = e.id
                  AND cap.attempt_id = a.id
                  AND cap.worker_id = ctx.worker_id
                  AND cap.lease_generation = ctx.lease_generation
                  AND a.worker_id = ctx.worker_id
                  AND a.lease_generation = ctx.lease_generation
                  AND a.lease_expires_at > clock_timestamp()
                  AND a.status::text IN ('claimed', 'running')
                  AND e.status::text IN ('claimed', 'running')
            )
        $function$
    """)
    op.execute("ALTER FUNCTION agency_os_private.worker_has_execution_context(text, text, text) OWNER TO agency_os_migrator")
    op.execute("REVOKE ALL ON FUNCTION agency_os_private.worker_has_execution_context(text, text, text) FROM PUBLIC, agency_os_app")
    op.execute("GRANT EXECUTE ON FUNCTION agency_os_private.worker_has_execution_context(text, text, text) TO agency_os_worker")

    # Keep human/API access unchanged. A worker's machine GUC values are ignored;
    # only the private PID+transaction-bound capability context grants a row.
    for table in ORG_WORKSPACE_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON public."{table}"')
        human = "agency_os_private.user_has_org_access(org_id, nullif(current_setting('agency_os.user_id', true), ''))"
        worker = "(session_user = 'agency_os_worker' AND agency_os_private.worker_has_execution_context(org_id, workspace_id, NULL))"
        if table == "outbox_events":
            worker = "(session_user = 'agency_os_worker' AND workspace_id IS NOT NULL AND agency_os_private.worker_has_execution_context(org_id, workspace_id, NULL))"
        predicate = f"({human} OR {worker})"
        op.execute(f'CREATE POLICY tenant_isolation ON public."{table}" USING ({predicate}) WITH CHECK ({predicate})')

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.execution_attempts")
    attempts = """EXISTS (
        SELECT 1 FROM public.executions AS e
        WHERE e.id = execution_attempts.execution_id
          AND (
            agency_os_private.user_has_org_access(e.org_id, nullif(current_setting('agency_os.user_id', true), ''))
            OR (session_user = 'agency_os_worker' AND agency_os_private.worker_has_execution_context(e.org_id, e.workspace_id, e.id))
          )
    )"""
    op.execute(f"CREATE POLICY execution_attempt_tenant_isolation ON public.execution_attempts USING ({attempts}) WITH CHECK ({attempts})")

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.workspaces")
    workspace_predicate = "(agency_os_private.user_has_org_access(org_id, nullif(current_setting('agency_os.user_id', true), '')) OR (session_user = 'agency_os_worker' AND agency_os_private.worker_has_execution_context(org_id, id, NULL)))"
    op.execute(f"CREATE POLICY tenant_isolation ON public.workspaces USING ({workspace_predicate}) WITH CHECK ({workspace_predicate})")

    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.organizations")
    org_predicate = "(agency_os_private.user_has_org_access(id, nullif(current_setting('agency_os.user_id', true), '')) OR (session_user = 'agency_os_worker' AND EXISTS (SELECT 1 FROM public.executions e WHERE e.org_id = organizations.id AND agency_os_private.worker_has_execution_context(e.org_id, e.workspace_id, e.id))))"
    op.execute(f"CREATE POLICY tenant_isolation ON public.organizations USING ({org_predicate}) WITH CHECK ({org_predicate})")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # Deliberately do not restore the vulnerable GUC-based worker policies.
    # Downgrade must be performed by restoring a reviewed database backup.
    raise RuntimeError("Unsafe downgrade refused: restoring GUC-authorized worker RLS would reintroduce cross-tenant access")
