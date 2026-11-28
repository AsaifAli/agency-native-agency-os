"""Prevent runtime roles from creating objects in the public schema.

SECURITY DEFINER routines use fixed search_path values that include public.
Runtime principals must not be able to create shadow objects there.
"""
from alembic import op

revision = "d6f8a0b2c4e6"
down_revision = "d5e7f9a1c3b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        "REVOKE CREATE ON SCHEMA public "
        "FROM PUBLIC, agency_os_app, agency_os_worker"
    )
    op.execute(
        "GRANT USAGE ON SCHEMA public TO agency_os_app, agency_os_worker"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Unsafe downgrade refused: restoring runtime CREATE on public would "
        "re-enable object-shadowing risk for SECURITY DEFINER search paths"
    )
