"""Link retainer service periods to recurring invoice drafts.

Revision ID: k1d7f9a5c438
Revises: j0c6e8f4b327
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "k1d7f9a5c438"
down_revision: Union[str, Sequence[str], None] = "j0c6e8f4b327"
branch_labels = None
depends_on = None

COLUMN = "retainer_period_id"
INDEX = "ix_invoice_records_retainer_period_id"
UNIQUE = "uq_invoice_retainer_period"
FOREIGN_KEY = "fk_invoice_records_retainer_period_id_retainer_service_periods"


def _schema_state() -> tuple[set[str], set[str], set[str], set[str]]:
    inspector = sa.inspect(op.get_bind())
    columns = {
        item["name"] for item in inspector.get_columns("invoice_records")
    }
    indexes = {
        item["name"] for item in inspector.get_indexes("invoice_records")
    }
    unique_constraints = {
        item["name"]
        for item in inspector.get_unique_constraints("invoice_records")
        if item.get("name")
    }
    foreign_keys = {
        item["name"]
        for item in inspector.get_foreign_keys("invoice_records")
        if item.get("name")
    }
    return columns, indexes, unique_constraints, foreign_keys


def upgrade() -> None:
    columns, indexes, unique_constraints, foreign_keys = _schema_state()
    missing_column = COLUMN not in columns
    missing_index = INDEX not in indexes
    missing_unique = UNIQUE not in unique_constraints
    missing_fk = FOREIGN_KEY not in foreign_keys

    if not (missing_column or missing_index or missing_unique or missing_fk):
        return

    if op.get_bind().dialect.name == "sqlite":
        # A named FK is mandatory for Alembic batch mode. Keep each operation
        # conditional so a retry can repair a partially applied migration.
        with op.batch_alter_table("invoice_records") as batch_op:
            if missing_column:
                batch_op.add_column(sa.Column(COLUMN, sa.String(36), nullable=True))
            if missing_fk:
                batch_op.create_foreign_key(
                    FOREIGN_KEY,
                    "retainer_service_periods",
                    [COLUMN],
                    ["id"],
                    ondelete="RESTRICT",
                )
            if missing_unique:
                batch_op.create_unique_constraint(
                    UNIQUE, ["org_id", "workspace_id", COLUMN]
                )
            if missing_index:
                batch_op.create_index(INDEX, [COLUMN])
        return

    if missing_column:
        op.add_column(
            "invoice_records", sa.Column(COLUMN, sa.String(36), nullable=True)
        )
    if missing_fk:
        op.create_foreign_key(
            FOREIGN_KEY,
            "invoice_records",
            "retainer_service_periods",
            [COLUMN],
            ["id"],
            ondelete="RESTRICT",
        )
    if missing_unique:
        op.create_unique_constraint(
            UNIQUE, "invoice_records", ["org_id", "workspace_id", COLUMN]
        )
    if missing_index:
        op.create_index(INDEX, "invoice_records", [COLUMN])


def downgrade() -> None:
    columns, indexes, unique_constraints, foreign_keys = _schema_state()
    if op.get_bind().dialect.name == "sqlite":
        if not (COLUMN in columns or INDEX in indexes or UNIQUE in unique_constraints or FOREIGN_KEY in foreign_keys):
            return
        with op.batch_alter_table("invoice_records") as batch_op:
            if FOREIGN_KEY in foreign_keys:
                batch_op.drop_constraint(FOREIGN_KEY, type_="foreignkey")
            if UNIQUE in unique_constraints:
                batch_op.drop_constraint(UNIQUE, type_="unique")
            if INDEX in indexes:
                batch_op.drop_index(INDEX)
            if COLUMN in columns:
                batch_op.drop_column(COLUMN)
        return

    if FOREIGN_KEY in foreign_keys:
        op.drop_constraint(FOREIGN_KEY, "invoice_records", type_="foreignkey")
    if UNIQUE in unique_constraints:
        op.drop_constraint(UNIQUE, "invoice_records", type_="unique")
    if INDEX in indexes:
        op.drop_index(INDEX, table_name="invoice_records")
    if COLUMN in columns:
        op.drop_column("invoice_records", COLUMN)
