"""Artifact metadata must be tenant-scoped before any upload surface exists."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Artifact, Organization, Workspace


def test_artifact_metadata_is_workspace_and_scope_bound():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        org = Organization(name="Org")
        db.add(org)
        db.flush()
        workspace = Workspace(org_id=org.id, name="Workspace")
        db.add(workspace)
        db.flush()
        artifact = Artifact(
            org_id=org.id,
            workspace_id=workspace.id,
            scope_type="workspace",
            scope_id=workspace.id,
            status="initiated",
            classification="synthetic",
            storage_provider="pending",
            object_key=None,
            original_filename="report.pdf",
            media_type="application/pdf",
            byte_size=0,
            sha256=None,
            created_by_principal="user:test",
        )
        db.add(artifact)
        db.commit()
        assert artifact.id
        assert artifact.status == "initiated"
    finally:
        db.close()
        engine.dispose()


def test_artifact_rejects_invalid_lifecycle_and_scope_values():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        org = Organization(name="Org")
        db.add(org)
        db.flush()
        workspace = Workspace(org_id=org.id, name="Workspace")
        db.add(workspace)
        db.flush()
        db.add(Artifact(
            org_id=org.id, workspace_id=workspace.id,
            scope_type="global", scope_id="elsewhere", status="available",
            classification="synthetic", storage_provider="pending",
            original_filename="x", media_type="text/plain", byte_size=1,
            created_by_principal="user:test",
        ))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.close()
        engine.dispose()


def test_artifact_is_in_required_tenant_rls_inventory():
    from app.db import REQUIRED_RLS_TABLES

    assert "artifacts" in REQUIRED_RLS_TABLES
    assert "artifacts" in Base.metadata.tables


def test_artifact_cannot_be_available_without_verified_clean_scan():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        org = Organization(name="Org")
        db.add(org)
        db.flush()
        workspace = Workspace(org_id=org.id, name="Workspace")
        db.add(workspace)
        db.flush()
        db.add(Artifact(
            org_id=org.id, workspace_id=workspace.id,
            scope_type="workspace", scope_id=workspace.id, status="available",
            classification="synthetic", storage_provider="test",
            object_key="opaque/key", original_filename="report.pdf",
            media_type="application/pdf", byte_size=100, sha256="a" * 64,
            created_by_principal="user:test",
        ))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.close()
        engine.dispose()


def test_base_metadata_registers_task_milestone_target_when_models_are_imported():
    assert "milestones" in Base.metadata.tables
    assert "tasks" in Base.metadata.tables
    assert "fk_tasks_milestone_scope" in {
        constraint.name
        for constraint in Base.metadata.tables["tasks"].foreign_key_constraints
    }
