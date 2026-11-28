"""Restrict API writes to the pre-provisioned OIDC identity binding fields.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    # `users` is the deliberately shared internal identity directory, not a
    # client-data table. The API may read provisioned identities and bind an
    # OIDC issuer/subject, but it must not create/delete users or mutate their
    # email, display name, activation state, or primary key.
    op.execute("""
        REVOKE ALL ON TABLE public.users
        FROM PUBLIC, agency_os_app, agency_os_worker
    """)
    op.execute("GRANT SELECT ON TABLE public.users TO agency_os_app")
    op.execute("""
        GRANT UPDATE (oidc_issuer, oidc_subject)
        ON TABLE public.users TO agency_os_app
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    raise RuntimeError(
        "Unsafe downgrade refused: restoring broad API writes to the shared "
        "user identity directory would weaken identity integrity"
    )
