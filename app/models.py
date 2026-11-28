import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, DateTime, Boolean, ForeignKey, ForeignKeyConstraint, Text, Enum, JSON,
    UniqueConstraint, Index, CheckConstraint, func, true, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

def uid(): return str(uuid.uuid4())
def now(): return datetime.now(timezone.utc)

class Role(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    operator = "operator"
    reviewer = "reviewer"
    viewer = "viewer"

class DataClass(str, enum.Enum):
    synthetic = "synthetic"
    public = "public"
    commercial = "commercial"
    confidential = "confidential"
    regulated = "regulated"

class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ExecutionStatus(str, enum.Enum):
    queued = "queued"
    claimed = "claimed"
    running = "running"
    retry_wait = "retry_wait"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    paused = "paused"


class ExecutionAttemptStatus(str, enum.Enum):
    queued = "queued"
    claimed = "claimed"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    abandoned = "abandoned"
    paused = "paused"


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("oidc_issuer", "oidc_subject", name="uq_users_oidc_issuer_subject"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    oidc_issuer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)

class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.viewer, nullable=False)


class FounderAuthority(Base):
    """Explicit founder grant, separate from organization membership roles.

    This table is provisioned through the trusted CLI/bootstrap path only; no
    public API grants or escalates founder authority.
    """
    __tablename__ = "founder_authorities"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_founder_authority_org_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    grant_source: Mapped[str] = mapped_column(String(40), default="bootstrap", server_default="cli_provisioning", nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, server_default=func.now(), nullable=False)

class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("org_id", "id", name="uq_workspaces_org_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Artifact(Base):
    """Workspace-owned artifact metadata; bytes live only in private object storage."""
    __tablename__ = "artifacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "workspace_id"],
            ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE",
            name="fk_artifacts_workspace_org",
        ),
        CheckConstraint(
            "scope_type IN ('workspace', 'thread')",
            name="ck_artifacts_scope_type",
        ),
        CheckConstraint(
            "(scope_type = 'workspace' AND scope_id = workspace_id) OR "
            "(scope_type = 'thread' AND length(scope_id) BETWEEN 1 AND 160)",
            name="ck_artifacts_scope_binding",
        ),
        CheckConstraint(
            "status IN ('initiated', 'quarantined', 'scanning', 'available', 'rejected', 'failed', 'deleting', 'deleted')",
            name="ck_artifacts_status",
        ),
        CheckConstraint(
            "classification IN ('synthetic', 'public', 'commercial', 'confidential', 'regulated')",
            name="ck_artifacts_classification",
        ),
        CheckConstraint("byte_size >= 0", name="ck_artifacts_byte_size_nonnegative"),
        CheckConstraint("sha256 IS NULL OR length(sha256) = 64", name="ck_artifacts_sha256_length"),
        CheckConstraint(
            "status NOT IN ('quarantined', 'scanning', 'available') OR object_key IS NOT NULL",
            name="ck_artifacts_storage_key_for_stored_states",
        ),
        CheckConstraint(
            "status != 'available' OR (object_key IS NOT NULL AND sha256 IS NOT NULL "
            "AND byte_size > 0 AND scan_result = 'clean' AND scanner_name IS NOT NULL "
            "AND scanner_version IS NOT NULL)",
            name="ck_artifacts_available_requires_clean_scan",
        ),
        UniqueConstraint("storage_provider", "object_key", name="uq_artifacts_storage_object"),
        Index("ix_artifacts_org_workspace_scope", "org_id", "workspace_id", "scope_type", "scope_id"),
        Index("ix_artifacts_org_workspace_status", "org_id", "workspace_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="initiated", nullable=False)
    classification: Mapped[str] = mapped_column(String(20), default="synthetic", nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    byte_size: Mapped[int] = mapped_column(nullable=False, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_principal: Mapped[str] = mapped_column(String(200), nullable=False)
    scanner_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scanner_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scan_result: Mapped[str | None] = mapped_column(String(40), nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now, nullable=False)


class WorkspaceGrant(Base):
    """Auditable, independently revocable human access to one workspace."""
    __tablename__ = "workspace_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "workspace_id"],
            ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE",
            name="fk_workspace_grants_workspace_org",
        ),
        UniqueConstraint("id", "org_id", "workspace_id", name="uq_workspace_grants_scope_id"),
        Index(
            "uq_workspace_grants_active", "org_id", "workspace_id", "user_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
        Index("ix_workspace_grants_user_active", "user_id", "revoked_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    granted_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("org_id", "workspace_id", "name", name="uq_agent_workspace_name"),
        Index("uq_agent_scope_id", "org_id", "workspace_id", "id", unique=True),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "id", "current_version_id"],
            ["agent_versions.org_id", "agent_versions.workspace_id", "agent_versions.agent_id", "agent_versions.id"],
            ondelete="RESTRICT",
            name="fk_agents_current_version_scope",
            use_alter=True,
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str] = mapped_column(String(100), default="Engineering")
    instructions: Mapped[str] = mapped_column(Text, default="")
    runtime: Mapped[str] = mapped_column(String(80), default="claude_managed_agents")
    data_class: Mapped[DataClass] = mapped_column(Enum(DataClass), default=DataClass.synthetic)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentVersion(Base):
    __tablename__ = "agent_versions"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "workspace_id", "agent_id", "version_number",
            name="uq_agent_version_number",
        ),
        UniqueConstraint(
            "org_id", "workspace_id", "agent_id", "id",
            name="uq_agent_version_scope_id",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "agent_id"],
            ["agents.org_id", "agents.workspace_id", "agents.id"],
            ondelete="RESTRICT",
            name="fk_agent_version_agent_scope",
        ),
        CheckConstraint("version_number >= 1", name="ck_agent_version_number"),
        Index(
            "ix_agent_version_scope_created",
            "org_id", "workspace_id", "agent_id", "created_at",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(String(36), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version_number: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    runtime: Mapped[str] = mapped_column(String(80), nullable=False)
    data_class: Mapped[DataClass] = mapped_column(Enum(DataClass), nullable=False)
    runtime_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("uq_task_scope_id", "org_id", "workspace_id", "id", unique=True),
        Index("ix_task_org_workspace_status", "org_id", "workspace_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="queued")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "idempotency_key",
            name="uq_execution_org_idempotency",
        ),
        CheckConstraint("max_attempts >= 1", name="ck_execution_max_attempts"),
        CheckConstraint("attempt_count >= 0", name="ck_execution_attempt_count"),
        UniqueConstraint(
            "org_id", "workspace_id", "machine_session_id",
            name="uq_execution_machine_session_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "machine_session_id"],
            ["agent_sessions.org_id", "agent_sessions.workspace_id", "agent_sessions.id"],
            ondelete="RESTRICT",
            name="fk_execution_machine_session_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "agent_id", "agent_version_id"],
            ["agent_versions.org_id", "agent_versions.workspace_id", "agent_versions.agent_id", "agent_versions.id"],
            ondelete="RESTRICT",
            name="fk_execution_agent_version_scope",
        ),
        ForeignKeyConstraint(
            ["org_id", "workspace_id", "workforce_member_id"],
            ["workforce_members.org_id", "workforce_members.workspace_id", "workforce_members.id"],
            ondelete="RESTRICT",
            name="fk_execution_workforce_member_scope",
        ),
        Index(
            "ix_execution_org_workspace_status_created",
            "org_id", "workspace_id", "status", "created_at",
        ),
        Index("ix_execution_task_id", "task_id"),
        Index("ix_execution_agent_version_id", "agent_version_id"),
        Index("ix_execution_workforce_member_id", "workforce_member_id"),
        Index(
            "ix_execution_status_retry_queued",
            "status",
            "next_retry_at",
            "queued_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id"), nullable=False
    )
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agents.id"), nullable=False
    )
    agent_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    required_capability_action: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workforce_member_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    requested_by: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(160), nullable=False
    )
    runtime: Mapped[str] = mapped_column(String(80), nullable=False)
    data_class: Mapped[DataClass] = mapped_column(
        Enum(DataClass), nullable=False
    )
    client_authorized: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus), default=ExecutionStatus.queued, nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=3, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    machine_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Only sanitized, allowlisted metadata belongs here.
    # Do not store raw prompts, secrets or unrestricted client payloads.
    request_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now, nullable=False
    )

    @property
    def provider_usage(self) -> dict | None:
        """Expose normalized provider usage without exposing the execution transcript."""
        if not isinstance(self.result, dict):
            return None
        usage = self.result.get("usage")
        return usage if isinstance(usage, dict) else None


class ExecutionAttempt(Base):
    __tablename__ = "execution_attempts"
    __table_args__ = (
        UniqueConstraint(
            "execution_id", "attempt_number",
            name="uq_execution_attempt_number",
        ),
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_execution_attempt_number",
        ),
        Index(
            "ix_execution_attempt_status_lease",
            "status", "lease_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("executions.id"), nullable=False, index=True
    )

    attempt_number: Mapped[int] = mapped_column(nullable=False)
    lease_generation: Mapped[int] = mapped_column(default=1, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(
        String(160), nullable=True
    )
    runtime: Mapped[str] = mapped_column(String(80), nullable=False)

    status: Mapped[ExecutionAttemptStatus] = mapped_column(
        Enum(ExecutionAttemptStatus),
        default=ExecutionAttemptStatus.queued,
        nullable=False,
    )

    external_run_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )

    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, nullable=False
    )


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "idempotency_key",
            name="uq_approval_org_idempotency",
        ),
        UniqueConstraint("org_id", "workspace_id", "id", name="uq_approvals_scope_id"),
        ForeignKeyConstraint(
            ["org_id", "workspace_id"], ["workspaces.org_id", "workspaces.id"],
            ondelete="CASCADE", name="fk_approvals_workspace_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True, nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True, nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.pending
    )
    requested_by: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    decided_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    decision_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consumed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        Index("uq_evaluation_runs_scope_id", "org_id", "workspace_id", "id", unique=True),
        Index("ix_eval_org_workspace_created", "org_id", "workspace_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=False)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    pack_name: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[float] = mapped_column(nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    gate_results: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_trust: Mapped[str] = mapped_column(String(32), default="self_reported", nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

# Register workforce tables before metadata creation so Execution's scoped
# workforce-member foreign key is always resolvable, including test/bootstrap
# processes that import app.models directly.
import app.workforce_models  # noqa: E402,F401
