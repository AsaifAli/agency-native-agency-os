"""Add session-bound MCP bearer credentials and execution session binding."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "r8f4c2a1d7e6"
down_revision: Union[str, Sequence[str], None] = "p6d8e2a4f913"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch:
        batch.create_unique_constraint(
            "uq_agent_session_identity_scope_id",
            ["org_id", "workspace_id", "machine_identity_id", "id"],
        )

    with op.batch_alter_table("executions") as batch:
        batch.add_column(sa.Column("machine_session_id", sa.String(length=36), nullable=True))
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

    op.create_table(
        "machine_session_credentials",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("machine_identity_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_prefix", sa.String(length=80), nullable=False),
        sa.Column("credential_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=80), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_window_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_count_window", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provider_vault_id", sa.String(length=160), nullable=True),
        sa.Column("provider_credential_id", sa.String(length=160), nullable=True),
        sa.Column(
            "provider_credential_status",
            sa.String(length=24),
            server_default="not_created",
            nullable=False,
        ),
        sa.Column("provider_credential_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_credential_deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "org_id", "workspace_id", "id",
            name="uq_machine_session_credential_scope_id",
        ),
        sa.UniqueConstraint("token_hash", name="uq_machine_session_credential_token_hash"),
        sa.UniqueConstraint(
            "org_id", "workspace_id", "session_id", "credential_version",
            name="uq_machine_session_credential_version",
        ),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_machine_session_credentials_org",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id", "machine_identity_id"],
            ["machine_identities.org_id", "machine_identities.workspace_id", "machine_identities.id"],
            ondelete="CASCADE",
            name="fk_machine_session_credential_identity_scope",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id", "machine_identity_id", "session_id"],
            [
                "agent_sessions.org_id",
                "agent_sessions.workspace_id",
                "agent_sessions.machine_identity_id",
                "agent_sessions.id",
            ],
            ondelete="CASCADE",
            name="fk_machine_session_credential_session_identity_scope",
        ),
        sa.CheckConstraint(
            "credential_version >= 1",
            name="ck_machine_session_credential_version",
        ),
        sa.CheckConstraint(
            "request_count_window >= 0",
            name="ck_machine_session_credential_request_count",
        ),
        sa.CheckConstraint(
            "provider_credential_status IN ('not_created','active','delete_pending','deleted','failed')",
            name="ck_machine_session_credential_provider_status",
        ),
    )
    op.create_index(
        "ix_machine_session_credential_session_revoked",
        "machine_session_credentials",
        ["org_id", "workspace_id", "session_id", "revoked_at"],
    )
    op.create_index(
        "ix_machine_session_credential_provider_cleanup",
        "machine_session_credentials",
        ["provider_credential_status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_machine_session_credential_provider_cleanup",
        table_name="machine_session_credentials",
    )
    op.drop_index(
        "ix_machine_session_credential_session_revoked",
        table_name="machine_session_credentials",
    )
    op.drop_table("machine_session_credentials")

    with op.batch_alter_table("executions") as batch:
        batch.drop_constraint("uq_execution_machine_session_scope", type_="unique")
        batch.drop_constraint("fk_execution_machine_session_scope", type_="foreignkey")
        batch.drop_column("machine_session_id")

    with op.batch_alter_table("agent_sessions") as batch:
        batch.drop_constraint("uq_agent_session_identity_scope_id", type_="unique")
