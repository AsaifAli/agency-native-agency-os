"""Add workspace-scoped QA issues and retest evidence.

Revision ID: d1e3f5a7b9c2
Revises: bc3d5e7f9a12
"""
from alembic import op
import sqlalchemy as sa

revision = "d1e3f5a7b9c2"
down_revision = "bc3d5e7f9a12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qa_issues",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="major"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("reproducible_steps", sa.JSON(), nullable=False),
        sa.Column("expected_result", sa.Text(), nullable=False, server_default=""),
        sa.Column("actual_result", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_references", sa.JSON(), nullable=False),
        sa.Column("assigned_to_user_id", sa.String(length=36), nullable=True),
        sa.Column("retest_evaluation_run_id", sa.String(length=36), nullable=True),
        sa.Column("retest_evidence_trust", sa.String(length=32), nullable=True),
        sa.Column("fixed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id", "workspace_id"],
                                ["workspaces.org_id", "workspaces.id"],
                                ondelete="CASCADE", name="fk_qa_issues_workspace_scope"),
        sa.ForeignKeyConstraint(["org_id", "workspace_id", "project_id"],
                                ["projects.org_id", "projects.workspace_id", "projects.id"],
                                ondelete="CASCADE", name="fk_qa_issues_project_scope"),
        sa.ForeignKeyConstraint(["org_id", "workspace_id", "task_id"],
                                ["tasks.org_id", "tasks.workspace_id", "tasks.id"],
                                ondelete="RESTRICT", name="fk_qa_issues_task_scope"),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id", "retest_evaluation_run_id"],
            ["evaluation_runs.org_id", "evaluation_runs.workspace_id", "evaluation_runs.id"],
            ondelete="RESTRICT", name="fk_qa_issues_retest_evaluation_scope",
        ),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["closed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("org_id", "workspace_id", "id", name="uq_qa_issues_scope_id"),
        sa.CheckConstraint(
            "severity IN ('blocker','critical','major','minor','cosmetic')",
            name="ck_qa_issue_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open','triaged','in_progress','fixed','retest','closed')",
            name="ck_qa_issue_status",
        ),
        sa.CheckConstraint(
            "status != 'closed' OR (retest_evaluation_run_id IS NOT NULL AND retest_evidence_trust IS NOT NULL)",
            name="ck_qa_issue_closed_requires_retest",
        ),
    )
    op.create_index("ix_qa_issues_org_id", "qa_issues", ["org_id"])
    op.create_index("ix_qa_issues_workspace_id", "qa_issues", ["workspace_id"])
    op.create_index(
        "ix_qa_issues_scope_status_severity",
        "qa_issues", ["org_id", "workspace_id", "status", "severity"],
    )
    op.create_index(
        "ix_qa_issues_scope_project",
        "qa_issues", ["org_id", "workspace_id", "project_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.qa_issues ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.qa_issues FORCE ROW LEVEL SECURITY")
        predicate = """(
            agency_os_private.user_has_workspace_access(
                org_id, workspace_id,
                nullif(current_setting('agency_os.user_id', true), '')
            )
        )"""
        op.execute(
            "CREATE POLICY tenant_isolation ON public.qa_issues "
            f"USING {predicate} WITH CHECK {predicate}"
        )
        op.execute("REVOKE ALL ON TABLE public.qa_issues FROM agency_os_worker")
        op.execute("GRANT SELECT, INSERT, UPDATE ON TABLE public.qa_issues TO agency_os_app")
        op.execute("REVOKE DELETE ON TABLE public.qa_issues FROM agency_os_app")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.qa_issues")
        op.execute("ALTER TABLE public.qa_issues NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.qa_issues DISABLE ROW LEVEL SECURITY")
    op.drop_table("qa_issues")
