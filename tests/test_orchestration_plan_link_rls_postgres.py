"""PostgreSQL tenant isolation and composite scope integrity for plan links."""
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.db import set_rls_context, verify_postgres_role
from app.models import (
    Membership, Organization, Role, Task, User, Workspace, WorkspaceGrant,
)
from app.workforce_models import (
    Delegation, OrchestrationPlan, OrchestrationPlanDelegation, WorkforceMember,
)

ADMIN_URL = os.getenv("AGENCY_OS_TEST_RLS_ADMIN_DATABASE_URL")
APP_URL = os.getenv("AGENCY_OS_TEST_RLS_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL),
    reason="Set PostgreSQL admin and app URLs for live orchestration-link RLS tests",
)


def test_orchestration_plan_links_are_workspace_isolated_and_composite():
    admin_engine = create_engine(ADMIN_URL, pool_pre_ping=True)
    app_engine = create_engine(APP_URL, pool_pre_ping=True)
    Admin = sessionmaker(bind=admin_engine, expire_on_commit=False)
    App = sessionmaker(bind=app_engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex
    org = Organization(name=f"Plan link RLS {suffix}")
    user = User(email=f"plan-link-rls-{suffix}@example.test")

    try:
        verify_postgres_role(
            app_engine,
            expected_bypassrls=False,
            require_rls=True,
            expected_role="agency_os_test_app",
        )

        with Admin() as db:
            db.add_all([org, user])
            db.flush()
            workspace_a = Workspace(
                org_id=org.id, name="Granted plan workspace", created_by=user.id
            )
            workspace_b = Workspace(
                org_id=org.id, name="Un-granted plan workspace", created_by=user.id
            )
            db.add_all([workspace_a, workspace_b])
            db.flush()
            db.add_all([
                Membership(org_id=org.id, user_id=user.id, role=Role.owner),
                WorkspaceGrant(
                    org_id=org.id, workspace_id=workspace_a.id,
                    user_id=user.id, granted_by=user.id,
                ),
            ])

            member_a = WorkforceMember(
                org_id=org.id, workspace_id=workspace_a.id,
                member_type="human", name="Supervisor A", title="Supervisor",
                department_key="operations", responsibilities=[],
                autonomy_level=1, status="active", is_founder_reserved=False,
            )
            member_b = WorkforceMember(
                org_id=org.id, workspace_id=workspace_b.id,
                member_type="human", name="Supervisor B", title="Supervisor",
                department_key="operations", responsibilities=[],
                autonomy_level=1, status="active", is_founder_reserved=False,
            )
            db.add_all([member_a, member_b])
            db.flush()

            root_a = Task(
                org_id=org.id, workspace_id=workspace_a.id,
                title="Plan A root", description="", status="in_progress",
                created_by=user.id,
            )
            child_a = Task(
                org_id=org.id, workspace_id=workspace_a.id,
                title="Plan A child", description="", status="queued",
                created_by=user.id,
            )
            root_b = Task(
                org_id=org.id, workspace_id=workspace_b.id,
                title="Plan B root", description="", status="in_progress",
                created_by=user.id,
            )
            child_b = Task(
                org_id=org.id, workspace_id=workspace_b.id,
                title="Plan B child", description="", status="queued",
                created_by=user.id,
            )
            db.add_all([root_a, child_a, root_b, child_b])
            db.flush()

            plan_a = OrchestrationPlan(
                org_id=org.id, workspace_id=workspace_a.id,
                root_task_id=root_a.id, created_by_member_id=member_a.id,
                objective="Complete workspace A work", plan_title="Plan A",
                status="planned",
            )
            plan_b = OrchestrationPlan(
                org_id=org.id, workspace_id=workspace_b.id,
                root_task_id=root_b.id, created_by_member_id=member_b.id,
                objective="Complete workspace B work", plan_title="Plan B",
                status="planned",
            )
            delegation_a = Delegation(
                org_id=org.id, workspace_id=workspace_a.id,
                parent_task_id=root_a.id, child_task_id=child_a.id,
                delegated_by_member_id=member_a.id,
                assigned_to_member_id=member_a.id,
                review_required=True, review_status="pending", status="ready",
                sequence_no=1,
            )
            delegation_b = Delegation(
                org_id=org.id, workspace_id=workspace_b.id,
                parent_task_id=root_b.id, child_task_id=child_b.id,
                delegated_by_member_id=member_b.id,
                assigned_to_member_id=member_b.id,
                review_required=True, review_status="pending", status="ready",
                sequence_no=1,
            )
            db.add_all([plan_a, plan_b, delegation_a, delegation_b])
            db.flush()
            link_a = OrchestrationPlanDelegation(
                org_id=org.id, workspace_id=workspace_a.id,
                plan_id=plan_a.id, delegation_id=delegation_a.id, ordinal=1,
            )
            link_b = OrchestrationPlanDelegation(
                org_id=org.id, workspace_id=workspace_b.id,
                plan_id=plan_b.id, delegation_id=delegation_b.id, ordinal=1,
            )
            db.add_all([link_a, link_b])
            db.commit()

            plan_a_id = plan_a.id
            delegation_b_id = delegation_b.id
            workspace_a_id = workspace_a.id
            plan_b_id = plan_b.id

        with App() as db:
            set_rls_context(db, user_id=user.id)
            visible = db.query(OrchestrationPlanDelegation).all()
            assert len(visible) == 1
            assert visible[0].plan_id == plan_a_id
            assert visible[0].workspace_id == workspace_a_id

            db.add(OrchestrationPlanDelegation(
                org_id=org.id, workspace_id=workspace_a_id,
                plan_id=plan_a_id, delegation_id=delegation_b_id, ordinal=2,
            ))
            with pytest.raises(DBAPIError):
                db.flush()
            db.rollback()

            set_rls_context(db, user_id=user.id)
            assert db.query(OrchestrationPlanDelegation).count() == 1
            assert db.query(OrchestrationPlanDelegation).filter_by(
                plan_id=plan_b_id
            ).count() == 0

    finally:
        if org.id is not None or user.id is not None:
            with Admin() as db:
                if org.id is not None:
                    db.query(OrchestrationPlanDelegation).filter_by(org_id=org.id).delete(
                        synchronize_session=False
                    )
                    db.query(OrchestrationPlan).filter_by(org_id=org.id).delete(
                        synchronize_session=False
                    )
                    db.query(Delegation).filter_by(org_id=org.id).delete(
                        synchronize_session=False
                    )
                    db.query(Task).filter_by(org_id=org.id).delete(
                        synchronize_session=False
                    )
                    db.query(WorkforceMember).filter_by(org_id=org.id).delete(
                        synchronize_session=False
                    )
                    db.query(WorkspaceGrant).filter_by(org_id=org.id).delete(
                        synchronize_session=False
                    )
                    db.query(Membership).filter_by(org_id=org.id).delete(
                        synchronize_session=False
                    )
                    db.query(Workspace).filter_by(org_id=org.id).delete(
                        synchronize_session=False
                    )
                    db.query(Organization).filter_by(id=org.id).delete(
                        synchronize_session=False
                    )
                if user.id is not None:
                    db.query(User).filter_by(id=user.id).delete(
                        synchronize_session=False
                    )
                db.commit()
        app_engine.dispose()
        admin_engine.dispose()
