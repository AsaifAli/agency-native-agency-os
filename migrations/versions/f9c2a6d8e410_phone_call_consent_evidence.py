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


def upgrade() -> None:
    op.add_column("contacts", sa.Column("phone_call_consent_status", sa.String(24), nullable=False, server_default="unknown"))
    op.add_column("contacts", sa.Column("phone_call_consent_source", sa.String(200), nullable=False, server_default=""))
    op.add_column("contacts", sa.Column("phone_call_consent_recorded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_contact_phone_call_consent_status", "contacts",
        "phone_call_consent_status IN ('unknown','pending','granted','withdrawn')",
    )
    op.create_check_constraint(
        "ck_contact_phone_call_consent_evidence", "contacts",
        "phone_call_consent_status != 'granted' OR (length(trim(phone_call_consent_source)) > 0 AND phone_call_consent_recorded_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_contact_phone_call_consent_evidence", "contacts", type_="check")
    op.drop_constraint("ck_contact_phone_call_consent_status", "contacts", type_="check")
    op.drop_column("contacts", "phone_call_consent_recorded_at")
    op.drop_column("contacts", "phone_call_consent_source")
    op.drop_column("contacts", "phone_call_consent_status")
