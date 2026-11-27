"""Add idempotency key for website-originated CRM leads.

Revision ID: 2e8a6c4d9f31
Revises: c7a4b1e9d2f6

Supports SQLite batch DDL and retries after partially applied DDL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2e8a6c4d9f31"
down_revision: Union[str, Sequence[str], None] = "c7a4b1e9d2f6"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "uq_lead_external_source_key"
CONSTRAINT_COLUMNS = ["org_id", "workspace_id", "source", "external_key"]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("leads"):
        raise RuntimeError("Required table leads does not exist")

    columns = {
        column["name"]: column
        for column in inspector.get_columns("leads")
    }

    if "external_key" not in columns:
        op.add_column(
            "leads",
            sa.Column("external_key", sa.String(160), nullable=True),
        )

    inspector = sa.inspect(bind)
    existing_constraints = {
        item["name"]: item
        for item in inspector.get_unique_constraints("leads")
        if item.get("name")
    }

    if CONSTRAINT_NAME in existing_constraints:
        actual_columns = existing_constraints[CONSTRAINT_NAME].get(
            "column_names"
        )
        if actual_columns != CONSTRAINT_COLUMNS:
            raise RuntimeError(
                f"Unexpected definition for {CONSTRAINT_NAME}: "
                f"{actual_columns}"
            )
        return

    if bind.dialect.name == "sqlite":
        # SQLite cannot ALTER TABLE to add a UNIQUE constraint. Batch mode
        # rebuilds the table and also recovers when external_key was added
        # before a previous migration attempt failed.
        with op.batch_alter_table("leads") as batch_op:
            batch_op.create_unique_constraint(
                CONSTRAINT_NAME,
                CONSTRAINT_COLUMNS,
            )
    else:
        op.create_unique_constraint(
            CONSTRAINT_NAME,
            "leads",
            CONSTRAINT_COLUMNS,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("leads"):
        return

    constraints = {
        item["name"]: item
        for item in inspector.get_unique_constraints("leads")
        if item.get("name")
    }

    if CONSTRAINT_NAME in constraints:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("leads") as batch_op:
                batch_op.drop_constraint(CONSTRAINT_NAME, type_="unique")
        else:
            op.drop_constraint(
                CONSTRAINT_NAME,
                "leads",
                type_="unique",
            )

    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("leads")
    }
    if "external_key" in columns:
        op.drop_column("leads", "external_key")
