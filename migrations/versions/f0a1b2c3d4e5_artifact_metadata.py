"""Add tenant-scoped artifact metadata without enabling upload endpoints.

Object bytes remain in a future private storage adapter. This migration only
creates the OS-owned metadata boundary and enforces workspace RLS.
"""
from alembic import op
import sqlalchemy as sa

revision = "f0a1b2c3d4e5"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="initiated"),
        sa.Column("classification", sa.String(20), nullable=False, server_default="synthetic"),
        sa.Column("storage_provider", sa.String(40), nullable=False, server_default="pending"),
        sa.Column("object_key", sa.String(512), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(160), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("created_by_principal", sa.String(200), nullable=False),
        sa.Column("scanner_name", sa.String(100), nullable=True),
        sa.Column("scanner_version", sa.String(100), nullable=True),
        sa.Column("scan_result", sa.String(40), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_artifacts_workspace_org",
        ),
        sa.CheckConstraint("scope_type IN ('workspace', 'thread')", name="ck_artifacts_scope_type"),
        sa.CheckConstraint(
            "(scope_type = 'workspace' AND scope_id = workspace_id) OR "
            "(scope_type = 'thread' AND length(scope_id) BETWEEN 1 AND 160)",
            name="ck_artifacts_scope_binding",
        ),
        sa.CheckConstraint(
            "status IN ('initiated', 'quarantined', 'scanning', 'available', 'rejected', 'failed', 'deleting', 'deleted')",
            name="ck_artifacts_status",
        ),
        sa.CheckConstraint(
            "classification IN ('synthetic', 'public', 'commercial', 'confidential', 'regulated')",
            name="ck_artifacts_classification",
        ),
        sa.CheckConstraint("byte_size >= 0", name="ck_artifacts_byte_size_nonnegative"),
        sa.CheckConstraint("sha256 IS NULL OR length(sha256) = 64", name="ck_artifacts_sha256_length"),
        sa.CheckConstraint(
            "status NOT IN ('quarantined', 'scanning', 'available') OR object_key IS NOT NULL",
            name="ck_artifacts_storage_key_for_stored_states",
        ),
        sa.CheckConstraint(
            "status != 'available' OR (object_key IS NOT NULL AND sha256 IS NOT NULL "
            "AND byte_size > 0 AND scan_result = 'clean' AND scanner_name IS NOT NULL "
            "AND scanner_version IS NOT NULL)",
            name="ck_artifacts_available_requires_clean_scan",
        ),
        sa.UniqueConstraint("storage_provider", "object_key", name="uq_artifacts_storage_object"),
    )
    op.create_index("ix_artifacts_org_workspace_scope", "artifacts", ["org_id", "workspace_id", "scope_type", "scope_id"])
    op.create_index("ix_artifacts_org_workspace_status", "artifacts", ["org_id", "workspace_id", "status"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.artifacts ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.artifacts FORCE ROW LEVEL SECURITY")
        predicate = (
            "(agency_os_private.user_has_org_access("
            "org_id, nullif(current_setting('agency_os.user_id', true), '')) "
            "AND agency_os_private.user_has_workspace_access("
            "org_id, workspace_id, nullif(current_setting('agency_os.user_id', true), ''))) "
            "OR (org_id = nullif(current_setting('agency_os.machine_org_id', true), '') "
            "AND workspace_id = nullif(current_setting('agency_os.machine_workspace_id', true), ''))"
        )
        op.execute(
            "CREATE POLICY artifact_tenant_isolation ON public.artifacts "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.artifacts TO agency_os_app")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS artifact_tenant_isolation ON public.artifacts")
        op.execute("ALTER TABLE public.artifacts NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.artifacts DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_artifacts_org_workspace_status", table_name="artifacts")
    op.drop_index("ix_artifacts_org_workspace_scope", table_name="artifacts")
    op.drop_table("artifacts")
