"""Live RLS isolation tests; require migrated PG16 and separate admin/app roles."""
import os
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import DBAPIError
from app.db import set_rls_context, verify_postgres_role
from app.models import AuditEvent, FounderAuthority, Membership, Organization, Role, Task, User, Workspace, WorkspaceGrant
from app.security_models import BrowserSession, MachineIdentity

ADMIN_URL = os.getenv("AGENCY_OS_TEST_RLS_ADMIN_DATABASE_URL")
APP_URL = os.getenv("AGENCY_OS_TEST_RLS_DATABASE_URL")
pytestmark = pytest.mark.skipif(not (ADMIN_URL and APP_URL),
    reason="Set AGENCY_OS_TEST_RLS_ADMIN_DATABASE_URL and AGENCY_OS_TEST_RLS_DATABASE_URL for live RLS tests")


def test_postgres_rls_blocks_cross_org_reads_writes_and_pool_context_leaks():
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    app_engine = create_engine(APP_URL, pool_size=1, max_overflow=0, pool_pre_ping=True)
    Admin, App = sessionmaker(bind=admin_engine, expire_on_commit=False), sessionmaker(bind=app_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    org_a, org_b = Organization(name=f"RLS A {suffix}"), Organization(name=f"RLS B {suffix}")
    user_a, user_b = User(email=f"rls-a-{suffix}@example.test"), User(email=f"rls-b-{suffix}@example.test")
    session_hash_a, session_hash_b = f"a{suffix}".ljust(64, "a"), f"b{suffix}".ljust(64, "b")
    try:
        verify_postgres_role(app_engine, expected_bypassrls=False, require_rls=True, expected_role="agency_os_test_app")
        with Admin() as db:
            db.add_all([org_a, org_b, user_a, user_b]); db.flush()
            ws_a = Workspace(org_id=org_a.id, name="Workspace A", created_by=user_a.id)
            ws_a2 = Workspace(org_id=org_a.id, name="Workspace A Other", created_by=user_a.id)
            ws_b = Workspace(org_id=org_b.id, name="Workspace B", created_by=user_b.id)
            db.add_all([ws_a, ws_a2, ws_b]); db.flush()
            db.add_all([
                BrowserSession(user_id=user_a.id, token_hash=session_hash_a,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1)),
                BrowserSession(user_id=user_b.id, token_hash=session_hash_b,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=1)),
                Membership(org_id=org_a.id, user_id=user_a.id, role=Role.owner),
                Membership(org_id=org_b.id, user_id=user_b.id, role=Role.owner),
                WorkspaceGrant(org_id=org_a.id, workspace_id=ws_a.id, user_id=user_a.id, granted_by=user_a.id),
                WorkspaceGrant(org_id=org_b.id, workspace_id=ws_b.id, user_id=user_b.id, granted_by=user_b.id),
                Task(org_id=org_a.id, workspace_id=ws_a.id, title="Tenant A", created_by=user_a.id),
                Task(org_id=org_a.id, workspace_id=ws_a2.id, title="Tenant A Other Workspace", created_by=user_a.id),
                Task(org_id=org_b.id, workspace_id=ws_b.id, title="Tenant B", created_by=user_b.id),
            ]); db.commit()
        with App() as db:
            set_rls_context(db, user_id=user_a.id)
            assert {r.title for r in db.query(Task).all()} == {"Tenant A"}
            assert {r.id for r in db.query(Workspace).all()} == {ws_a.id}
            assert {r.token_hash for r in db.query(BrowserSession).all()} == {session_hash_a}
            db.commit()
        # Revocation must take effect on the next transaction even when the
        # same pooled API connection is reused.
        with Admin() as db:
            grant = db.query(WorkspaceGrant).filter_by(
                org_id=org_a.id, workspace_id=ws_a.id, user_id=user_a.id,
                revoked_at=None,
            ).one()
            grant.revoked_at = datetime.now(timezone.utc)
            db.commit()
        with App() as db:
            set_rls_context(db, user_id=user_a.id)
            assert db.query(Task).count() == 0
            db.commit()
        with Admin() as db:
            grant = db.query(WorkspaceGrant).filter_by(id=grant.id).one()
            grant.revoked_at = None
            db.commit()
        with App() as db:
            set_rls_context(db, browser_session_token_hash=session_hash_b)
            assert {r.token_hash for r in db.query(BrowserSession).all()} == {session_hash_b}
            db.commit()
        with App() as db:
            set_rls_context(db, machine_org_id=org_a.id, machine_workspace_id=ws_a.id)
            assert {r.title for r in db.query(Task).all()} == {"Tenant A"}
            assert {r.id for r in db.query(Workspace).all()} == {ws_a.id}
            db.commit()
        with App() as db:
            assert db.query(Task).count() == 0
            db.commit()
        with App() as db:
            set_rls_context(db, user_id=user_a.id)
            db.add(Task(org_id=org_a.id, workspace_id=ws_a2.id, title="Cross-workspace write", created_by=user_a.id))
            with pytest.raises(DBAPIError):
                db.flush()
            db.rollback()
            db.add(Task(org_id=org_b.id, workspace_id=ws_b.id, title="Cross-org write", created_by=user_a.id))
            with pytest.raises(DBAPIError):
                db.flush()
            db.rollback()
    finally:
        with Admin() as db:
            db.query(BrowserSession).filter(BrowserSession.token_hash.in_([session_hash_a, session_hash_b])).delete(synchronize_session=False)
            db.query(WorkspaceGrant).filter(WorkspaceGrant.org_id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
            db.query(Task).filter(Task.org_id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
            db.query(Membership).filter(Membership.org_id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
            db.query(Workspace).filter(Workspace.org_id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
            db.query(Organization).filter(Organization.id.in_([org_a.id, org_b.id])).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_([user_a.id, user_b.id])).delete(synchronize_session=False)
            db.commit()
        app_engine.dispose(); admin_engine.dispose()



def test_postgres_workspace_grant_functions_require_authority_and_audit_changes():
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    app_engine = create_engine(APP_URL, pool_size=1, max_overflow=0, pool_pre_ping=True)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    App = sessionmaker(bind=app_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    org = Organization(name=f"Grant function org {suffix}")
    founder = User(email=f"grant-founder-{suffix}@example.test")
    member = User(email=f"grant-member-{suffix}@example.test")
    outsider = User(email=f"grant-outsider-{suffix}@example.test")
    try:
        with Admin() as db:
            db.add_all([org, founder, member, outsider])
            db.flush()
            workspace = Workspace(org_id=org.id, name="Grant lifecycle", created_by=founder.id)
            db.add(workspace)
            db.flush()
            db.add_all([
                Membership(org_id=org.id, user_id=founder.id, role=Role.owner),
                Membership(org_id=org.id, user_id=member.id, role=Role.viewer),
                Membership(org_id=org.id, user_id=outsider.id, role=Role.owner),
                FounderAuthority(org_id=org.id, user_id=founder.id, active=True),
                Task(org_id=org.id, workspace_id=workspace.id,
                     title="Grant lifecycle task", created_by=founder.id),
            ])
            db.commit()

        with App() as db:
            set_rls_context(db, user_id=founder.id)
            creator_grant_id = db.execute(
                text("SELECT agency_os_private.grant_workspace_access(:org, :workspace, :target, :actor)"),
                {"org": org.id, "workspace": workspace.id,
                 "target": founder.id, "actor": founder.id},
            ).scalar_one()
            member_grant_id = db.execute(
                text("SELECT agency_os_private.grant_workspace_access(:org, :workspace, :target, :actor)"),
                {"org": org.id, "workspace": workspace.id,
                 "target": member.id, "actor": founder.id},
            ).scalar_one()
            assert creator_grant_id and member_grant_id
            db.commit()

        with App() as db:
            set_rls_context(db, user_id=outsider.id)
            with pytest.raises(DBAPIError):
                db.execute(
                    text("SELECT agency_os_private.grant_workspace_access(:org, :workspace, :target, :actor)"),
                    {"org": org.id, "workspace": workspace.id,
                     "target": outsider.id, "actor": outsider.id},
                )
            db.rollback()

        with App() as db:
            set_rls_context(db, user_id=member.id)
            assert db.query(Task).filter_by(org_id=org.id, workspace_id=workspace.id).count() == 1
            db.commit()

        with App() as db:
            set_rls_context(db, user_id=founder.id)
            assert db.execute(
                text("SELECT agency_os_private.revoke_workspace_access(:org, :workspace, :target, :actor)"),
                {"org": org.id, "workspace": workspace.id,
                 "target": member.id, "actor": founder.id},
            ).scalar_one() is True
            db.commit()

        with App() as db:
            set_rls_context(db, user_id=member.id)
            assert db.query(Task).filter_by(org_id=org.id, workspace_id=workspace.id).count() == 0
            db.commit()

        with Admin() as db:
            events = db.query(AuditEvent).filter(
                AuditEvent.org_id == org.id,
                AuditEvent.event_type.in_([
                    "workspace.access_granted", "workspace.access_revoked",
                ]),
            ).all()
            assert len(events) == 3
            assert {event.event_type for event in events} == {
                "workspace.access_granted", "workspace.access_revoked",
            }
    finally:
        with Admin() as db:
            if org.id:
                # Workspace grant operations append audit events whose actor,
                # organization and workspace references must remain valid.
                # Keep those synthetic parent records in the disposable CI DB.
                db.query(WorkspaceGrant).filter_by(org_id=org.id).delete(synchronize_session=False)
                db.query(Task).filter_by(org_id=org.id).delete(synchronize_session=False)
                db.query(FounderAuthority).filter_by(org_id=org.id).delete(synchronize_session=False)
                db.query(Membership).filter_by(org_id=org.id).delete(synchronize_session=False)
                db.commit()
        app_engine.dispose()
        admin_engine.dispose()


def test_app_runtime_role_cannot_create_objects_in_public_schema():
    engine = create_engine(APP_URL, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            can_create, can_use = connection.execute(text(
                "SELECT has_schema_privilege(current_user, 'public', 'CREATE'), "
                "has_schema_privilege(current_user, 'public', 'USAGE')"
            )).one()
        assert can_create is False
        assert can_use is True
    finally:
        engine.dispose()



def test_machine_identity_lookup_is_id_scoped_before_org_context_is_established():
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    app_engine = create_engine(APP_URL, pool_size=1, max_overflow=0, pool_pre_ping=True)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    App = sessionmaker(bind=app_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    user = User(email=f"machine-lookup-{suffix}@example.test")
    org = Organization(name=f"Machine lookup {suffix}")
    other_org = Organization(name=f"Other machine lookup {suffix}")
    try:
        with Admin() as db:
            db.add_all([user, org, other_org]); db.flush()
            workspace = Workspace(org_id=org.id, name="Machine workspace", created_by=user.id)
            other_workspace = Workspace(org_id=other_org.id, name="Other machine workspace", created_by=user.id)
            db.add_all([workspace, other_workspace]); db.flush()
            identity = MachineIdentity(
                org_id=org.id, workspace_id=workspace.id, name="Scoped identity",
                subject_type="service", subject_id=f"service-{suffix[:28]}",
                token_hash="a" * 64, token_prefix="aos_mi_test",
                scopes=["sessions:create"], allowed_data_classes=["public"],
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                created_by_user_id=user.id,
            )
            other_identity = MachineIdentity(
                org_id=other_org.id, workspace_id=other_workspace.id, name="Other identity",
                subject_type="service", subject_id=f"other-service-{suffix[:24]}",
                token_hash="b" * 64, token_prefix="aos_mi_test",
                scopes=["sessions:create"], allowed_data_classes=["public"],
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                created_by_user_id=user.id,
            )
            db.add_all([identity, other_identity]); db.commit()
            identity_id = identity.id
        with App() as db:
            # This is the first phase of authenticate_machine_token: no org or
            # workspace is trusted until the token digest is verified.
            set_rls_context(db, machine_identity_lookup_id=identity_id)
            assert [row[0] for row in db.query(MachineIdentity.id).all()] == [identity_id]
            db.commit()
    finally:
        with Admin() as db:
            db.query(MachineIdentity).filter(MachineIdentity.org_id.in_([org.id, other_org.id])).delete(synchronize_session=False)
            db.query(Workspace).filter(Workspace.org_id.in_([org.id, other_org.id])).delete(synchronize_session=False)
            db.query(Organization).filter(Organization.id.in_([org.id, other_org.id])).delete(synchronize_session=False)
            db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
            db.commit()
        app_engine.dispose(); admin_engine.dispose()
