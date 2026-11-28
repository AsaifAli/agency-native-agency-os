"""Add immutable workspace-scoped Agent configuration versions.

Revision ID: f2a4c6e8b0d2
Revises: c4d8e2f6a1b3
"""
import hashlib
import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2a4c6e8b0d2"
down_revision = "c4d8e2f6a1b3"
branch_labels = None
depends_on = None


def _canonical_config(row):
    return {
        "name": row["name"],
        "department": row["department"],
        "instructions": row["instructions"] or "",
        "runtime": row["runtime"],
        "data_class": row["data_class"],
        "runtime_config": {},
    }


def upgrade() -> None:
    bind = op.get_bind()
    enum_type = (
        postgresql.ENUM(
            "synthetic", "public", "commercial", "confidential", "regulated",
            name="dataclass", create_type=False,
        )
        if bind.dialect.name == "postgresql"
        else sa.Enum(
            "synthetic", "public", "commercial", "confidential", "regulated",
            name="dataclass",
        )
    )

    op.add_column("agents", sa.Column("current_version_id", sa.String(36), nullable=True))
    op.add_column("executions", sa.Column("agent_version_id", sa.String(36), nullable=True))
    op.create_table(
        "agent_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("agent_id", sa.String(36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("department", sa.String(100), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("runtime", sa.String(80), nullable=False),
        sa.Column("data_class", enum_type, nullable=False),
        sa.Column("runtime_config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("config_sha256", sa.String(64), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id", "agent_id"],
            ["agents.org_id", "agents.workspace_id", "agents.id"],
            ondelete="RESTRICT",
            name="fk_agent_version_agent_scope",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "org_id", "workspace_id", "agent_id", "version_number",
            name="uq_agent_version_number",
        ),
        sa.UniqueConstraint(
            "org_id", "workspace_id", "agent_id", "id",
            name="uq_agent_version_scope_id",
        ),
        sa.CheckConstraint("version_number >= 1", name="ck_agent_version_number"),
    )
    op.create_index(
        "ix_agent_version_scope_created",
        "agent_versions",
        ["org_id", "workspace_id", "agent_id", "created_at"],
    )
    op.create_index(
        "ix_execution_agent_version_id",
        "executions",
        ["agent_version_id"],
    )

    # Backfill a version 1 for every existing Agent before adding the
    # active-version and execution-version foreign keys.
    version_table = sa.table(
        "agent_versions",
        sa.column("id", sa.String(36)),
        sa.column("org_id", sa.String(36)),
        sa.column("workspace_id", sa.String(36)),
        sa.column("agent_id", sa.String(36)),
        sa.column("version_number", sa.Integer()),
        sa.column("name", sa.String(200)),
        sa.column("department", sa.String(100)),
        sa.column("instructions", sa.Text()),
        sa.column("runtime", sa.String(80)),
        sa.column("data_class", enum_type),
        sa.column("runtime_config", sa.JSON()),
        sa.column("config_sha256", sa.String(64)),
        sa.column("change_reason", sa.Text()),
        sa.column("created_by", sa.String(36)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    agents = bind.execute(sa.text("""
        SELECT id, org_id, workspace_id, name, department, instructions,
               runtime, data_class::text AS data_class, created_at
        FROM public.agents
        ORDER BY org_id, workspace_id, id
    """) if bind.dialect.name == "postgresql" else sa.text("""
        SELECT id, org_id, workspace_id, name, department, instructions,
               runtime, data_class, created_at
        FROM agents
        ORDER BY org_id, workspace_id, id
    """)).mappings().all()

    for row in agents:
        config = _canonical_config(row)
        canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        version_id = str(uuid.uuid4())
        bind.execute(version_table.insert().values(
            id=version_id,
            org_id=row["org_id"],
            workspace_id=row["workspace_id"],
            agent_id=row["id"],
            version_number=1,
            name=config["name"],
            department=config["department"],
            instructions=config["instructions"],
            runtime=config["runtime"],
            data_class=config["data_class"],
            runtime_config={},
            config_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            change_reason="Initial version backfilled from existing Agent configuration",
            created_by=None,
            created_at=row["created_at"],
        ))
        bind.execute(sa.text("""
            UPDATE agents SET current_version_id = :version_id
            WHERE id = :agent_id AND org_id = :org_id AND workspace_id = :workspace_id
        """), {
            "version_id": version_id,
            "agent_id": row["id"],
            "org_id": row["org_id"],
            "workspace_id": row["workspace_id"],
        })

    bind.execute(sa.text("""
        UPDATE executions AS e
        SET agent_version_id = a.current_version_id
        FROM agents AS a
        WHERE e.agent_id = a.id
          AND e.org_id = a.org_id
          AND e.workspace_id = a.workspace_id
          AND e.agent_version_id IS NULL
    """) if bind.dialect.name == "postgresql" else sa.text("""
        UPDATE executions
        SET agent_version_id = (
            SELECT a.current_version_id FROM agents AS a
            WHERE executions.agent_id = a.id
              AND executions.org_id = a.org_id
              AND executions.workspace_id = a.workspace_id
        )
        WHERE agent_version_id IS NULL
    """))

    if bind.dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_agents_current_version_scope",
            "agents", "agent_versions",
            ["org_id", "workspace_id", "id", "current_version_id"],
            ["org_id", "workspace_id", "agent_id", "id"],
            ondelete="RESTRICT",
        )
        op.create_foreign_key(
            "fk_execution_agent_version_scope",
            "executions", "agent_versions",
            ["org_id", "workspace_id", "agent_id", "agent_version_id"],
            ["org_id", "workspace_id", "agent_id", "id"],
            ondelete="RESTRICT",
        )
        op.execute("ALTER TABLE public.agent_versions ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.agent_versions FORCE ROW LEVEL SECURITY")
        op.execute("""
            CREATE POLICY tenant_isolation ON public.agent_versions
            USING (
                agency_os_private.user_has_workspace_access(
                    org_id, workspace_id,
                    nullif(current_setting('agency_os.user_id', true), '')
                )
                OR (
                    session_user = 'agency_os_worker'
                    AND EXISTS (
                        SELECT 1 FROM public.executions AS e
                        WHERE e.org_id = agent_versions.org_id
                          AND e.workspace_id = agent_versions.workspace_id
                          AND e.agent_id = agent_versions.agent_id
                          AND e.agent_version_id = agent_versions.id
                          AND agency_os_private.worker_has_execution_context(
                              e.org_id, e.workspace_id, e.id
                          )
                    )
                )
            )
            WITH CHECK (
                agency_os_private.user_has_workspace_access(
                    org_id, workspace_id,
                    nullif(current_setting('agency_os.user_id', true), '')
                )
            )
        """)
        op.execute("GRANT SELECT, INSERT ON TABLE public.agent_versions TO agency_os_app")
        op.execute("GRANT SELECT ON TABLE public.agent_versions TO agency_os_worker")
        op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.agent_versions FROM agency_os_app, agency_os_worker")
        op.execute("""
            CREATE OR REPLACE FUNCTION agency_os_private.reject_agent_version_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public, agency_os_private
            AS $function$
            BEGIN
                RAISE EXCEPTION 'agent_versions are immutable';
            END
            $function$
        """)
        op.execute("""
            ALTER FUNCTION agency_os_private.reject_agent_version_mutation()
            OWNER TO agency_os_migrator
        """)
        op.execute("""
            REVOKE ALL ON FUNCTION agency_os_private.reject_agent_version_mutation()
            FROM PUBLIC, agency_os_app, agency_os_worker
        """)
        op.execute("""
            CREATE TRIGGER trg_agent_versions_immutable
            BEFORE UPDATE OR DELETE ON public.agent_versions
            FOR EACH ROW EXECUTE FUNCTION agency_os_private.reject_agent_version_mutation()
        """)


def downgrade() -> None:
    raise RuntimeError(
        "Agent version history and execution pins are immutable; use a forward migration."
    )
