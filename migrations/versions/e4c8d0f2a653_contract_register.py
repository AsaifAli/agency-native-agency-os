"""Create founder-governed contract register.

Revision ID: e4c8d0f2a653
Revises: d3a7c9e1b542
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e4c8d0f2a653"
down_revision: Union[str, Sequence[str], None] = "d3a7c9e1b542"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contract_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("proposal_id", sa.String(36), sa.ForeignKey("proposals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_number", sa.String(80), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("terms_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("approval_id", sa.String(36), sa.ForeignKey("approvals.id"), nullable=True),
        sa.Column("signed_reference", sa.String(240), nullable=False, server_default=""),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "workspace_id", "contract_number", name="uq_contract_number_workspace"),
        sa.CheckConstraint("status IN ('draft','pending_approval','executed','rejected','terminated')", name="ck_contract_record_status"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_contract_record_amount_nonnegative"),
    )
    op.create_index("ix_contract_records_scope_status", "contract_records", ["org_id", "workspace_id", "status"])
    op.create_index("ix_contract_records_org_id", "contract_records", ["org_id"])
    op.create_index("ix_contract_records_workspace_id", "contract_records", ["workspace_id"])
    op.create_index("ix_contract_records_client_id", "contract_records", ["client_id"])
    op.create_index("ix_contract_records_proposal_id", "contract_records", ["proposal_id"])


def downgrade() -> None:
    op.drop_index("ix_contract_records_proposal_id", table_name="contract_records")
    op.drop_index("ix_contract_records_client_id", table_name="contract_records")
    op.drop_index("ix_contract_records_workspace_id", table_name="contract_records")
    op.drop_index("ix_contract_records_org_id", table_name="contract_records")
    op.drop_index("ix_contract_records_scope_status", table_name="contract_records")
    op.drop_table("contract_records")
