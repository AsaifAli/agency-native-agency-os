"""Add workspace-scoped Revenue and Delivery domain tables.

Revision ID: c91e2d7a4f10
Revises: eb75d47bfc63
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c91e2d7a4f10"
down_revision: Union[str, Sequence[str], None] = "eb75d47bfc63"
branch_labels = None
depends_on = None


def _scope_columns():
    return [
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspaces.id"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.String(36), primary_key=True),
        *_scope_columns(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("legal_name", sa.String(240)),
        sa.Column("external_key", sa.String(120), nullable=True),
        sa.Column("industry", sa.String(120), nullable=False, server_default=""),
        sa.Column("website", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="prospect"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "workspace_id", "external_key", name="uq_client_workspace_external_key"),
    )
    op.create_index("ix_clients_org_id", "clients", ["org_id"])
    op.create_index("ix_clients_workspace_id", "clients", ["workspace_id"])
    op.create_index("ix_clients_scope_status", "clients", ["org_id", "workspace_id", "status"])

    op.create_table(
        "contacts",
        sa.Column("id", sa.String(36), primary_key=True),
        *_scope_columns(),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id")),
        sa.Column("first_name", sa.String(120), nullable=False),
        sa.Column("last_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("email", sa.String(320), nullable=False, server_default=""),
        sa.Column("phone", sa.String(50), nullable=False, server_default=""),
        sa.Column("job_title", sa.String(160), nullable=False, server_default=""),
        sa.Column("source", sa.String(120), nullable=False, server_default=""),
        sa.Column("consent_status", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contacts_org_id", "contacts", ["org_id"])
    op.create_index("ix_contacts_workspace_id", "contacts", ["workspace_id"])
    op.create_index("ix_contacts_client_id", "contacts", ["client_id"])
    op.create_index("ix_contacts_scope_client", "contacts", ["org_id", "workspace_id", "client_id"])

    op.create_table(
        "leads",
        sa.Column("id", sa.String(36), primary_key=True),
        *_scope_columns(),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id")),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id")),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("contact_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("email", sa.String(320), nullable=False, server_default=""),
        sa.Column("source", sa.String(120), nullable=False, server_default=""),
        sa.Column("stage", sa.String(32), nullable=False, server_default="new"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("qualification_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("suppression_reason", sa.String(240), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_lead_score_range"),
    )
    op.create_index("ix_leads_org_id", "leads", ["org_id"])
    op.create_index("ix_leads_workspace_id", "leads", ["workspace_id"])
    op.create_index("ix_leads_client_id", "leads", ["client_id"])
    op.create_index("ix_leads_contact_id", "leads", ["contact_id"])
    op.create_index("ix_leads_scope_stage_created", "leads", ["org_id", "workspace_id", "stage", "created_at"])

    op.create_table(
        "opportunities",
        sa.Column("id", sa.String(36), primary_key=True),
        *_scope_columns(),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id")),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id")),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False, server_default="qualification"),
        sa.Column("amount_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("probability", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expected_close_date", sa.DateTime(timezone=True)),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor >= 0", name="ck_opportunity_amount_nonnegative"),
        sa.CheckConstraint("probability >= 0 AND probability <= 100", name="ck_opportunity_probability_range"),
    )
    op.create_index("ix_opportunities_org_id", "opportunities", ["org_id"])
    op.create_index("ix_opportunities_workspace_id", "opportunities", ["workspace_id"])
    op.create_index("ix_opportunities_client_id", "opportunities", ["client_id"])
    op.create_index("ix_opportunities_lead_id", "opportunities", ["lead_id"])
    op.create_index("ix_opportunities_scope_stage", "opportunities", ["org_id", "workspace_id", "stage"])

    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        *_scope_columns(),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id")),
        sa.Column("opportunity_id", sa.String(36), sa.ForeignKey("opportunities.id")),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        sa.Column("priority", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("budget_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("start_date", sa.DateTime(timezone=True)),
        sa.Column("due_date", sa.DateTime(timezone=True)),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("budget_minor >= 0", name="ck_project_budget_nonnegative"),
    )
    op.create_index("ix_projects_org_id", "projects", ["org_id"])
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])
    op.create_index("ix_projects_client_id", "projects", ["client_id"])
    op.create_index("ix_projects_opportunity_id", "projects", ["opportunity_id"])
    op.create_index("ix_projects_scope_status", "projects", ["org_id", "workspace_id", "status"])

    op.create_table(
        "milestones",
        sa.Column("id", sa.String(36), primary_key=True),
        *_scope_columns(),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("due_date", sa.DateTime(timezone=True)),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sort_order >= 0", name="ck_milestone_sort_order_nonnegative"),
    )
    op.create_index("ix_milestones_org_id", "milestones", ["org_id"])
    op.create_index("ix_milestones_workspace_id", "milestones", ["workspace_id"])
    op.create_index("ix_milestones_project_id", "milestones", ["project_id"])
    op.create_index("ix_milestones_scope_project", "milestones", ["org_id", "workspace_id", "project_id"])


def downgrade() -> None:
    for table, indexes in [
        ("milestones", ["ix_milestones_scope_project", "ix_milestones_project_id", "ix_milestones_workspace_id", "ix_milestones_org_id"]),
        ("projects", ["ix_projects_scope_status", "ix_projects_opportunity_id", "ix_projects_client_id", "ix_projects_workspace_id", "ix_projects_org_id"]),
        ("opportunities", ["ix_opportunities_scope_stage", "ix_opportunities_lead_id", "ix_opportunities_client_id", "ix_opportunities_workspace_id", "ix_opportunities_org_id"]),
        ("leads", ["ix_leads_scope_stage_created", "ix_leads_contact_id", "ix_leads_client_id", "ix_leads_workspace_id", "ix_leads_org_id"]),
        ("contacts", ["ix_contacts_scope_client", "ix_contacts_client_id", "ix_contacts_workspace_id", "ix_contacts_org_id"]),
        ("clients", ["ix_clients_scope_status", "ix_clients_workspace_id", "ix_clients_org_id"]),
    ]:
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
