"""Snapshot service catalogue revision on proposal drafts.

Revision ID: h7f3a5b9d261
Revises: g6e2f4a8c195, d3a7c9e1b542
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "h7f3a5b9d261"
down_revision: Union[str, Sequence[str], None] = (
    "g6e2f4a8c195",
    "d3a7c9e1b542",
)
branch_labels = None
depends_on = None

SERVICE_OFFERING_COLUMN = "service_offering_id"
SNAPSHOT_COLUMN = "service_offering_snapshot"
FOREIGN_KEY = "fk_proposals_service_offering_id_service_offerings"
INDEX = "ix_proposals_service_offering_id"


def _schema_state() -> tuple[set[str], set[str], set[str]]:
    inspector = sa.inspect(op.get_bind())
    columns = {
        item["name"] for item in inspector.get_columns("proposals")
    }
    indexes = {
        item["name"] for item in inspector.get_indexes("proposals")
    }
    foreign_keys = {
        item["name"]
        for item in inspector.get_foreign_keys("proposals")
        if item.get("name")
    }
    return columns, indexes, foreign_keys


def upgrade() -> None:
    columns, indexes, foreign_keys = _schema_state()
    missing_service_column = SERVICE_OFFERING_COLUMN not in columns
    missing_snapshot_column = SNAPSHOT_COLUMN not in columns
    missing_fk = FOREIGN_KEY not in foreign_keys
    missing_index = INDEX not in indexes

    if op.get_bind().dialect.name == "sqlite":
        if missing_service_column or missing_snapshot_column or missing_fk:
            with op.batch_alter_table("proposals") as batch_op:
                if missing_service_column:
                    batch_op.add_column(
                        sa.Column(SERVICE_OFFERING_COLUMN, sa.String(36), nullable=True)
                    )
                if missing_snapshot_column:
                    batch_op.add_column(
                        sa.Column(SNAPSHOT_COLUMN, sa.JSON(), nullable=True)
                    )
                if missing_fk:
                    batch_op.create_foreign_key(
                        FOREIGN_KEY,
                        "service_offerings",
                        [SERVICE_OFFERING_COLUMN],
                        ["id"],
                        ondelete="RESTRICT",
                    )
        if missing_index:
            op.create_index(INDEX, "proposals", [SERVICE_OFFERING_COLUMN])
        return

    if missing_service_column:
        op.add_column(
            "proposals",
            sa.Column(SERVICE_OFFERING_COLUMN, sa.String(36), nullable=True),
        )
    if missing_snapshot_column:
        op.add_column(
            "proposals", sa.Column(SNAPSHOT_COLUMN, sa.JSON(), nullable=True)
        )
    if missing_fk:
        op.create_foreign_key(
            FOREIGN_KEY,
            "proposals",
            "service_offerings",
            [SERVICE_OFFERING_COLUMN],
            ["id"],
            ondelete="RESTRICT",
        )
    if missing_index:
        op.create_index(INDEX, "proposals", [SERVICE_OFFERING_COLUMN])


def downgrade() -> None:
    columns, indexes, foreign_keys = _schema_state()
    if INDEX in indexes:
        op.drop_index(INDEX, table_name="proposals")

    if op.get_bind().dialect.name == "sqlite":
        if (
            SERVICE_OFFERING_COLUMN in columns
            or SNAPSHOT_COLUMN in columns
            or FOREIGN_KEY in foreign_keys
        ):
            with op.batch_alter_table("proposals") as batch_op:
                if FOREIGN_KEY in foreign_keys:
                    batch_op.drop_constraint(FOREIGN_KEY, type_="foreignkey")
                if SNAPSHOT_COLUMN in columns:
                    batch_op.drop_column(SNAPSHOT_COLUMN)
                if SERVICE_OFFERING_COLUMN in columns:
                    batch_op.drop_column(SERVICE_OFFERING_COLUMN)
        return

    if FOREIGN_KEY in foreign_keys:
        op.drop_constraint(FOREIGN_KEY, "proposals", type_="foreignkey")
    if SNAPSHOT_COLUMN in columns:
        op.drop_column("proposals", SNAPSHOT_COLUMN)
    if SERVICE_OFFERING_COLUMN in columns:
        op.drop_column("proposals", SERVICE_OFFERING_COLUMN)
