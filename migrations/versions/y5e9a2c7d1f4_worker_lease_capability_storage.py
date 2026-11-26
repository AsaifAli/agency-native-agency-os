"""Create private storage for database-verified worker lease capabilities.

This is schema groundwork only. No worker claim/lifecycle path uses these tables
until the follow-up capability verifier and runtime cutover are implemented.
"""
from alembic import op

revision = "y5e9a2c7d1f4"
down_revision = "x4c8d1e6f902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("CREATE SCHEMA IF NOT EXISTS agency_os_private")
    op.execute("""
        CREATE TABLE agency_os_private.worker_lease_capabilities (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            token_hash bytea NOT NULL UNIQUE,
            execution_id text NOT NULL REFERENCES public.executions(id) ON DELETE CASCADE,
            attempt_id text NOT NULL REFERENCES public.execution_attempts(id) ON DELETE CASCADE,
            worker_id text NOT NULL,
            lease_generation integer NOT NULL CHECK (lease_generation > 0),
            expires_at timestamptz NOT NULL,
            invalidated_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (octet_length(token_hash) = 32),
            UNIQUE (execution_id, attempt_id, worker_id, lease_generation)
        )
    """)
    op.execute("""
        CREATE INDEX worker_lease_capabilities_active_idx
        ON agency_os_private.worker_lease_capabilities
            (execution_id, attempt_id, worker_id, lease_generation, expires_at)
        WHERE invalidated_at IS NULL
    """)
    op.execute("""
        CREATE TABLE agency_os_private.worker_transaction_context (
            backend_pid integer NOT NULL,
            transaction_id bigint NOT NULL,
            capability_id uuid NOT NULL
                REFERENCES agency_os_private.worker_lease_capabilities(id)
                ON DELETE CASCADE,
            execution_id text NOT NULL,
            attempt_id text NOT NULL,
            worker_id text NOT NULL,
            lease_generation integer NOT NULL,
            established_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (backend_pid, transaction_id)
        )
    """)
    op.execute("""
        ALTER TABLE agency_os_private.worker_lease_capabilities
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        ALTER TABLE agency_os_private.worker_transaction_context
        OWNER TO agency_os_migrator
    """)
    op.execute("""
        REVOKE ALL ON TABLE
            agency_os_private.worker_lease_capabilities,
            agency_os_private.worker_transaction_context
        FROM PUBLIC, agency_os_app, agency_os_worker
    """)
    op.execute("""
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA agency_os_private
        FROM PUBLIC, agency_os_app, agency_os_worker
    """)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS agency_os_private.worker_transaction_context")
    op.execute("DROP TABLE IF EXISTS agency_os_private.worker_lease_capabilities")
