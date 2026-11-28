"""Add workspace-scoped knowledge versions and source-linked business drafts."""
from alembic import op
import sqlalchemy as sa

revision = "a7b2c9d4e1f6"
down_revision = "e8a1c3d5f7b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(36), nullable=True),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_reference", sa.String(240), nullable=False),
        sa.Column("classification", sa.String(24), nullable=False),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("effective_until", sa.DateTime(timezone=True)),
        sa.Column("retention_policy", sa.String(24), nullable=False, server_default="standard"),
        sa.Column("retention_until", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("supersedes_id", sa.String(36), sa.ForeignKey("knowledge_items.id", ondelete="RESTRICT")),
        sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "workspace_id", "key", "version", name="uq_knowledge_item_version"),
        sa.ForeignKeyConstraint(["org_id", "workspace_id", "client_id"], ["clients.org_id", "clients.workspace_id", "clients.id"],
                                ondelete="RESTRICT", name="fk_knowledge_client_scope"),
        sa.CheckConstraint("classification IN ('public','internal','confidential','restricted')", name="ck_knowledge_classification"),
        sa.CheckConstraint("status IN ('draft','approved','retired')", name="ck_knowledge_status"),
        sa.CheckConstraint("version >= 1", name="ck_knowledge_version_positive"),
        sa.CheckConstraint("effective_until IS NULL OR effective_until >= effective_from", name="ck_knowledge_effective_window"),
        sa.CheckConstraint("retention_policy IN ('standard','contractual','legal_hold')", name="ck_knowledge_retention_policy"),
    )
    op.create_index("ix_knowledge_items_org_id", "knowledge_items", ["org_id"])
    op.create_index("ix_knowledge_items_workspace_id", "knowledge_items", ["workspace_id"])
    op.create_index("ix_knowledge_items_scope_key", "knowledge_items", ["org_id", "workspace_id", "key", "version"])
    op.create_index("ix_knowledge_items_scope_client", "knowledge_items", ["org_id", "workspace_id", "client_id"])
    op.create_table(
        "business_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('front_desk','meeting_proposal','receivable_followup')", name="ck_business_draft_kind"),
        sa.CheckConstraint("status IN ('draft','reviewed','rejected')", name="ck_business_draft_status"),
    )
    op.create_index("ix_business_drafts_org_id", "business_drafts", ["org_id"])
    op.create_index("ix_business_drafts_workspace_id", "business_drafts", ["workspace_id"])
    op.create_index("ix_business_drafts_scope_kind_status", "business_drafts", ["org_id", "workspace_id", "kind", "status"])
    if op.get_bind().dialect.name == "postgresql":
        for table in ("knowledge_items", "business_drafts"):
            op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE public."{table}" FORCE ROW LEVEL SECURITY')
            # These records are currently accessed through authenticated human OS
            # routes only. Do not grant worker access until an explicit, tested
            # execution-capability adapter is introduced; forged machine GUCs
            # must never authorize the worker role.
            policy = """(
                agency_os_private.user_has_workspace_access(
                    org_id, workspace_id, nullif(current_setting('agency_os.user_id', true), '')
                )
                OR (
                    session_user <> 'agency_os_worker'
                    AND org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                    AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                )
            )"""
            op.execute(f'CREATE POLICY tenant_isolation ON public."{table}" USING ({policy}) WITH CHECK ({policy})')
            op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON public."{table}" TO agency_os_app')
            op.execute(f'REVOKE ALL ON public."{table}" FROM agency_os_worker')


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("business_drafts", "knowledge_items"):
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON public."{table}"')
    op.drop_table("business_drafts")
    op.drop_table("knowledge_items")
