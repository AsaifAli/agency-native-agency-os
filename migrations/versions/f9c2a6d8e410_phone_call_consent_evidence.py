"""Add channel-specific phone-call consent evidence to CRM contacts.

Revision ID: f9c2a6d8e410
Revises: a7c2d59e481b
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f9c2a6d8e410"
down_revision: Union[str, Sequence[str], None] = "a7c2d59e481b"
branch_labels = None
depends_on = None

STATUS_CONSTRAINT = "ck_contact_phone_call_consent_status"
EVIDENCE_CONSTRAINT = "ck_contact_phone_call_consent_evidence"
CHECK_CONSTRAINTS = {
    STATUS_CONSTRAINT: (
        "phone_call_consent_status IN "
        "('unknown','pending','granted','withdrawn')"
    ),
    EVIDENCE_CONSTRAINT: (
        "phone_call_consent_status != 'granted' OR "
        "(length(trim(phone_call_consent_source)) > 0 AND "
        "phone_call_consent_recorded_at IS NOT NULL)"
    ),
}
COLUMNS = (
    sa.Column(
        "phone_call_consent_status",
        sa.String(24),
        nullable=False,
        server_default="unknown",
    ),
    sa.Column(
        "phone_call_consent_source",
        sa.String(200),
        nullable=False,
        server_default="",
    ),
    sa.Column(
        "phone_call_consent_recorded_at",
        sa.DateTime(timezone=True),
        nullable=True,
    ),
)


def _existing_columns() -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns("contacts")}


def _existing_checks() -> dict[str, str]:
    inspector = sa.inspect(op.get_bind())
    return {
        item["name"]: item.get("sqltext", "")
        for item in inspector.get_check_constraints("contacts")
        if item.get("name")
    }


def upgrade() -> None:
    # SQLite DDL is non-transactional in this migration environment. Make each
    # additive step safe to retry if an earlier attempt stopped part-way through.
    existing_columns = _existing_columns()
    for column in COLUMNS:
        if column.name not in existing_columns:
            op.add_column("contacts", column)

    existing_checks = _existing_checks()
    missing_checks = {
        name: expression
        for name, expression in CHECK_CONSTRAINTS.items()
        if name not in existing_checks
    }

    if not missing_checks:
        return

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("contacts") as batch_op:
            for name, expression in missing_checks.items():
                batch_op.create_check_constraint(name, expression)
    else:
        for name, expression in missing_checks.items():
            op.create_check_constraint(name, "contacts", expression)


def downgrade() -> None:
    existing_columns = _existing_columns()
    existing_checks = _existing_checks()

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("contacts") as batch_op:
            for name in CHECK_CONSTRAINTS:
                if name in existing_checks:
                    batch_op.drop_constraint(name, type_="check")
            for column in reversed(COLUMNS):
                if column.name in existing_columns:
                    batch_op.drop_column(column.name)
        return

    for name in CHECK_CONSTRAINTS:
        if name in existing_checks:
            op.drop_constraint(name, "contacts", type_="check")
    for column in reversed(COLUMNS):
        if column.name in existing_columns:
            op.drop_column("contacts", column.name)
