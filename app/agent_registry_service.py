"""Workspace-scoped immutable Agent configuration version service."""
import hashlib
import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.audit import record_event
from app.models import Agent, AgentVersion, DataClass


class AgentVersionConflict(ValueError):
    pass


class AgentVersionNotFound(LookupError):
    pass


def validate_runtime_config(runtime: str, runtime_config: dict | None) -> dict:
    if runtime_config is None:
        return {}
    if not isinstance(runtime_config, dict):
        raise ValueError("runtime_config must be an object")
    unknown = set(runtime_config) - {"timeout_seconds"}
    if unknown:
        raise ValueError("runtime_config contains unsupported keys")
    if "timeout_seconds" in runtime_config:
        timeout = runtime_config["timeout_seconds"]
        if (
            runtime != "claude_managed_agents"
            or isinstance(timeout, bool)
            or not isinstance(timeout, int)
            or not 30 <= timeout <= 3600
        ):
            raise ValueError("timeout_seconds must be an integer from 30 to 3600 for Managed Agents")
    return dict(runtime_config)


def _snapshot(
    *,
    name: str,
    department: str,
    instructions: str,
    runtime: str,
    data_class: DataClass,
    runtime_config: dict,
) -> dict:
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError("Agent name must contain 1 to 200 characters")
    if not isinstance(department, str) or not department.strip() or len(department) > 100:
        raise ValueError("Agent department must contain 1 to 100 characters")
    if not isinstance(instructions, str) or len(instructions) > 50000:
        raise ValueError("Agent instructions exceed the permitted size")
    if runtime not in {"claude_managed_agents", "mock"}:
        raise ValueError("Unsupported Agent runtime")
    if not isinstance(data_class, DataClass):
        try:
            data_class = DataClass(data_class)
        except (TypeError, ValueError) as exc:
            raise ValueError("Unsupported Agent data class") from exc
    safe_runtime_config = validate_runtime_config(runtime, runtime_config)
    return {
        "name": name.strip(),
        "department": department.strip(),
        "instructions": instructions,
        "runtime": runtime,
        "data_class": data_class,
        "runtime_config": safe_runtime_config,
    }


def _config_hash(snapshot: dict) -> str:
    canonical = {
        **snapshot,
        "data_class": snapshot["data_class"].value,
    }
    payload = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _version_values(snapshot: dict) -> dict:
    return {
        "name": snapshot["name"],
        "department": snapshot["department"],
        "instructions": snapshot["instructions"],
        "runtime": snapshot["runtime"],
        "data_class": snapshot["data_class"],
        "runtime_config": snapshot["runtime_config"],
        "config_sha256": _config_hash(snapshot),
    }


def _get_agent(db: Session, *, org_id: str, workspace_id: str, agent_id: str, lock: bool = False) -> Agent:
    query = db.query(Agent).filter_by(
        id=agent_id, org_id=org_id, workspace_id=workspace_id,
    )
    if lock:
        query = query.with_for_update()
    agent = query.one_or_none()
    if agent is None:
        raise AgentVersionNotFound("Agent not found")
    return agent


def get_agent_version(
    db: Session, *, org_id: str, workspace_id: str, agent_id: str, version_id: str,
) -> AgentVersion:
    version = db.query(AgentVersion).filter_by(
        id=version_id, org_id=org_id, workspace_id=workspace_id, agent_id=agent_id,
    ).one_or_none()
    if version is None:
        raise AgentVersionNotFound("Agent version not found")
    return version


def list_agent_versions(
    db: Session, *, org_id: str, workspace_id: str, agent_id: str,
) -> list[AgentVersion]:
    _get_agent(db, org_id=org_id, workspace_id=workspace_id, agent_id=agent_id)
    return (
        db.query(AgentVersion)
        .filter_by(org_id=org_id, workspace_id=workspace_id, agent_id=agent_id)
        .order_by(AgentVersion.version_number.desc())
        .all()
    )


def create_agent_version(
    db: Session,
    *,
    org_id: str,
    workspace_id: str,
    agent_id: str,
    name: str,
    department: str,
    instructions: str,
    runtime: str,
    data_class: DataClass,
    runtime_config: dict | None,
    change_reason: str,
    created_by: str,
) -> AgentVersion:
    agent = _get_agent(
        db, org_id=org_id, workspace_id=workspace_id, agent_id=agent_id, lock=True,
    )
    if not isinstance(change_reason, str) or not change_reason.strip() or len(change_reason) > 500:
        raise ValueError("change_reason must contain 1 to 500 characters")
    snapshot = _snapshot(
        name=name,
        department=department,
        instructions=instructions,
        runtime=runtime,
        data_class=data_class,
        runtime_config=runtime_config or {},
    )
    latest = db.query(func.max(AgentVersion.version_number)).filter_by(
        org_id=org_id, workspace_id=workspace_id, agent_id=agent_id,
    ).scalar()
    version = AgentVersion(
        org_id=org_id,
        workspace_id=workspace_id,
        agent_id=agent.id,
        version_number=(latest or 0) + 1,
        **_version_values(snapshot),
        change_reason=change_reason.strip(),
        created_by=created_by,
    )
    db.add(version)
    db.flush()
    record_event(
        db, org_id, created_by, "agent.version.created", "agent_version", version.id,
        workspace_id,
        {
            "agent_id": agent.id,
            "version_number": version.version_number,
            "config_sha256": version.config_sha256,
            "change_reason": version.change_reason,
            "active": False,
        },
    )
    return version


def ensure_initial_agent_version(
    db: Session,
    agent: Agent,
    *,
    created_by: str | None = None,
) -> AgentVersion:
    """Idempotently snapshot legacy Agent fields before first execution."""
    if agent.current_version_id:
        version = db.query(AgentVersion).filter_by(
            id=agent.current_version_id,
            org_id=agent.org_id,
            workspace_id=agent.workspace_id,
            agent_id=agent.id,
        ).one_or_none()
        if version is None:
            raise AgentVersionConflict("Agent active version pointer is invalid")
        if (
            agent.name != version.name
            or agent.department != version.department
            or agent.instructions != version.instructions
            or agent.runtime != version.runtime
            or agent.data_class != version.data_class
        ):
            raise AgentVersionConflict("Agent fields diverge from the active immutable version")
        return version

    existing = db.query(AgentVersion).filter_by(
        org_id=agent.org_id, workspace_id=agent.workspace_id, agent_id=agent.id,
    ).count()
    if existing:
        raise AgentVersionConflict("Agent has version history but no active version pointer")

    snapshot = _snapshot(
        name=agent.name,
        department=agent.department,
        instructions=agent.instructions or "",
        runtime=agent.runtime,
        data_class=agent.data_class,
        runtime_config={},
    )
    version = AgentVersion(
        org_id=agent.org_id,
        workspace_id=agent.workspace_id,
        agent_id=agent.id,
        version_number=1,
        **_version_values(snapshot),
        change_reason="Initial configuration snapshot",
        created_by=created_by,
    )
    db.add(version)
    db.flush()
    agent.current_version_id = version.id
    record_event(
        db, agent.org_id, created_by, "agent.version.created", "agent_version",
        version.id, agent.workspace_id,
        {
            "agent_id": agent.id,
            "version_number": 1,
            "config_sha256": version.config_sha256,
            "change_reason": version.change_reason,
            "active": True,
            "source": "initial_snapshot",
        },
    )
    record_event(
        db, agent.org_id, created_by, "agent.version.activated", "agent",
        agent.id, agent.workspace_id,
        {
            "prior_version_id": None,
            "version_id": version.id,
            "version_number": 1,
            "config_sha256": version.config_sha256,
            "source": "initial_snapshot",
        },
    )
    return version


def activate_agent_version(
    db: Session,
    *,
    org_id: str,
    workspace_id: str,
    agent_id: str,
    version_id: str,
    actor_user_id: str,
    operation: str = "activate",
) -> AgentVersion:
    agent = _get_agent(
        db, org_id=org_id, workspace_id=workspace_id, agent_id=agent_id, lock=True,
    )
    version = get_agent_version(
        db, org_id=org_id, workspace_id=workspace_id,
        agent_id=agent_id, version_id=version_id,
    )
    prior_version_id = agent.current_version_id
    agent.current_version_id = version.id
    agent.name = version.name
    agent.department = version.department
    agent.instructions = version.instructions
    agent.runtime = version.runtime
    agent.data_class = version.data_class
    db.flush()
    record_event(
        db, org_id, actor_user_id, "agent.version.activated", "agent", agent.id,
        workspace_id,
        {
            "operation": operation,
            "prior_version_id": prior_version_id,
            "version_id": version.id,
            "version_number": version.version_number,
            "config_sha256": version.config_sha256,
        },
    )
    return version


def rollback_agent_version(
    db: Session,
    *,
    org_id: str,
    workspace_id: str,
    agent_id: str,
    source_version_id: str,
    actor_user_id: str,
    change_reason: str,
) -> AgentVersion:
    source = get_agent_version(
        db, org_id=org_id, workspace_id=workspace_id,
        agent_id=agent_id, version_id=source_version_id,
    )
    version = create_agent_version(
        db,
        org_id=org_id,
        workspace_id=workspace_id,
        agent_id=agent_id,
        name=source.name,
        department=source.department,
        instructions=source.instructions,
        runtime=source.runtime,
        data_class=source.data_class,
        runtime_config=source.runtime_config or {},
        change_reason=change_reason,
        created_by=actor_user_id,
    )
    activate_agent_version(
        db,
        org_id=org_id,
        workspace_id=workspace_id,
        agent_id=agent_id,
        version_id=version.id,
        actor_user_id=actor_user_id,
        operation="rollback",
    )
    record_event(
        db, org_id, actor_user_id, "agent.version.rolled_back", "agent", agent_id,
        workspace_id,
        {
            "source_version_id": source.id,
            "new_version_id": version.id,
            "version_number": version.version_number,
            "config_sha256": version.config_sha256,
        },
    )
    return version
