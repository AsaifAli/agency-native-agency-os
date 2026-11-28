import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import HTTPException

from app.oidc_auth import verified_identity, validate_csrf_pair, link_provisioned_user
from app.db import Base
from app.models import Organization, User, Membership, Role


def test_identity_requires_verified_email_and_subject():
    with pytest.raises(HTTPException) as error:
        verified_identity({"sub": "subject-1", "email": "founder@example.com", "email_verified": False})
    assert error.value.status_code == 401


def test_identity_normalizes_verified_email_and_preserves_subject():
    identity = verified_identity({"sub": "authentik|123", "email": " Founder@Example.com ", "email_verified": True})
    assert identity == ("authentik|123", "founder@example.com")


def test_identity_requires_configured_mfa_assurance_class():
    claims = {"sub": "subject-1", "email": "founder@example.com", "email_verified": True, "acr": "urn:agency-os:aal2"}
    assert verified_identity(claims, "urn:agency-os:aal2")[0] == "subject-1"
    with pytest.raises(HTTPException) as error:
        verified_identity({**claims, "acr": "urn:agency-os:aal1"}, "urn:agency-os:aal2")
    assert error.value.status_code == 403


@pytest.mark.parametrize("claims", [{}, {"sub": "", "email": "founder@example.com", "email_verified": True}, {"sub": "s", "email": "not-an-email", "email_verified": True}])
def test_identity_rejects_missing_or_malformed_claims(claims):
    with pytest.raises(HTTPException):
        verified_identity(claims)


def test_csrf_requires_matching_nonempty_cookie_and_header():
    validate_csrf_pair("random-value", "random-value")


@pytest.mark.parametrize("cookie,header", [(None, "x"), ("x", None), ("x", "y"), ("", "")])
def test_csrf_rejects_missing_or_mismatched_tokens(cookie, header):
    with pytest.raises(HTTPException) as error:
        validate_csrf_pair(cookie, header)
    assert error.value.status_code == 403


@pytest.fixture
def oidc_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[Organization.__table__, User.__table__, Membership.__table__])
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    org = Organization(name="Provisioned Org")
    user = User(email="founder@example.com", display_name="Founder", active=True)
    db.add_all([org, user]); db.flush()
    db.add(Membership(org_id=org.id, user_id=user.id, role=Role.owner)); db.commit()
    try:
        yield db, user.id
    finally:
        db.close(); engine.dispose()


def test_oidc_links_only_preprovisioned_active_member(oidc_db):
    db, user_id = oidc_db
    user = link_provisioned_user(db, "https://auth.example/issuer", "subject-1", "founder@example.com")
    db.commit()
    assert user.id == user_id
    assert user.oidc_issuer == "https://auth.example/issuer"
    assert user.oidc_subject == "subject-1"


def test_oidc_rejects_unprovisioned_user(oidc_db):
    db, _ = oidc_db
    with pytest.raises(HTTPException) as error:
        link_provisioned_user(db, "https://auth.example/issuer", "subject-2", "stranger@example.com")
    assert error.value.status_code == 403


def test_oidc_rejects_conflicting_subject_mapping(oidc_db):
    db, user_id = oidc_db
    user = db.get(User, user_id)
    user.oidc_issuer = "https://auth.example/issuer"
    user.oidc_subject = "already-linked"
    db.commit()
    with pytest.raises(HTTPException) as error:
        link_provisioned_user(db, "https://auth.example/issuer", "different-subject", "founder@example.com")
    assert error.value.status_code == 403


def test_oidc_rejects_email_mismatch_for_existing_subject(oidc_db):
    db, user_id = oidc_db
    user = db.get(User, user_id)
    user.oidc_issuer = "https://auth.example/issuer"
    user.oidc_subject = "subject-3"
    db.commit()
    with pytest.raises(HTTPException) as error:
        link_provisioned_user(db, "https://auth.example/issuer", "subject-3", "changed@example.com")
    assert error.value.status_code == 403


def test_oidc_link_establishes_verified_user_rls_context_before_returning(oidc_db):
    db, user_id = oidc_db
    user = link_provisioned_user(db, "https://auth.example/issuer", "subject-4", "founder@example.com")

    assert user.id == user_id
    assert db.info["agency_os_rls_context"]["user_id"] == user_id


def test_oidc_rejects_existing_subject_without_active_org_membership(oidc_db):
    db, user_id = oidc_db
    user = db.get(User, user_id)
    user.oidc_issuer = "https://auth.example/issuer"
    user.oidc_subject = "subject-without-membership"
    db.query(Membership).filter_by(user_id=user_id).delete()
    db.commit()

    with pytest.raises(HTTPException) as error:
        link_provisioned_user(
            db, "https://auth.example/issuer", "subject-without-membership", "founder@example.com"
        )

    assert error.value.status_code == 403


def test_oidc_does_not_persist_new_identity_link_when_user_has_no_membership(oidc_db):
    db, user_id = oidc_db
    db.query(Membership).filter_by(user_id=user_id).delete()
    db.commit()

    with pytest.raises(HTTPException) as error:
        link_provisioned_user(db, "https://auth.example/issuer", "unattached-subject", "founder@example.com")
    assert error.value.status_code == 403

    db.rollback()
    user = db.get(User, user_id)
    assert user.oidc_issuer is None
    assert user.oidc_subject is None
