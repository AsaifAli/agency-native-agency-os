"""Human workspace authorization regression tests.

These tests intentionally exercise the centralized authorization contract with
real SQLAlchemy/SQLite state. PostgreSQL RLS behavior is covered separately by
the disposable PostgreSQL integration suite.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import Principal, require_workspace_access
from app.db import Base
from app.models import Membership, Organization, Role, User, Workspace, WorkspaceGrant


@pytest.fixture
def workspace_auth_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            User.__table__,
            Membership.__table__,
            Workspace.__table__,
            WorkspaceGrant.__table__,
        ],
    )
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    org = Organization(name="Workspace authorization test")
    outsider_org = Organization(name="Other organization")
    member = User(email="member@example.test", active=True)
    outsider = User(email="outsider@example.test", active=True)
    db.add_all([org, outsider_org, member, outsider])
    db.flush()
    db.add(Membership(org_id=org.id, user_id=member.id, role=Role.viewer))
    workspace_a = Workspace(org_id=org.id, name="Workspace A")
    workspace_b = Workspace(org_id=org.id, name="Workspace B")
    other_workspace = Workspace(org_id=outsider_org.id, name="Other workspace")
    db.add_all([workspace_a, workspace_b, other_workspace])
    db.flush()
    db.add(WorkspaceGrant(
        org_id=org.id, workspace_id=workspace_a.id, user_id=member.id,
        granted_by=member.id,
    ))
    db.commit()
    try:
        yield db, org, member, outsider, workspace_a, workspace_b, other_workspace
    finally:
        db.close()
        engine.dispose()


def test_member_can_access_exactly_the_workspace_granted(workspace_auth_db):
    db, org, member, _, workspace_a, _, _ = workspace_auth_db

    result = require_workspace_access(
        org.id, workspace_a.id, Principal(member), db
    )

    assert result.id == workspace_a.id


def test_org_membership_does_not_grant_access_to_another_workspace(workspace_auth_db):
    db, org, member, _, _, workspace_b, _ = workspace_auth_db

    with pytest.raises(HTTPException) as error:
        require_workspace_access(org.id, workspace_b.id, Principal(member), db)

    assert error.value.status_code == 404


def test_revoked_workspace_grant_does_not_authorize_access(workspace_auth_db):
    db, org, member, _, workspace_a, _, _ = workspace_auth_db
    grant = db.query(WorkspaceGrant).filter_by(
        org_id=org.id, workspace_id=workspace_a.id, user_id=member.id
    ).one()
    from datetime import datetime, timezone
    grant.revoked_at = datetime.now(timezone.utc)
    db.commit()

    with pytest.raises(HTTPException) as error:
        require_workspace_access(org.id, workspace_a.id, Principal(member), db)

    assert error.value.status_code == 404


def test_non_member_cannot_access_workspace_even_with_a_grant_row(workspace_auth_db):
    db, org, _, outsider, workspace_a, _, _ = workspace_auth_db
    # Deliberately create an inconsistent authorization row to prove that
    # membership is independently required by the API contract.
    db.add(WorkspaceGrant(
        org_id=org.id, workspace_id=workspace_a.id, user_id=outsider.id,
        granted_by=outsider.id,
    ))
    db.commit()

    with pytest.raises(HTTPException) as error:
        require_workspace_access(org.id, workspace_a.id, Principal(outsider), db)

    assert error.value.status_code == 404


def test_workspace_from_another_organization_is_not_disclosed(workspace_auth_db):
    db, org, member, _, _, _, other_workspace = workspace_auth_db

    with pytest.raises(HTTPException) as error:
        require_workspace_access(org.id, other_workspace.id, Principal(member), db)

    assert error.value.status_code == 404
