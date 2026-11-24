"""Create invoice register and append-only payment receipt ledger.

Revision ID: g6e2f4a8c195
Revises: f5d9e1a3b764
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "g6e2f4a8c195"
down_revision: Union[str, Sequence[str], None] = "f5d9e1a3b764"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_id", sa.String(36), sa.ForeignKey("contract_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("invoice_number", sa.String(80), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("line_items", sa.JSON(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("paid_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("approval_id", sa.String(36), sa.ForeignKey("approvals.id"), nullable=True),
        sa.Column("external_reference", sa.String(240), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "workspace_id", "invoice_number", name="uq_invoice_number_workspace"),
        sa.UniqueConstraint("org_id", "workspace_id", "external_reference", name="uq_invoice_external_reference"),
        sa.CheckConstraint("status IN ('draft','pending_approval','issued','partially_paid','paid','rejected','cancelled')", name="ck_invoice_record_status"),
        sa.CheckConstraint("amount_minor > 0 AND paid_minor >= 0 AND paid_minor <= amount_minor", name="ck_invoice_amount_paid_range"),
    )
    op.create_index("ix_invoice_records_scope_status", "invoice_records", ["org_id", "workspace_id", "status"])
    op.create_index("ix_invoice_records_org_id", "invoice_records", ["org_id"])
    op.create_index("ix_invoice_records_workspace_id", "invoice_records", ["workspace_id"])
    op.create_index("ix_invoice_records_client_id", "invoice_records", ["client_id"])
    op.create_index("ix_invoice_records_contract_id", "invoice_records", ["contract_id"])
    op.create_index("ix_invoice_records_project_id", "invoice_records", ["project_id"])

    op.create_table(
        "payment_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoice_records.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_reference", sa.String(240), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("payment_method", sa.String(40), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "workspace_id", "external_reference", name="uq_payment_receipt_reference"),
        sa.CheckConstraint("amount_minor > 0", name="ck_payment_receipt_amount_positive"),
    )
    op.create_index("ix_payment_receipts_invoice_paid", "payment_receipts", ["org_id", "workspace_id", "invoice_id", "paid_at"])
    op.create_index("ix_payment_receipts_org_id", "payment_receipts", ["org_id"])
    op.create_index("ix_payment_receipts_workspace_id", "payment_receipts", ["workspace_id"])
    op.create_index("ix_payment_receipts_invoice_id", "payment_receipts", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_receipts_invoice_id", table_name="payment_receipts")
    op.drop_index("ix_payment_receipts_workspace_id", table_name="payment_receipts")
    op.drop_index("ix_payment_receipts_org_id", table_name="payment_receipts")
    op.drop_index("ix_payment_receipts_invoice_paid", table_name="payment_receipts")
    op.drop_table("payment_receipts")
    op.drop_index("ix_invoice_records_project_id", table_name="invoice_records")
    op.drop_index("ix_invoice_records_contract_id", table_name="invoice_records")
    op.drop_index("ix_invoice_records_client_id", table_name="invoice_records")
    op.drop_index("ix_invoice_records_workspace_id", table_name="invoice_records")
    op.drop_index("ix_invoice_records_org_id", table_name="invoice_records")
    op.drop_index("ix_invoice_records_scope_status", table_name="invoice_records")
    op.drop_table("invoice_records")
