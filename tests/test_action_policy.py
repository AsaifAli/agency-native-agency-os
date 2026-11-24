import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    Approval,
    ApprovalStatus,
    AuditEvent,
    Organization,
    User,
    Workspace,
    Membership,
    Role,
    FounderAuthority,
)
from app.action_policy import require_approved_action


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    session = TestingSession()

    owner = User(email="policy-owner@test.local")
    reviewer = User(email="policy-reviewer@test.local")
    actor = User(email="policy-actor@test.local")
    org = Organization(name="Policy Test Org")

    session.add_all([owner, reviewer, actor, org])
    session.flush()

    workspace = Workspace(
        id="policy-test-workspace",
        org_id=org.id,
        name="Policy Test Workspace",
    )
    session.add(workspace)
    session.flush()

    session.add_all([
        Membership(org_id=org.id, user_id=owner.id, role=Role.owner),
        Membership(org_id=org.id, user_id=reviewer.id, role=Role.reviewer),
        Membership(org_id=org.id, user_id=actor.id, role=Role.operator),
    ])
    session.add(FounderAuthority(
        org_id=org.id, user_id=reviewer.id, grant_source="test_fixture"
    ))

    approval = Approval(
        org_id=org.id,
        workspace_id=workspace.id,
        action_type="production.release",
        idempotency_key="policy-test-key-001",
        resource_id="release-policy-001",
        request_payload={"reason": "test"},
        status=ApprovalStatus.approved,
        requested_by=owner.id,
        decided_by=reviewer.id,
    )
    session.add(approval)
    session.commit()

    yield session, org, workspace, owner, reviewer, actor, approval

    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def consume(db, approval, org, workspace, actor):
    return require_approved_action(
        db,
        approval_id=approval.id,
        org_id=org.id,
        workspace_id=workspace.id,
        action_type="production.release",
        resource_id="release-policy-001",
        actor_user_id=actor.id,
    )


def test_approved_action_is_consumed_and_audited(db):
    session, org, workspace, owner, reviewer, actor, approval = db

    result = consume(session, approval, org, workspace, actor)

    assert result.id == approval.id
    assert result.consumed_at is not None
    assert result.consumed_by == actor.id

    event = session.query(AuditEvent).filter_by(
        event_type="approval.consumed",
        resource_id=approval.id,
    ).one()

    assert event.actor_user_id == actor.id


def test_consumed_approval_cannot_be_reused(db):
    session, org, workspace, owner, reviewer, actor, approval = db

    consume(session, approval, org, workspace, actor)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        consume(session, approval, org, workspace, actor)

    assert exc.value.status_code == 409


@pytest.mark.parametrize(
    "field,value",
    [
        ("workspace_id", "wrong-workspace"),
        ("action_type", "pricing.change"),
        ("resource_id", "wrong-resource"),
    ],
)
def test_approval_scope_mismatch_is_rejected(db, field, value):
    session, org, workspace, owner, reviewer, actor, approval = db

    kwargs = {
        "approval_id": approval.id,
        "org_id": org.id,
        "workspace_id": workspace.id,
        "action_type": "production.release",
        "resource_id": "release-policy-001",
        "actor_user_id": actor.id,
    }
    kwargs[field] = value

    with pytest.raises(HTTPException) as exc:
        require_approved_action(session, **kwargs)

    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "status",
    [ApprovalStatus.pending, ApprovalStatus.rejected],
)
def test_non_approved_status_is_rejected(db, status):
    session, org, workspace, owner, reviewer, actor, approval = db

    approval.status = status
    session.commit()

    with pytest.raises(HTTPException) as exc:
        consume(session, approval, org, workspace, actor)

    assert exc.value.status_code == 409


def test_self_approved_record_is_rejected(db):
    session, org, workspace, owner, reviewer, actor, approval = db

    approval.decided_by = approval.requested_by
    session.commit()

    with pytest.raises(HTTPException) as exc:
        consume(session, approval, org, workspace, actor)

    assert exc.value.status_code == 403


def test_rollback_restores_approval_consumption(db):
    session, org, workspace, owner, reviewer, actor, approval = db

    consume(session, approval, org, workspace, actor)
    session.rollback()

    session.expire_all()
    restored = session.get(Approval, approval.id)

    assert restored.consumed_at is None
    assert restored.consumed_by is None

    audit_count = session.query(AuditEvent).filter_by(
        event_type="approval.consumed",
        resource_id=approval.id,
    ).count()

    assert audit_count == 0


def test_founder_may_approve_own_initiated_action(db):
    session, org, workspace, owner, founder, actor, approval = db
    approval.requested_by = founder.id
    approval.decided_by = founder.id
    session.commit()

    result = consume(session, approval, org, workspace, actor)
    assert result.consumed_at is not None


def test_approval_from_revoked_founder_is_not_consumable(db):
    session, org, workspace, owner, founder, actor, approval = db
    grant = session.query(FounderAuthority).filter_by(
        org_id=org.id, user_id=founder.id
    ).one()
    grant.active = False
    session.commit()

    with pytest.raises(HTTPException) as exc:
        consume(session, approval, org, workspace, actor)

    assert exc.value.status_code == 403
