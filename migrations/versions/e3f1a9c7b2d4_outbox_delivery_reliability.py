"""Add durable outbox delivery leases and retry metadata.

Revision ID: e3f1a9c7b2d4
Revises: d8c5a1f20973

Supports fresh databases and partially provisioned databases.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3f1a9c7b2d4"
down_revision: Union[str, Sequence[str], None] = "d8c5a1f20973"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("outbox_events"):
        raise RuntimeError("Required table outbox_events does not exist")

    expected_columns = {
        "max_attempts": sa.Column(
            "max_attempts", sa.Integer(),
            nullable=False, server_default="8"
        ),
        "claimed_by": sa.Column(
            "claimed_by", sa.String(160), nullable=True
        ),
        "lease_expires_at": sa.Column(
            "lease_expires_at", sa.DateTime(timezone=True),
            nullable=True
        ),
        "published_at": sa.Column(
            "published_at", sa.DateTime(timezone=True),
            nullable=True
        ),
        "last_error": sa.Column(
            "last_error", sa.Text(), nullable=True
        ),
    }

    existing_columns = {
        column["name"]: column
        for column in inspector.get_columns("outbox_events")
    }

    for name, expected in expected_columns.items():
        if name not in existing_columns:
            op.add_column("outbox_events", expected)
            continue

        actual = existing_columns[name]
        actual_type = actual["type"]
        expected_type = expected.type

        if not isinstance(actual_type, type(expected_type)):
            raise RuntimeError(
                f"Unexpected type for outbox_events.{name}: "
                f"{actual_type}; expected {expected_type}"
            )

        if actual["nullable"] != expected.nullable:
            raise RuntimeError(
                f"Unexpected nullability for outbox_events.{name}"
            )

        if isinstance(expected_type, sa.String):
            if actual_type.length != expected_type.length:
                raise RuntimeError(
                    f"Unexpected length for outbox_events.{name}"
                )

        # SQLite has no native timezone-aware DATETIME type. Its SQLAlchemy
        # inspector therefore reports timezone=False even when the schema
        # was declared with DateTime(timezone=True). Keep this check on
        # dialects that can represent the distinction (e.g. PostgreSQL).
        if (
            isinstance(expected_type, sa.DateTime)
            and bind.dialect.name != "sqlite"
            and actual_type.timezone != expected_type.timezone
        ):
            raise RuntimeError(
                f"Unexpected timezone for outbox_events.{name}"
            )

    inspector = sa.inspect(bind)

    checks = {
        item["name"]: item
        for item in inspector.get_check_constraints("outbox_events")
    }

    check_name = "ck_outbox_attempts"
    expected_fragments = ("attempts >= 0", "max_attempts >= 1")

    if check_name in checks:
        definition = (checks[check_name].get("sqltext") or "").lower()
        compact = (
            definition.replace(" ", "")
            .replace("(", "")
            .replace(")", "")
        )

        if not all(
            fragment.replace(" ", "") in compact
            for fragment in expected_fragments
        ):
            raise RuntimeError(
                f"Unexpected definition for {check_name}"
            )
    else:
        # SQLite does not support ALTER TABLE ADD CONSTRAINT. Alembic batch
        # mode rebuilds the table while preserving its existing schema/data.
        with op.batch_alter_table("outbox_events") as batch_op:
            batch_op.create_check_constraint(
                check_name,
                "attempts >= 0 AND max_attempts >= 1",
            )

    indexes = {
        item["name"]: item
        for item in sa.inspect(bind).get_indexes("outbox_events")
    }

    index_name = "ix_outbox_lease_recovery"
    expected_index_columns = [
        "status",
        "lease_expires_at",
        "available_at",
    ]

    if index_name in indexes:
        existing = indexes[index_name]

        if (
            existing.get("column_names") != expected_index_columns
            or existing.get("unique", False)
        ):
            raise RuntimeError(
                f"Unexpected definition for {index_name}"
            )
    else:
        op.create_index(
            index_name,
            "outbox_events",
            expected_index_columns,
            unique=False,
        )


def downgrade() -> None:
    raise RuntimeError(
        "This reconciliation migration is intentionally non-reversible. "
        "Review the database schema before any manual rollback."
    )
