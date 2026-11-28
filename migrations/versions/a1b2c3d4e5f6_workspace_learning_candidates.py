"""Add evidence-backed, founder-reviewed workspace learning candidates."""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = ("z6f1b3d8a2c5", "b7d4c9a2e6f1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(240), nullable=False),
        sa.Column("data_class", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending_review"),
        sa.Column("knowledge_item_id", sa.String(36), sa.ForeignKey("knowledge_items.id", ondelete="RESTRICT")),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "workspace_id", "idempotency_key", name="uq_learning_candidate_idempotency"),
        sa.CheckConstraint("status IN ('pending_review','promoted','rejected')", name="ck_learning_candidate_status"),
        sa.CheckConstraint("data_class IN ('synthetic','public','internal')", name="ck_learning_candidate_data_class"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_learning_candidate_confidence"),
    )
    op.create_index("ix_learning_candidates_org_id", "learning_candidates", ["org_id"])
    op.create_index("ix_learning_candidates_workspace_id", "learning_candidates", ["workspace_id"])
    op.create_index("ix_learning_candidate_scope_status", "learning_candidates", ["org_id", "workspace_id", "status", "created_at"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.learning_candidates ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.learning_candidates FORCE ROW LEVEL SECURITY")
        policy = """(
            session_user <> 'agency_os_worker'
            AND (
                agency_os_private.user_has_workspace_access(
                    org_id, workspace_id, nullif(current_setting('agency_os.user_id', true), '')
                )
                OR (
                    org_id = nullif(current_setting('agency_os.machine_org_id', true), '')
                    AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), '')
                )
            )
        )"""
        op.execute(f"CREATE POLICY tenant_isolation ON public.learning_candidates USING ({policy}) WITH CHECK ({policy})")
        op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.learning_candidates TO agency_os_app")
        op.execute("REVOKE ALL ON public.learning_candidates FROM agency_os_worker")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.learning_candidates")
    op.drop_table("learning_candidates")
