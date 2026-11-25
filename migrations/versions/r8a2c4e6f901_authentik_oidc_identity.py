"""Add immutable external OIDC subject mapping to local users."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "r8a2c4e6f901"
down_revision: Union[str, Sequence[str], None] = "q7f2b9d4c631"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("oidc_issuer", sa.String(length=500), nullable=True))
        batch.add_column(sa.Column("oidc_subject", sa.String(length=255), nullable=True))
        batch.create_unique_constraint("uq_users_oidc_issuer_subject", ["oidc_issuer", "oidc_subject"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("uq_users_oidc_issuer_subject", type_="unique")
        batch.drop_column("oidc_subject")
        batch.drop_column("oidc_issuer")
