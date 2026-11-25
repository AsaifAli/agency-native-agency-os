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
        verify_postgres_role(app_engine, expected_bypassrls=False, require_rls=True)
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
                db.query(AuditEvent).filter_by(org_id=org.id).delete(synchronize_session=False)
                db.query(WorkspaceGrant).filter_by(org_id=org.id).delete(synchronize_session=False)
                db.query(Task).filter_by(org_id=org.id).delete(synchronize_session=False)
                db.query(FounderAuthority).filter_by(org_id=org.id).delete(synchronize_session=False)
                db.query(Membership).filter_by(org_id=org.id).delete(synchronize_session=False)
                db.query(Workspace).filter_by(org_id=org.id).delete(synchronize_session=False)
                db.query(Organization).filter_by(id=org.id).delete(synchronize_session=False)
                db.query(User).filter(User.id.in_([founder.id, member.id, outsider.id])).delete(synchronize_session=False)
                db.commit()
        app_engine.dispose()
        admin_engine.dispose()


def test_postgres_machine_identity_lookup_is_exact_and_precedes_workspace_scope():
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    app_engine = create_engine(APP_URL, pool_size=1, max_overflow=0, pool_pre_ping=True)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    App = sessionmaker(bind=app_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    org = Organization(name=f"Machine lookup org {suffix}")
    user = User(email=f"machine-lookup-{suffix}@example.test")
    try:
        with Admin() as db:
            db.add_all([org, user])
            db.flush()
            workspace_a = Workspace(org_id=org.id, name="Machine lookup A", created_by=user.id)
            workspace_b = Workspace(org_id=org.id, name="Machine lookup B", created_by=user.id)
            db.add_all([workspace_a, workspace_b])
            db.flush()
            identity_a = MachineIdentity(
                org_id=org.id, workspace_id=workspace_a.id, name="Identity A",
                subject_type="service", subject_id=user.id,
                token_hash=f"a{suffix}"[:64].ljust(64, "a"), token_prefix="a",
                scopes=[], allowed_data_classes=["synthetic"],
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                created_by_user_id=user.id,
            )
            identity_b = MachineIdentity(
                org_id=org.id, workspace_id=workspace_b.id, name="Identity B",
                subject_type="service", subject_id=user.id,
                token_hash=f"b{suffix}"[:64].ljust(64, "b"), token_prefix="b",
                scopes=[], allowed_data_classes=["synthetic"],
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                created_by_user_id=user.id,
            )
            db.add_all([identity_a, identity_b])
            db.commit()

        with App() as db:
            # Authentication starts with only the opaque identity ID. Org and
            # workspace context are deliberately not known until this lookup.
            set_rls_context(db, machine_identity_lookup_id=identity_a.id)
            visible = db.query(MachineIdentity).all()
            assert [row.id for row in visible] == [identity_a.id]
            db.commit()

            # The lookup-only context must not authorize mutation.
            set_rls_context(db, machine_identity_lookup_id=identity_a.id)
            changed = db.query(MachineIdentity).filter_by(id=identity_a.id).update(
                {"last_used_at": datetime.now(timezone.utc)},
                synchronize_session=False,
            )
            assert changed == 0
            db.rollback()

            # After credential verification, exact machine scope permits only
            # that identity's workspace and normal last-used bookkeeping.
            set_rls_context(
                db, machine_org_id=org.id, machine_workspace_id=workspace_a.id
            )
            assert [row.id for row in db.query(MachineIdentity).all()] == [identity_a.id]
            changed = db.query(MachineIdentity).filter_by(id=identity_a.id).update(
                {"last_used_at": datetime.now(timezone.utc)},
                synchronize_session=False,
            )
            assert changed == 1
            db.commit()
    finally:
        with Admin() as db:
            db.query(MachineIdentity).filter(MachineIdentity.org_id == org.id).delete(synchronize_session=False)
            db.query(Workspace).filter(Workspace.org_id == org.id).delete(synchronize_session=False)
            db.query(Organization).filter(Organization.id == org.id).delete(synchronize_session=False)
            db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
            db.commit()
        app_engine.dispose()
        admin_engine.dispose()
