"""Associate Agency OS executions with scoped machine sessions."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "q7f2b9d4c631"
down_revision: Union[str, Sequence[str], None] = "p6d8e2a4f913"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("executions") as batch:
        batch.add_column(sa.Column("machine_session_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_execution_machine_session_scope",
            "agent_sessions",
            ["org_id", "workspace_id", "machine_session_id"],
            ["org_id", "workspace_id", "id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint(
            "uq_execution_machine_session_scope",
            ["org_id", "workspace_id", "machine_session_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("executions") as batch:
        batch.drop_constraint("uq_execution_machine_session_scope", type_="unique")
        batch.drop_constraint("fk_execution_machine_session_scope", type_="foreignkey")
        batch.drop_column("machine_session_id")
