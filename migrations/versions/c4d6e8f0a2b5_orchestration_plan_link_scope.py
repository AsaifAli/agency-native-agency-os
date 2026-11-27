"""Enforce tenant scope on orchestration plan-to-delegation links.

Revision ID: c4d6e8f0a2b5
Revises: ab2c3d4e5f6a
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d6e8f0a2b5"
down_revision: Union[str, Sequence[str], None] = "ab2c3d4e5f6a"
branch_labels = None
depends_on = None


def _ensure_index(
    bind: sa.Connection,
    table: str,
    name: str,
    columns: list[str],
    *,
    unique: bool,
) -> None:
    indexes = {item["name"]: item for item in sa.inspect(bind).get_indexes(table)}
    if name in indexes:
        existing = indexes[name]
        if (
            existing.get("column_names") != columns
            or bool(existing.get("unique")) != unique
        ):
            raise RuntimeError(f"Unexpected definition for {name}")
        return
    op.create_index(name, table, columns, unique=unique)


def _ensure_column(bind: sa.Connection, name: str) -> None:
    columns = {
        item["name"]
        for item in sa.inspect(bind).get_columns("orchestration_plan_delegations")
    }
    if name not in columns:
        op.add_column(
            "orchestration_plan_delegations",
            sa.Column(name, sa.String(length=36), nullable=True),
        )


def _validate_existing_links(bind: sa.Connection) -> None:
    invalid = bind.execute(sa.text("""
        SELECT count(*)
        FROM orchestration_plan_delegations AS link
        LEFT JOIN orchestration_plans AS plan ON plan.id = link.plan_id
        LEFT JOIN delegations AS delegation ON delegation.id = link.delegation_id
        WHERE plan.id IS NULL
           OR delegation.id IS NULL
           OR link.org_id IS NULL
           OR link.workspace_id IS NULL
           OR link.org_id <> plan.org_id
           OR link.workspace_id <> plan.workspace_id
           OR link.org_id <> delegation.org_id
           OR link.workspace_id <> delegation.workspace_id
    """)).scalar_one()
    if invalid:
        raise RuntimeError(
            "Cannot scope orchestration plan links: existing orphaned or "
            "cross-workspace links found"
        )


def _install_postgres_rls() -> None:
    op.execute(
        "ALTER TABLE public.orchestration_plan_delegations "
        "ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE public.orchestration_plan_delegations "
        "FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        "DROP POLICY IF EXISTS tenant_isolation "
        "ON public.orchestration_plan_delegations"
    )
    predicate = """
        (
            agency_os_private.user_has_workspace_access(
                org_id, workspace_id,
                nullif(current_setting('agency_os.user_id', true), '')
            )
            OR
            (
                session_user <> 'agency_os_worker'
                AND org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
            )
            OR
            (
                session_user = 'agency_os_worker'
                AND agency_os_private.worker_has_execution_context(
                    org_id, workspace_id, NULL
                )
            )
        )
    """
    op.execute(
        "CREATE POLICY tenant_isolation "
        "ON public.orchestration_plan_delegations "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("orchestration_plan_delegations"):
        raise RuntimeError(
            "Required table orchestration_plan_delegations does not exist"
        )

    _ensure_column(bind, "org_id")
    _ensure_column(bind, "workspace_id")

    op.execute(sa.text("""
        UPDATE orchestration_plan_delegations
        SET org_id = (
            SELECT org_id FROM orchestration_plans
            WHERE orchestration_plans.id = orchestration_plan_delegations.plan_id
        ),
        workspace_id = (
            SELECT workspace_id FROM orchestration_plans
            WHERE orchestration_plans.id = orchestration_plan_delegations.plan_id
        )
        WHERE org_id IS NULL OR workspace_id IS NULL
    """))
    _validate_existing_links(bind)

    _ensure_index(
        bind,
        "orchestration_plans",
        "uq_orchestration_plan_scope_id",
        ["org_id", "workspace_id", "id"],
        unique=True,
    )
    _ensure_index(
        bind,
        "delegations",
        "uq_delegation_scope_id",
        ["org_id", "workspace_id", "id"],
        unique=True,
    )

    columns = {
        item["name"]: item
        for item in sa.inspect(bind).get_columns("orchestration_plan_delegations")
    }
    existing_fks = {
        item.get("name")
        for item in sa.inspect(bind).get_foreign_keys("orchestration_plan_delegations")
    }
    missing_fks = {
        "fk_plan_delegation_plan_workspace",
        "fk_plan_delegation_delegation_workspace",
    } - existing_fks

    if bind.dialect.name == "sqlite":
        needs_batch = bool(missing_fks) or any(
            columns[name].get("nullable", True)
            for name in ("org_id", "workspace_id")
        )
        if needs_batch:
            with op.batch_alter_table("orchestration_plan_delegations") as batch:
                for name in ("org_id", "workspace_id"):
                    if columns[name].get("nullable", True):
                        batch.alter_column(
                            name,
                            existing_type=sa.String(length=36),
                            nullable=False,
                        )
                if "fk_plan_delegation_plan_workspace" in missing_fks:
                    batch.create_foreign_key(
                        "fk_plan_delegation_plan_workspace",
                        "orchestration_plans",
                        ["org_id", "workspace_id", "plan_id"],
                        ["org_id", "workspace_id", "id"],
                        ondelete="CASCADE",
                    )
                if "fk_plan_delegation_delegation_workspace" in missing_fks:
                    batch.create_foreign_key(
                        "fk_plan_delegation_delegation_workspace",
                        "delegations",
                        ["org_id", "workspace_id", "delegation_id"],
                        ["org_id", "workspace_id", "id"],
                        ondelete="CASCADE",
                    )
    else:
        for name in ("org_id", "workspace_id"):
            if columns[name].get("nullable", True):
                op.alter_column(
                    "orchestration_plan_delegations",
                    name,
                    existing_type=sa.String(length=36),
                    nullable=False,
                )
        if "fk_plan_delegation_plan_workspace" in missing_fks:
            op.create_foreign_key(
                "fk_plan_delegation_plan_workspace",
                "orchestration_plan_delegations",
                "orchestration_plans",
                ["org_id", "workspace_id", "plan_id"],
                ["org_id", "workspace_id", "id"],
                ondelete="CASCADE",
            )
        if "fk_plan_delegation_delegation_workspace" in missing_fks:
            op.create_foreign_key(
                "fk_plan_delegation_delegation_workspace",
                "orchestration_plan_delegations",
                "delegations",
                ["org_id", "workspace_id", "delegation_id"],
                ["org_id", "workspace_id", "id"],
                ondelete="CASCADE",
            )

    _ensure_index(
        bind,
        "orchestration_plan_delegations",
        "ix_orchestration_plan_delegations_scope_plan",
        ["org_id", "workspace_id", "plan_id"],
        unique=False,
    )

    if bind.dialect.name == "postgresql":
        _install_postgres_rls()


def downgrade() -> None:
    raise RuntimeError(
        "Unsafe downgrade refused: removing workspace constraints and RLS "
        "would weaken orchestration tenant isolation"
    )
