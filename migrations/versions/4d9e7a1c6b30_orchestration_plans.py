"""Merge existing heads and add Chief of Staff orchestration records.

Revision ID: 4d9e7a1c6b30
Revises: d8c5a1f20973, c7a4b1e9d2f6, 2e8a6c4d9f31

Supports SQLite batch DDL and recovery from partially applied DDL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4d9e7a1c6b30"
down_revision: Union[str, Sequence[str], None] = (
    "d8c5a1f20973",
    "c7a4b1e9d2f6",
    "2e8a6c4d9f31",
)
branch_labels = None
depends_on = None

DELEGATION_CHECK = "ck_delegation_status"
DELEGATION_CHECK_SQL = (
    "status IN ('blocked','ready','queued','running','awaiting_review',"
    "'succeeded','failed','cancelled')"
)


def _ensure_index(
    bind: sa.Connection,
    table_name: str,
    index_name: str,
    columns: list[str],
) -> None:
    indexes = {
        item["name"]: item
        for item in sa.inspect(bind).get_indexes(table_name)
    }
    if index_name in indexes:
        if indexes[index_name].get("column_names") != columns:
            raise RuntimeError(f"Unexpected definition for {index_name}")
        return
    op.create_index(index_name, table_name, columns)


def _ensure_orchestration_plans(bind: sa.Connection) -> None:
    if not sa.inspect(bind).has_table("orchestration_plans"):
        op.create_table(
            "orchestration_plans",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
            sa.Column("root_task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_by_member_id", sa.String(36), sa.ForeignKey("workforce_members.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("objective", sa.Text(), nullable=False),
            sa.Column("plan_title", sa.String(200), nullable=False),
            sa.Column("status", sa.String(24), nullable=False, server_default="planned"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('planned','in_progress','awaiting_review','succeeded','failed','cancelled')",
                name="ck_orchestration_plan_status",
            ),
        )
    else:
        expected = {
            "id", "org_id", "workspace_id", "root_task_id",
            "created_by_member_id", "objective", "plan_title", "status",
            "created_at", "updated_at",
        }
        actual = {
            item["name"]
            for item in sa.inspect(bind).get_columns("orchestration_plans")
        }
        if not expected <= actual:
            raise RuntimeError(
                "Existing orchestration_plans table is incomplete: "
                f"missing {sorted(expected - actual)}"
            )

    _ensure_index(
        bind, "orchestration_plans", "ix_orchestration_plan_scope_status",
        ["org_id", "workspace_id", "status"],
    )
    _ensure_index(
        bind, "orchestration_plans", "ix_orchestration_plan_root_task",
        ["root_task_id"],
    )


def _ensure_delegation_columns(bind: sa.Connection) -> None:
    if not sa.inspect(bind).has_table("delegations"):
        raise RuntimeError("Required table delegations does not exist")

    expected_columns = {
        "status": sa.Column(
            "status", sa.String(24), nullable=False, server_default="ready"
        ),
        "sequence_no": sa.Column(
            "sequence_no", sa.Integer(), nullable=False, server_default="1"
        ),
        "last_error_code": sa.Column(
            "last_error_code", sa.String(80), nullable=True
        ),
        "updated_at": sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
    }
    existing = {
        item["name"]
        for item in sa.inspect(bind).get_columns("delegations")
    }
    for name, column in expected_columns.items():
        if name not in existing:
            op.add_column("delegations", column)


def _ensure_delegation_check(bind: sa.Connection) -> None:
    checks = {
        item["name"]: item
        for item in sa.inspect(bind).get_check_constraints("delegations")
        if item.get("name")
    }
    if DELEGATION_CHECK in checks:
        actual = (checks[DELEGATION_CHECK].get("sqltext") or "").lower()
        normalized = actual.replace(" ", "").replace("'", "")
        required = DELEGATION_CHECK_SQL.lower().replace(" ", "").replace("'", "")
        if normalized != required:
            raise RuntimeError(f"Unexpected definition for {DELEGATION_CHECK}")
        return

    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("delegations") as batch_op:
            batch_op.create_check_constraint(
                DELEGATION_CHECK, DELEGATION_CHECK_SQL
            )
    else:
        op.create_check_constraint(
            DELEGATION_CHECK, "delegations", DELEGATION_CHECK_SQL
        )


def _ensure_plan_delegations(bind: sa.Connection) -> None:
    if sa.inspect(bind).has_table("orchestration_plan_delegations"):
        expected = {"plan_id", "delegation_id", "ordinal"}
        actual = {
            item["name"]
            for item in sa.inspect(bind).get_columns(
                "orchestration_plan_delegations"
            )
        }
        if not expected <= actual:
            raise RuntimeError(
                "Existing orchestration_plan_delegations table is incomplete"
            )
        return

    op.create_table(
        "orchestration_plan_delegations",
        sa.Column(
            "plan_id", sa.String(36),
            sa.ForeignKey("orchestration_plans.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "delegation_id", sa.String(36),
            sa.ForeignKey("delegations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "plan_id", "ordinal", name="uq_plan_delegation_ordinal"
        ),
    )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_orchestration_plans(bind)
    _ensure_delegation_columns(bind)
    _ensure_delegation_check(bind)
    _ensure_index(
        bind, "delegations", "ix_delegation_scope_status",
        ["org_id", "workspace_id", "status"],
    )
    _ensure_plan_delegations(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("orchestration_plan_delegations"):
        op.drop_table("orchestration_plan_delegations")

    if inspector.has_table("delegations"):
        indexes = {
            item["name"] for item in sa.inspect(bind).get_indexes("delegations")
        }
        if "ix_delegation_scope_status" in indexes:
            op.drop_index(
                "ix_delegation_scope_status", table_name="delegations"
            )

        columns = {
            item["name"]
            for item in sa.inspect(bind).get_columns("delegations")
        }
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("delegations") as batch_op:
                checks = {
                    item["name"]
                    for item in sa.inspect(bind).get_check_constraints(
                        "delegations"
                    )
                }
                if DELEGATION_CHECK in checks:
                    batch_op.drop_constraint(
                        DELEGATION_CHECK, type_="check"
                    )
                for name in (
                    "updated_at", "last_error_code", "sequence_no", "status"
                ):
                    if name in columns:
                        batch_op.drop_column(name)
        else:
            checks = {
                item["name"]
                for item in sa.inspect(bind).get_check_constraints(
                    "delegations"
                )
            }
            if DELEGATION_CHECK in checks:
                op.drop_constraint(
                    DELEGATION_CHECK, "delegations", type_="check"
                )
            for name in (
                "updated_at", "last_error_code", "sequence_no", "status"
            ):
                if name in columns:
                    op.drop_column("delegations", name)

    inspector = sa.inspect(bind)
    if inspector.has_table("orchestration_plans"):
        indexes = {
            item["name"]
            for item in sa.inspect(bind).get_indexes("orchestration_plans")
        }
        for name in (
            "ix_orchestration_plan_root_task",
            "ix_orchestration_plan_scope_status",
        ):
            if name in indexes:
                op.drop_index(name, table_name="orchestration_plans")
        op.drop_table("orchestration_plans")
