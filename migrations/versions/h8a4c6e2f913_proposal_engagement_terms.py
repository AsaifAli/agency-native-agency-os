"""Add explicit one-time and retainer engagement terms to proposals.

Revision ID: h8a4c6e2f913
Revises: g6e2f4a8c195
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "h8a4c6e2f913"
down_revision: Union[str, Sequence[str], None] = "g6e2f4a8c195"
branch_labels = None
depends_on = None

CHECK_CONSTRAINTS = {
    "ck_proposal_engagement_type": (
        "engagement_type IN ('one_time','retainer')"
    ),
    "ck_proposal_billing_frequency": (
        "billing_frequency IN ('one_time','monthly','quarterly','annual')"
    ),
    "ck_proposal_engagement_terms": (
        "(engagement_type = 'one_time' AND billing_frequency = 'one_time' "
        "AND term_months IS NULL AND included_hours_per_period IS NULL "
        "AND rollover_hours = false AND auto_renew = false) OR "
        "(engagement_type = 'retainer' AND "
        "billing_frequency IN ('monthly','quarterly','annual') AND "
        "term_months BETWEEN 1 AND 60 AND "
        "included_hours_per_period IS NOT NULL AND "
        "included_hours_per_period >= 0)"
    ),
    "ck_proposal_support_response_hours": (
        "support_response_hours IS NULL OR "
        "support_response_hours BETWEEN 1 AND 720"
    ),
}

COLUMNS = (
    sa.Column(
        "engagement_type",
        sa.String(24),
        nullable=False,
        server_default="one_time",
    ),
    sa.Column(
        "billing_frequency",
        sa.String(24),
        nullable=False,
        server_default="one_time",
    ),
    sa.Column("term_months", sa.Integer(), nullable=True),
    sa.Column("included_hours_per_period", sa.Integer(), nullable=True),
    sa.Column(
        "rollover_hours",
        sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    ),
    sa.Column("support_response_hours", sa.Integer(), nullable=True),
    sa.Column(
        "auto_renew",
        sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    ),
)


def _existing_columns() -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("proposals")
    }


def _existing_checks() -> dict[str, str]:
    return {
        item["name"]: item.get("sqltext", "")
        for item in sa.inspect(op.get_bind()).get_check_constraints("proposals")
        if item.get("name")
    }


def _normalize_check(expression: str) -> str:
    return (
        expression.lower()
        .replace(" ", "")
        .replace("\n", "")
        .replace("\t", "")
        .replace("(", "")
        .replace(")", "")
        .replace("'", "")
        .replace('"', "")
    )


def upgrade() -> None:
    # SQLite DDL is non-transactional in this deployment path. Inspect before
    # each additive operation so a retry can recover from a partial attempt.
    existing_columns = _existing_columns()
    for column in COLUMNS:
        if column.name not in existing_columns:
            op.add_column("proposals", column)

    existing_checks = _existing_checks()
    missing_checks: dict[str, str] = {}
    for name, expression in CHECK_CONSTRAINTS.items():
        existing = existing_checks.get(name)
        if existing is None:
            missing_checks[name] = expression
        elif _normalize_check(existing) != _normalize_check(expression):
            raise RuntimeError(
                f"Existing constraint {name!r} does not match the expected definition"
            )

    if not missing_checks:
        return

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("proposals") as batch_op:
            for name, expression in missing_checks.items():
                batch_op.create_check_constraint(name, expression)
    else:
        for name, expression in missing_checks.items():
            op.create_check_constraint(name, "proposals", expression)


def downgrade() -> None:
    existing_columns = _existing_columns()
    existing_checks = _existing_checks()

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("proposals") as batch_op:
            for name in CHECK_CONSTRAINTS:
                if name in existing_checks:
                    batch_op.drop_constraint(name, type_="check")
            for column in reversed(COLUMNS):
                if column.name in existing_columns:
                    batch_op.drop_column(column.name)
        return

    for name in CHECK_CONSTRAINTS:
        if name in existing_checks:
            op.drop_constraint(name, "proposals", type_="check")
    for column in reversed(COLUMNS):
        if column.name in existing_columns:
            op.drop_column("proposals", column.name)
