"""Narrow the worker login to the tables and operations used by its runtime.

The API role is intentionally unchanged. Worker row visibility continues to be
controlled by the existing execution/workspace capability RLS policies.
"""
from alembic import op

revision = "d5e7f9a1c3b5"
down_revision = "c4d6e8f0a2b5"
branch_labels = None
depends_on = None


SELECT_TABLES = (
    "agent_sessions",
    "agents",
    "delegations",
    "execution_attempts",
    "executions",
    "lead_research_drafts",
    "machine_identities",
    "orchestration_plan_drafts",
    "outbox_events",
    "tasks",
    "tool_invocations",
    "workforce_capabilities",
    "workforce_members",
    "workspaces",
)

INSERT_TABLES = (
    "agent_sessions",
    "audit_events",
    "executions",
    "lead_research_drafts",
    "tool_invocations",
)

UPDATE_TABLES = (
    "agent_sessions",
    "delegations",
    "execution_attempts",
    "executions",
    "orchestration_plan_drafts",
    "outbox_events",
    "tasks",
    "tool_invocations",
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    # Remove the original all-table DML grant without changing agency_os_app.
    # Future table/sequence defaults were already revoked for the worker by
    # u1b2c3d4e5f6; this closes the remaining grants on existing public objects.
    op.execute(
        "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public "
        "FROM agency_os_worker"
    )
    op.execute(
        "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public "
        "FROM agency_os_worker"
    )

    op.execute(
        "GRANT SELECT ON TABLE "
        + ", ".join(f'public."{table}"' for table in SELECT_TABLES)
        + " TO agency_os_worker"
    )
    op.execute(
        "GRANT INSERT ON TABLE "
        + ", ".join(f'public."{table}"' for table in INSERT_TABLES)
        + " TO agency_os_worker"
    )
    op.execute(
        "GRANT UPDATE ON TABLE "
        + ", ".join(f'public."{table}"' for table in UPDATE_TABLES)
        + " TO agency_os_worker"
    )

    # These tables are locked with SELECT FOR UPDATE by the tool gateway. A
    # narrow, non-authoritative timestamp column privilege satisfies PostgreSQL's
    # UPDATE privilege requirement without allowing capability/member mutation.
    op.execute(
        "GRANT UPDATE (created_at) ON TABLE public.workforce_capabilities "
        "TO agency_os_worker"
    )
    op.execute(
        "GRANT UPDATE (updated_at) ON TABLE public.workforce_members "
        "TO agency_os_worker"
    )

    # Machine identities are readable only within the execution capability;
    # the worker may update only the last-used timestamp. PostgreSQL requires
    # UPDATE privilege on at least one column for SELECT FOR UPDATE.
    op.execute(
        "GRANT UPDATE (last_used_at) ON TABLE public.machine_identities "
        "TO agency_os_worker"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Unsafe downgrade refused: restoring broad worker table privileges "
        "would undo the least-privilege security boundary"
    )
