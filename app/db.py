from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings



def _make_engine(database_url: str):
    sqlite = database_url.startswith("sqlite")
    args = (
        {"check_same_thread": False, "timeout": settings.db_connect_timeout_seconds}
        if sqlite else {
            "connect_timeout": settings.db_connect_timeout_seconds,
            "options": f"-c statement_timeout={settings.db_statement_timeout_ms} -c lock_timeout={settings.db_lock_timeout_ms}",
        }
    )
    return create_engine(database_url, pool_pre_ping=True,
        pool_timeout=settings.db_pool_timeout_seconds, connect_args=args)


engine = _make_engine(settings.database_url)
worker_engine = _make_engine(settings.database_url)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
WorkerSessionLocal = sessionmaker(bind=worker_engine, autoflush=False, autocommit=False)

# Trusted administrative commands use this URL only when explicitly supplied.
import os
_admin_url = os.environ.get("MIGRATION_DATABASE_URL")
admin_engine = _make_engine(_admin_url) if _admin_url else engine
AdminSessionLocal = sessionmaker(bind=admin_engine, autoflush=False, autocommit=False)

_RLS_KEYS = ("user_id", "machine_org_id", "machine_workspace_id", "machine_identity_lookup_id", "browser_session_token_hash")


def _apply_rls_context(session: Session, transaction, connection) -> None:
    workspace_capability = session.info.get("agency_os_worker_workspace_capability")
    if workspace_capability is not None:
        if connection.dialect.name != "postgresql":
            raise RuntimeError("Worker workspace capabilities require PostgreSQL")
        accepted = connection.execute(
            text("""
                SELECT agency_os_private.establish_worker_workspace_context(
                    :token, :org_id, :workspace_id, :worker_id
                )
            """),
            {
                "token": workspace_capability.token,
                "org_id": workspace_capability.org_id,
                "workspace_id": workspace_capability.workspace_id,
                "worker_id": workspace_capability.worker_id,
            },
        ).scalar_one()
        if accepted is not True:
            raise PermissionError("Worker maintenance capability is expired, revoked, or invalid")
        return

    capability = session.info.get("agency_os_worker_capability")
    if capability is not None:
        if connection.dialect.name != "postgresql":
            raise RuntimeError("Worker execution capabilities require PostgreSQL")
        accepted = connection.execute(
            text("""
                SELECT agency_os_private.establish_worker_execution_context(
                    :token, :execution_id, :attempt_id, :worker_id,
                    :lease_generation
                )
            """),
            {
                "token": capability.token,
                "execution_id": capability.execution_id,
                "attempt_id": capability.attempt_id,
                "worker_id": capability.worker_id,
                "lease_generation": capability.lease_generation,
            },
        ).scalar_one()
        if accepted is not True:
            raise PermissionError("Worker execution capability is expired, revoked, or invalid")
        return

    context = session.info.get("agency_os_rls_context")
    if not context or connection.dialect.name != "postgresql":
        return
    for key in _RLS_KEYS:
        connection.execute(text("SELECT set_config(:name, :value, true)"),
            {"name": f"agency_os.{key}", "value": context[key]})


event.listen(Session, "after_begin", _apply_rls_context)


def set_rls_context(db: Session, *, user_id: str | None = None,
    machine_org_id: str | None = None, machine_workspace_id: str | None = None,
    machine_identity_lookup_id: str | None = None,
    browser_session_token_hash: str | None = None) -> None:
    """Set transaction-local tenant identity and reapply it after commits."""
    context = {
        "user_id": user_id or "", "machine_org_id": machine_org_id or "",
        "machine_workspace_id": machine_workspace_id or "",
        "machine_identity_lookup_id": machine_identity_lookup_id or "",
        "browser_session_token_hash": browser_session_token_hash or "",
    }
    db.info["agency_os_rls_context"] = context
    if db.get_bind().dialect.name == "postgresql":
        for key, value in context.items():
            db.execute(text("SELECT set_config(:name, :value, true)"),
                {"name": f"agency_os.{key}", "value": value})


# Keep this inventory aligned with the tenant RLS migrations. A startup check
# that samples only a few tables can silently miss a newly added unprotected
# tenant table, so API and worker processes verify the complete set.
REQUIRED_RLS_TABLES = frozenset({
    "agent_sessions", "agents", "approvals", "audit_events",
    "call_sessions", "call_transcripts", "client_onboardings", "clients",
    "communication_blocks", "communication_consents", "contact_activities",
    "contacts", "contract_records", "delegations", "evaluation_runs",
    "executions", "founder_authorities", "invoice_records",
    "lead_research_drafts", "lead_research_records", "leads",
    "machine_identities", "memberships", "milestones",
    "onboarding_checklist_items", "opportunities", "orchestration_plan_drafts",
    "orchestration_plans", "outbound_message_events", "outbound_messages",
    "outbound_senders", "outbox_events", "outreach_drafts", "outcome_measurements", "payment_receipts",
    "project_costs", "project_outcomes", "projects", "proposals", "retainer_service_periods",
    "scope_change_requests", "service_offerings", "service_playbooks", "tasks",
    "time_entries", "tool_invocations", "workforce_capabilities",
    "workforce_members", "workforce_positions", "workforce_units", "workspaces",
    "workspace_grants",
    "organizations", "browser_sessions", "execution_attempts",
})


def verify_postgres_role(
    database_engine, *, expected_bypassrls: bool, require_rls: bool,
    expected_role: str,
) -> None:
    """Fail closed unless the exact connection role and complete tenant RLS inventory are safe."""
    if not isinstance(expected_role, str) or not expected_role.strip():
        raise ValueError("expected_role must be a non-empty PostgreSQL role name")
    if database_engine.dialect.name != "postgresql":
        raise RuntimeError("Production database role verification requires PostgreSQL")
    with database_engine.connect() as connection:
        role = connection.execute(text("""
            SELECT r.rolname AS role_name, r.rolsuper, r.rolbypassrls,
                EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='public' AND c.relrowsecurity AND c.relowner=r.oid) owns_rls_tables
            FROM pg_roles r WHERE r.rolname=current_user
        """)).mappings().one_or_none()
        if (
            role is None
            or role["role_name"] != expected_role
            or role["rolsuper"]
            or bool(role["rolbypassrls"]) != expected_bypassrls
            or role["owns_rls_tables"]
        ):
            expected = "non-owner BYPASSRLS role" if expected_bypassrls else "non-owner NOBYPASSRLS role"
            raise RuntimeError(
                f"PostgreSQL connection must use the exact {expected_role} "
                f"({expected}) role"
            )
        if require_rls:
            required = sorted(REQUIRED_RLS_TABLES)
            inventory = connection.execute(text("""
                SELECT
                    count(*) AS present_count,
                    count(*) FILTER (
                        WHERE c.relrowsecurity AND c.relforcerowsecurity
                    ) AS protected_count,
                    count(*) FILTER (
                        WHERE EXISTS (
                            SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid
                        )
                    ) AS policy_table_count
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind IN ('r', 'p')
                  AND c.relname = ANY(:required_tables)
            """), {"required_tables": required}).mappings().one()
            expected_count = len(REQUIRED_RLS_TABLES)
            if (
                inventory["present_count"] != expected_count
                or inventory["protected_count"] != expected_count
                or inventory["policy_table_count"] != expected_count
            ):
                raise RuntimeError(
                    "PostgreSQL tenant RLS migration is missing or incomplete "
                    f"(expected {expected_count} protected tables with policies; "
                    f"found {inventory['present_count']} tables, "
                    f"{inventory['protected_count']} FORCE-RLS tables, "
                    f"{inventory['policy_table_count']} tables with policies)"
                )


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def scoped_worker_capability_session_factory(capability, session_factory=WorkerSessionLocal):
    """Create transaction-scoped sessions authorized by one live execution lease."""
    required = (
        "token", "execution_id", "attempt_id", "worker_id", "lease_generation",
    )
    if any(not getattr(capability, name, None) for name in required):
        raise ValueError("A complete worker execution capability is required")

    def create_capability_session():
        db = session_factory()
        db.info["agency_os_worker_capability"] = capability
        return db

    return create_capability_session



def scoped_worker_workspace_session_factory(capability, session_factory=WorkerSessionLocal):
    """Create sessions authorized for one short-lived maintenance workspace lease."""
    required = ("token", "org_id", "workspace_id", "worker_id")
    if any(not getattr(capability, name, None) for name in required):
        raise ValueError("A complete worker workspace capability is required")

    def create_workspace_session():
        db = session_factory()
        db.info["agency_os_worker_workspace_capability"] = capability
        return db

    return create_workspace_session
