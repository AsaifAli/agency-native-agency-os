"""Link delivery tasks to milestones within the same workspace.

Revision ID: bc3d5e7f9a12
Revises: ab2c3d4e5f6a
"""
from alembic import op
import sqlalchemy as sa

revision = "bc3d5e7f9a12"
down_revision = "ab2c3d4e5f6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("milestone_id", sa.String(length=36), nullable=True))
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.create_unique_constraint(
            "uq_tasks_scope_id", ["org_id", "workspace_id", "id"]
        )
        batch_op.create_foreign_key(
            "fk_tasks_milestone_scope",
            "milestones",
            ["org_id", "workspace_id", "milestone_id"],
            ["org_id", "workspace_id", "id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_task_org_workspace_milestone",
            ["org_id", "workspace_id", "milestone_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index("ix_task_org_workspace_milestone")
        batch_op.drop_constraint("fk_tasks_milestone_scope", type_="foreignkey")
        batch_op.drop_constraint("uq_tasks_scope_id", type_="unique")
        batch_op.drop_column("milestone_id")
