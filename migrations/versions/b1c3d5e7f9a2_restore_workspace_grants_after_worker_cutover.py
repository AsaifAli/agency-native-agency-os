"""Restore exact human workspace grants after the worker capability RLS cutover.

The worker capability cutover must not broaden human/API access back to the
organization boundary. This follow-up keeps verified worker lease access while
reinstating exact workspace grants, nullable org-level event handling, and
founder-gated workspace mutations.
"""
from alembic import op


revision = "b1c3d5e7f9a2"
down_revision = "a7c2e9f4b1d6"
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


def human_workspace_predicate(table: str) -> str:
    user_id = "nullif(current_setting('agency_os.user_id', true), '')"
    org_access = (
        "agency_os_private.user_has_org_access(org_id, "
        f"{user_id})"
    )
    workspace_access = (
        "agency_os_private.user_has_workspace_access(org_id, workspace_id, "
        f"{user_id})"
    )
    if table in ORG_LEVEL_NULLABLE_WORKSPACE_TABLES:
        return (
            f"((workspace_id IS NULL AND {org_access}) OR "
            f"(workspace_id IS NOT NULL AND {workspace_access}))"
        )
    return workspace_access


def machine_workspace_predicate(table: str) -> str:
    org_id = "nullif(current_setting('agency_os.machine_org_id', true), '')"
    workspace_id = "nullif(current_setting('agency_os.machine_workspace_id', true), '')"
    if table == "outbox_events":
        return (
            f"(session_user <> 'agency_os_worker' AND org_id = {org_id} "
            f"AND (workspace_id IS NULL OR workspace_id = {workspace_id}))"
        )
    if table == "machine_identities":
        identity_id = "nullif(current_setting('agency_os.machine_identity_lookup_id', true), '')"
        return (
            f"(session_user <> 'agency_os_worker' AND org_id = {org_id} "
            f"AND (workspace_id = {workspace_id} OR id = {identity_id}))"
        )
    return (
        f"(session_user <> 'agency_os_worker' AND org_id = {org_id} "
        f"AND workspace_id = {workspace_id})"
    )


def worker_workspace_predicate(table: str) -> str:
    if table == "machine_identities":
        # The worker has no direct table privilege; identity lookup remains an
        # API machine-identity operation and is never a worker capability.
        return "FALSE"
    non_null = "workspace_id IS NOT NULL AND " if table == "outbox_events" else ""
    return (
        f"(session_user = 'agency_os_worker' AND {non_null}"
        "agency_os_private.worker_has_execution_context("
        "org_id, workspace_id, NULL))"
    )


def workspace_select_predicate() -> str:
    user_id = "nullif(current_setting('agency_os.user_id', true), '')"
    machine_org_id = "nullif(current_setting('agency_os.machine_org_id', true), '')"
    machine_workspace_id = "nullif(current_setting('agency_os.machine_workspace_id', true), '')"
    return (
        "(agency_os_private.user_has_workspace_access(org_id, id, "
        f"{user_id}) "
        "OR (session_user <> 'agency_os_worker' "
        f"AND org_id = {machine_org_id} AND id = {machine_workspace_id}) "
        "OR (session_user = 'agency_os_worker' "
        "AND agency_os_private.worker_has_execution_context(org_id, id, NULL)))"
    )


def execution_attempt_predicate() -> str:
    user_id = "nullif(current_setting('agency_os.user_id', true), '')"
    machine_org_id = "nullif(current_setting('agency_os.machine_org_id', true), '')"
    machine_workspace_id = "nullif(current_setting('agency_os.machine_workspace_id', true), '')"
    return f"""EXISTS (
        SELECT 1 FROM public.executions AS e
        WHERE e.id = execution_attempts.execution_id
          AND (
            agency_os_private.user_has_workspace_access(e.org_id, e.workspace_id, {user_id})
            OR (session_user <> 'agency_os_worker'
                AND e.org_id = {machine_org_id}
                AND e.workspace_id = {machine_workspace_id})
            OR (session_user = 'agency_os_worker'
                AND agency_os_private.worker_has_execution_context(e.org_id, e.workspace_id, e.id))
          )
    )"""


def workspace_write_policies() -> dict[str, str]:
    user_id = "nullif(current_setting('agency_os.user_id', true), '')"
    org_access = (
        "agency_os_private.user_has_org_access(org_id, "
        f"{user_id})"
    )
    founder = (
        "EXISTS (SELECT 1 FROM public.founder_authorities AS f "
        "WHERE f.org_id = workspaces.org_id "
        f"AND f.user_id = {user_id} AND f.active IS TRUE)"
    )
    return {
        "workspace_insert": org_access,
        "workspace_update": founder,
        "workspace_delete": founder,
    }


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    # Reapply human grant scope without weakening the worker's independently
    # verified execution capability or the API's exact machine scope.
    for table in WORKSPACE_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON public."{table}"')
        predicate = " OR ".join((
            human_workspace_predicate(table),
            machine_workspace_predicate(table),
            worker_workspace_predicate(table),
        ))
        op.execute(
            f'CREATE POLICY tenant_isolation ON public."{table}" '
            f'USING ({predicate}) WITH CHECK ({predicate})'
        )

    op.execute(
        "DROP POLICY IF EXISTS execution_attempt_tenant_isolation "
        "ON public.execution_attempts"
    )
    attempts = execution_attempt_predicate()
    op.execute(
        "CREATE POLICY execution_attempt_tenant_isolation "
        f"ON public.execution_attempts USING ({attempts}) WITH CHECK ({attempts})"
    )

    for policy in (
        "tenant_isolation", "workspace_select", "workspace_insert",
        "workspace_update", "workspace_delete",
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON public.workspaces")

    op.execute(
        "CREATE POLICY workspace_select ON public.workspaces "
        f"FOR SELECT USING ({workspace_select_predicate()})"
    )
    write_policies = workspace_write_policies()
    op.execute(
        "CREATE POLICY workspace_insert ON public.workspaces "
        f"FOR INSERT WITH CHECK ({write_policies['workspace_insert']})"
    )
    op.execute(
        "CREATE POLICY workspace_update ON public.workspaces "
        f"FOR UPDATE USING ({write_policies['workspace_update']}) "
        f"WITH CHECK ({write_policies['workspace_update']})"
    )
    op.execute(
        "CREATE POLICY workspace_delete ON public.workspaces "
        f"FOR DELETE USING ({write_policies['workspace_delete']})"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Unsafe downgrade refused: it would restore organization-wide human "
        "workspace access after the worker capability cutover"
    )
