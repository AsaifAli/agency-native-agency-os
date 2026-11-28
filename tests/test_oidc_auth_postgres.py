"""OIDC account linking must establish the PostgreSQL human RLS context."""
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Membership, Organization, Role, User
from app.oidc_auth import link_provisioned_user

ADMIN_URL = os.getenv("AGENCY_OS_TEST_RLS_ADMIN_DATABASE_URL")
APP_URL = os.getenv("AGENCY_OS_TEST_RLS_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL),
    reason="Dedicated migrator and API PostgreSQL URLs are required",
)


def test_oidc_linking_establishes_user_context_before_postgres_membership_rls():
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    app_engine = create_engine(APP_URL, pool_pre_ping=True)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    App = sessionmaker(bind=app_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    issuer = "https://auth.example.test/"
    member = User(email=f"oidc-member-{suffix}@example.test")
    unassigned = User(email=f"oidc-unassigned-{suffix}@example.test")
    org = Organization(name=f"OIDC membership boundary {suffix}")
    try:
        with Admin() as db:
            db.add_all([member, unassigned, org])
            db.flush()
            db.add(Membership(org_id=org.id, user_id=member.id, role=Role.owner))
            db.commit()
            member_id, unassigned_id, org_id = member.id, unassigned.id, org.id

        # No RLS identity is set before OIDC resolution. The verified subject
        # match must set it before the membership query can see its own row.
        with App() as db:
            linked = link_provisioned_user(
                db, issuer, "verified-subject", member.email.lower()
            )
            assert linked.id == member_id
            assert db.info["agency_os_rls_context"]["user_id"] == member_id
            visible_memberships = db.query(Membership.id).filter_by(
                org_id=org_id, user_id=member_id
            ).count()
            assert visible_memberships == 1
            db.commit()

        # A pre-provisioned but unassigned identity must not be linked merely
        # because its email matches a verified OIDC claim.
        with App() as db:
            with pytest.raises(HTTPException) as error:
                link_provisioned_user(
                    db, issuer, "unassigned-subject", unassigned.email.lower()
                )
            assert error.value.status_code == 403
            db.rollback()

        with Admin() as db:
            persisted = db.get(User, member_id)
            rejected = db.get(User, unassigned_id)
            assert persisted.oidc_issuer == issuer
            assert persisted.oidc_subject == "verified-subject"
            assert rejected.oidc_issuer is None
            assert rejected.oidc_subject is None
    finally:
        with Admin() as db:
            db.query(Membership).filter_by(org_id=org.id).delete(synchronize_session=False)
            db.query(Organization).filter_by(id=org.id).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_([member.id, unassigned.id])).delete(synchronize_session=False)
            db.commit()
        admin_engine.dispose()
        app_engine.dispose()

