"""PostgreSQL isolation and append-only enforcement for RAAS outcome evidence."""
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db import set_rls_context, verify_postgres_role
from app.models import Membership, Organization, Role, User, Workspace, WorkspaceGrant
from app.domain_models import Project, ProjectOutcome, OutcomeMeasurement

ADMIN_URL = os.getenv("AGENCY_OS_TEST_RLS_ADMIN_DATABASE_URL")
APP_URL = os.getenv("AGENCY_OS_TEST_RLS_DATABASE_URL")
pytestmark = pytest.mark.skipif(not (ADMIN_URL and APP_URL),
    reason="Set PostgreSQL admin and app URLs for live outcome RLS tests")


def test_outcome_rows_are_workspace_isolated_and_measurements_are_append_only():
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    app_engine = create_engine(APP_URL, pool_pre_ping=True)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    App = sessionmaker(bind=app_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    org = Organization(name=f"Outcome RLS {suffix}")
    user = User(email=f"outcome-rls-{suffix}@example.test")
    try:
        verify_postgres_role(
            app_engine, expected_bypassrls=False, require_rls=True,
            expected_role="agency_os_test_app",
        )
        with Admin() as db:
            db.add_all([org, user]); db.flush()
            workspace = Workspace(org_id=org.id, name="Granted workspace", created_by=user.id)
            other_workspace = Workspace(org_id=org.id, name="Un-granted workspace", created_by=user.id)
            db.add_all([workspace, other_workspace]); db.flush()
            db.add_all([
                Membership(org_id=org.id, user_id=user.id, role=Role.owner),
                WorkspaceGrant(org_id=org.id, workspace_id=workspace.id, user_id=user.id, granted_by=user.id),
            ])
            project = Project(
                org_id=org.id, workspace_id=workspace.id, name="Outcome project",
                owner_user_id=user.id,
            )
            other_project = Project(
                org_id=org.id, workspace_id=other_workspace.id, name="Hidden project",
                owner_user_id=user.id,
            )
            db.add_all([project, other_project]); db.flush()
            outcome = ProjectOutcome(
                org_id=org.id, workspace_id=workspace.id, project_id=project.id,
                title="Reduce processing time", problem_statement="Manual work is slow.",
                desired_outcome="Reduce processing time to four minutes.",
                metric_name="Processing time", metric_unit="minutes", direction="decrease",
                baseline_value=10, target_value=4, measurement_method="Measure a 30-day average.",
                acceptance_criteria=["QA checks pass."], owner_user_id=user.id,
            )
            hidden_outcome = ProjectOutcome(
                org_id=org.id, workspace_id=other_workspace.id, project_id=other_project.id,
                title="Hidden outcome", problem_statement="This workspace is not granted.",
                desired_outcome="Keep this record isolated.", metric_name="Count",
                metric_unit="items", direction="increase", target_value=1,
                measurement_method="Count items.", acceptance_criteria=["Count verified."],
                owner_user_id=user.id,
            )
            db.add_all([outcome, hidden_outcome]); db.flush()
            measurement = OutcomeMeasurement(
                org_id=org.id, workspace_id=workspace.id, outcome_id=outcome.id,
                value=3.5, source_type="client_reported",
                source_reference="Client report 2026-11",
                evidence_summary="Client-reported average over the agreed period.",
                created_by=user.id,
            )
            db.add(measurement); db.commit()
            measurement_id = measurement.id

        with App() as db:
            set_rls_context(db, user_id=user.id)
            assert db.query(ProjectOutcome).count() == 1
            assert db.query(OutcomeMeasurement).count() == 1
            row = db.query(OutcomeMeasurement).filter_by(id=measurement_id).one()
            row.value = 8
            with pytest.raises(DBAPIError):
                db.flush()
            db.rollback()

        with App() as db:
            set_rls_context(db, user_id=user.id)
            row = db.query(OutcomeMeasurement).filter_by(id=measurement_id).one()
            db.delete(row)
            with pytest.raises(DBAPIError):
                db.flush()
            db.rollback()
    finally:
        with Admin() as db:
            db.query(OutcomeMeasurement).filter_by(org_id=org.id).delete(synchronize_session=False)
            db.query(ProjectOutcome).filter_by(org_id=org.id).delete(synchronize_session=False)
            db.query(Project).filter_by(org_id=org.id).delete(synchronize_session=False)
            db.query(WorkspaceGrant).filter_by(org_id=org.id).delete(synchronize_session=False)
            db.query(Membership).filter_by(org_id=org.id).delete(synchronize_session=False)
            db.query(Workspace).filter_by(org_id=org.id).delete(synchronize_session=False)
            db.query(Organization).filter_by(id=org.id).delete(synchronize_session=False)
            db.query(User).filter_by(id=user.id).delete(synchronize_session=False)
            db.commit()
        app_engine.dispose()
        admin_engine.dispose()
