"""Live PostgreSQL tests for the NOBYPASSRLS worker workspace boundary."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db import set_rls_context, verify_postgres_role
from app.models import Membership, Organization, Role, Task, User, Workspace

ADMIN_URL = os.getenv("AGENCY_OS_TEST_RLS_ADMIN_DATABASE_URL")
WORKER_URL = os.getenv("AGENCY_OS_TEST_RLS_WORKER_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and WORKER_URL),
    reason="Set admin and worker PostgreSQL URLs for live worker RLS tests",
)


def test_worker_is_nobypassrls_and_scoped_to_one_workspace():
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    worker_engine = create_engine(WORKER_URL, pool_size=1, max_overflow=0, pool_pre_ping=True)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    Worker = sessionmaker(bind=worker_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    user = User(email=f"worker-rls-{suffix}@example.test")
    org_a = Organization(name=f"Worker RLS A {suffix}")
    org_b = Organization(name=f"Worker RLS B {suffix}")
    try:
        verify_postgres_role(worker_engine, expected_bypassrls=False, require_rls=True)
        with Admin() as db:
            db.add_all([user, org_a, org_b])
            db.flush()
            ws_a = Workspace(org_id=org_a.id, name="Worker A")
            ws_a_other = Workspace(org_id=org_a.id, name="Worker A other")
            ws_b = Workspace(org_id=org_b.id, name="Worker B")
            db.add_all([ws_a, ws_a_other, ws_b])
            db.flush()
            db.add(Membership(org_id=org_a.id, user_id=user.id, role=Role.owner))
            db.add_all([
                Task(org_id=org_a.id, workspace_id=ws_a.id, title="A visible", created_by=user.id),
                Task(org_id=org_a.id, workspace_id=ws_a_other.id, title="A other hidden", created_by=user.id),
                Task(org_id=org_b.id, workspace_id=ws_b.id, title="B hidden", created_by=user.id),
            ])
            db.commit()

        with Worker() as db:
            scopes = {
                (row.org_id, row.workspace_id)
                for row in db.execute(text(
                    "SELECT org_id, workspace_id FROM agency_os_private.worker_workspace_scopes()"
                )).mappings()
            }
            assert (org_a.id, ws_a.id) in scopes
            assert (org_a.id, ws_a_other.id) in scopes
            assert (org_b.id, ws_b.id) in scopes
            assert db.execute(
                text("SELECT agency_os_private.user_has_org_access(:org_id, :user_id)"),
                {"org_id": org_a.id, "user_id": user.id},
            ).scalar_one() is False
            db.commit()

        with Worker() as db:
            set_rls_context(db, machine_org_id=org_a.id, machine_workspace_id=ws_a.id)
            assert [row.title for row in db.query(Task).all()] == ["A visible"]
            db.commit()

        with Worker() as db:
            assert db.query(Task).count() == 0
            with pytest.raises(DBAPIError):
                db.execute(text("SELECT id FROM public.browser_sessions LIMIT 1"))
            db.rollback()
    finally:
        with Admin() as db:
            db.query(Task).filter(Task.org_id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
            db.query(Membership).filter(Membership.org_id == org_a.id).delete(synchronize_session=False)
            db.query(Workspace).filter(Workspace.org_id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
            db.query(Organization).filter(Organization.id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
            db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
            db.commit()
        worker_engine.dispose()
        admin_engine.dispose()
