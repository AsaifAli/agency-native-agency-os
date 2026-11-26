"""PostgreSQL regression tests for append-only audit event storage."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url

from app.models import AuditEvent, Organization


def test_audit_events_are_append_only_for_application_and_worker_roles():
    admin_url = os.getenv("AGENCY_OS_TEST_DATABASE_URL")
    migrator_url = os.getenv("AGENCY_OS_TEST_MIGRATOR_DATABASE_URL")
    app_url = os.getenv("AGENCY_OS_TEST_RLS_DATABASE_URL")
    worker_url = os.getenv("AGENCY_OS_TEST_RLS_WORKER_DATABASE_URL")
    if not all((admin_url, migrator_url, app_url, worker_url)):
        pytest.skip(
            "Set admin, migrator, app and worker PostgreSQL URLs for audit immutability tests"
        )

    for url in (admin_url, migrator_url, app_url, worker_url):
        parsed = make_url(url)
        assert parsed.get_backend_name() == "postgresql"
        assert parsed.database == "agency_os_worker_test", (
            "Safety check: audit immutability tests may only use agency_os_worker_test"
        )

    admin_engine = create_engine(admin_url, pool_pre_ping=True)
    migrator_engine = create_engine(migrator_url, pool_pre_ping=True)
    app_engine = create_engine(app_url, pool_pre_ping=True)
    worker_engine = create_engine(worker_url, pool_pre_ping=True)
    org_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())

    try:
        with Session(admin_engine) as db:
            db.add(Organization(id=org_id, name="Audit immutability test"))
            db.flush()
            db.add(AuditEvent(
                id=event_id,
                org_id=org_id,
                workspace_id=None,
                actor_user_id=None,
                event_type="test.audit_immutability",
                resource_type="test",
                resource_id=event_id,
                payload={"synthetic": True},
            ))
            db.commit()

        for engine in (app_engine, worker_engine):
            with engine.connect() as connection:
                privileges = connection.execute(text("""
                    SELECT
                        has_table_privilege(current_user, 'public.audit_events', 'UPDATE'),
                        has_table_privilege(current_user, 'public.audit_events', 'DELETE')
                """)).one()
                assert privileges == (False, False)

        # The table owner is not a superuser and must also be unable to rewrite
        # history. The trigger is defense in depth beyond application grants.
        with pytest.raises(DBAPIError):
            with migrator_engine.begin() as connection:
                connection.execute(
                    text("UPDATE public.audit_events SET payload = '{}'::json WHERE id = :id"),
                    {"id": event_id},
                )

        with pytest.raises(DBAPIError):
            with migrator_engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM public.audit_events WHERE id = :id"),
                    {"id": event_id},
                )

        with Session(admin_engine) as db:
            stored = db.query(AuditEvent).filter_by(id=event_id).one()
            assert stored.payload == {"synthetic": True}
    finally:
        # The isolated test bootstrap connection is a PostgreSQL superuser.
        # Production application and worker roles never receive this bypass.
        with admin_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM public.audit_events WHERE id = :id"),
                {"id": event_id},
            )
            connection.execute(
                text("DELETE FROM public.organizations WHERE id = :id"),
                {"id": org_id},
            )
        for engine in (admin_engine, migrator_engine, app_engine, worker_engine):
            engine.dispose()
