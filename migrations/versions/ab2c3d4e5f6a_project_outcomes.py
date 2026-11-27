"""Add RAAS project outcomes, immutable measurements and tenant RLS.

Revision ID: ab2c3d4e5f6a
Revises: aa1b2c3d4e5f
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ab2c3d4e5f6a"
down_revision: Union[str, Sequence[str], None] = "aa1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("uq_projects_scope_id", "projects", ["org_id", "workspace_id", "id"], unique=True)
    op.create_index("uq_milestones_scope_id", "milestones", ["org_id", "workspace_id", "id"], unique=True)
    op.create_index("uq_evaluation_runs_scope_id", "evaluation_runs", ["org_id", "workspace_id", "id"], unique=True)
    op.create_table(
        "project_outcomes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("problem_statement", sa.Text(), nullable=False),
        sa.Column("desired_outcome", sa.Text(), nullable=False),
        sa.Column("metric_name", sa.String(length=160), nullable=False),
        sa.Column("metric_unit", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("baseline_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("target_value", sa.Numeric(20, 6), nullable=False),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("measurement_method", sa.Text(), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("delivery_acceptance_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("acceptance_results", sa.JSON(), nullable=False),
        sa.Column("acceptance_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("decided_by_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_project_outcomes_workspace_scope",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id", "project_id"],
            ["projects.org_id", "projects.workspace_id", "projects.id"],
            ondelete="CASCADE", name="fk_project_outcomes_project_scope",
        ),
        sa.UniqueConstraint("org_id", "workspace_id", "id", name="uq_project_outcomes_scope_id"),
        sa.CheckConstraint("direction IN ('increase','decrease')", name="ck_project_outcome_direction"),
        sa.CheckConstraint("delivery_acceptance_status IN ('pending','accepted','rejected')",
                           name="ck_project_outcome_acceptance_status"),
    )
    op.create_index("ix_project_outcomes_org_id", "project_outcomes", ["org_id"])
    op.create_index("ix_project_outcomes_workspace_id", "project_outcomes", ["workspace_id"])
    op.create_index("ix_project_outcomes_project_id", "project_outcomes", ["project_id"])
    op.create_index("ix_project_outcomes_scope_project", "project_outcomes", ["org_id", "workspace_id", "project_id"])

    op.create_table(
        "outcome_measurements",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("org_id", sa.String(length=36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("outcome_id", sa.String(length=36), nullable=False),
        sa.Column("value", sa.Numeric(20, 6), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_reference", sa.String(length=240), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column("supporting_evaluation_run_id", sa.String(length=36), nullable=True),
        sa.Column("milestone_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_outcome_measurements_workspace_scope",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id", "outcome_id"],
            ["project_outcomes.org_id", "project_outcomes.workspace_id", "project_outcomes.id"],
            ondelete="CASCADE", name="fk_outcome_measurements_outcome_scope",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id", "supporting_evaluation_run_id"],
            ["evaluation_runs.org_id", "evaluation_runs.workspace_id", "evaluation_runs.id"],
            ondelete="RESTRICT", name="fk_outcome_measurements_evaluation_scope",
        ),
        sa.ForeignKeyConstraint(
            ["org_id", "workspace_id", "milestone_id"],
            ["milestones.org_id", "milestones.workspace_id", "milestones.id"],
            ondelete="RESTRICT", name="fk_outcome_measurements_milestone_scope",
        ),
        sa.UniqueConstraint("org_id", "workspace_id", "id", name="uq_outcome_measurements_scope_id"),
        sa.CheckConstraint(
            "source_type IN ('agency_measured','client_reported','system_measured')",
            name="ck_outcome_measurement_source_type",
        ),
    )
    op.create_index("ix_outcome_measurements_org_id", "outcome_measurements", ["org_id"])
    op.create_index("ix_outcome_measurements_workspace_id", "outcome_measurements", ["workspace_id"])
    op.create_index("ix_outcome_measurements_outcome_id", "outcome_measurements", ["outcome_id"])
    op.create_index(
        "ix_outcome_measurements_scope_outcome_time",
        "outcome_measurements", ["org_id", "workspace_id", "outcome_id", "measured_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE public.project_outcomes ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.project_outcomes FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.outcome_measurements ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.outcome_measurements FORCE ROW LEVEL SECURITY")
        predicate = """(
            agency_os_private.user_has_workspace_access(
                org_id, workspace_id,
                nullif(current_setting('agency_os.user_id', true), '')
            )
        )"""
        for table in ("project_outcomes", "outcome_measurements"):
            op.execute(
                f'CREATE POLICY tenant_isolation ON public."{table}" '
                f'USING {predicate} WITH CHECK {predicate}'
            )
        op.execute("REVOKE ALL ON TABLE public.project_outcomes, public.outcome_measurements FROM agency_os_worker")
        op.execute("GRANT SELECT, INSERT ON TABLE public.project_outcomes TO agency_os_app")
        op.execute("REVOKE UPDATE, DELETE ON TABLE public.project_outcomes FROM agency_os_app")
        op.execute("""
            GRANT UPDATE (
                delivery_acceptance_status, acceptance_results, acceptance_note,
                decided_by_user_id, decided_at, updated_at
            ) ON TABLE public.project_outcomes TO agency_os_app
        """)
        op.execute("GRANT SELECT, INSERT ON TABLE public.outcome_measurements TO agency_os_app")

        op.execute("""
            CREATE OR REPLACE FUNCTION agency_os_private.reject_outcome_measurement_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $function$
            DECLARE is_superuser boolean;
            BEGIN
                SELECT r.rolsuper INTO is_superuser
                FROM pg_catalog.pg_roles AS r WHERE r.rolname = session_user;
                IF COALESCE(is_superuser, false) THEN
                    IF TG_OP = 'DELETE' THEN
                        RETURN OLD;
                    END IF;
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'outcome_measurements are append-only'
                    USING ERRCODE = '55000';
            END;
            $function$
        """)
        op.execute("ALTER FUNCTION agency_os_private.reject_outcome_measurement_mutation() OWNER TO agency_os_migrator")
        op.execute("REVOKE ALL ON FUNCTION agency_os_private.reject_outcome_measurement_mutation() FROM PUBLIC")
        op.execute("""
            CREATE TRIGGER outcome_measurements_append_only
            BEFORE UPDATE OR DELETE ON public.outcome_measurements
            FOR EACH ROW EXECUTE FUNCTION agency_os_private.reject_outcome_measurement_mutation()
        """)
        op.execute("""
            CREATE OR REPLACE FUNCTION agency_os_private.protect_project_outcome_contract()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, public
            AS $function$
            DECLARE is_superuser boolean;
            BEGIN
                SELECT r.rolsuper INTO is_superuser
                FROM pg_catalog.pg_roles AS r WHERE r.rolname = session_user;
                IF COALESCE(is_superuser, false) THEN
                    RETURN NEW;
                END IF;
                IF ROW(
                    NEW.id, NEW.org_id, NEW.workspace_id, NEW.project_id, NEW.title,
                    NEW.problem_statement, NEW.desired_outcome, NEW.metric_name,
                    NEW.metric_unit, NEW.direction, NEW.baseline_value,
                    NEW.target_value, NEW.target_date, NEW.measurement_method,
                    NEW.acceptance_criteria::text, NEW.owner_user_id, NEW.created_at
                ) IS DISTINCT FROM ROW(
                    OLD.id, OLD.org_id, OLD.workspace_id, OLD.project_id, OLD.title,
                    OLD.problem_statement, OLD.desired_outcome, OLD.metric_name,
                    OLD.metric_unit, OLD.direction, OLD.baseline_value,
                    OLD.target_value, OLD.target_date, OLD.measurement_method,
                    OLD.acceptance_criteria::text, OLD.owner_user_id, OLD.created_at
                ) THEN
                    RAISE EXCEPTION 'agreed project outcome terms are immutable'
                        USING ERRCODE = '55000';
                END IF;
                RETURN NEW;
            END;
            $function$
        """)
        op.execute("ALTER FUNCTION agency_os_private.protect_project_outcome_contract() OWNER TO agency_os_migrator")
        op.execute("REVOKE ALL ON FUNCTION agency_os_private.protect_project_outcome_contract() FROM PUBLIC")
        op.execute("""
            CREATE TRIGGER project_outcome_contract_immutable
            BEFORE UPDATE ON public.project_outcomes
            FOR EACH ROW EXECUTE FUNCTION agency_os_private.protect_project_outcome_contract()
        """)
        op.execute("REVOKE UPDATE, DELETE ON TABLE public.outcome_measurements FROM agency_os_app")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS project_outcome_contract_immutable ON public.project_outcomes")
        op.execute("DROP FUNCTION IF EXISTS agency_os_private.protect_project_outcome_contract()")
        op.execute("DROP TRIGGER IF EXISTS outcome_measurements_append_only ON public.outcome_measurements")
        op.execute("DROP FUNCTION IF EXISTS agency_os_private.reject_outcome_measurement_mutation()")
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.outcome_measurements")
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.project_outcomes")
        op.execute("ALTER TABLE public.outcome_measurements NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.outcome_measurements DISABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.project_outcomes NO FORCE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE public.project_outcomes DISABLE ROW LEVEL SECURITY")
    op.drop_table("outcome_measurements")
    op.drop_table("project_outcomes")
    op.drop_index("uq_projects_scope_id", table_name="projects")
    op.drop_index("uq_milestones_scope_id", table_name="milestones")
    op.drop_index("uq_evaluation_runs_scope_id", table_name="evaluation_runs")
