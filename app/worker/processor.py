import json
import threading

from app.audit import record_event
from app.data_protection import DataProtectionBlocked, protect_execution_request, protect_execution_result
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import WorkerSessionLocal, scoped_worker_capability_session_factory
from app.integrations.runtime import (
    ExecutionRequest,
    ExecutionResult,
    RuntimeExecutionError,
    RuntimeManualReviewRequired,
    RuntimeCancelled,
    RuntimePaused,
    RuntimeNotConfiguredError,
    RuntimeTransientError,
)
from app.worker.runtime_factory import get_runtime
from app.worker.tool_executor import build_machine_mcp_session_preparer, build_machine_tool_executor
from app.execution_controls import (
    acknowledge_execution_cancel,
    get_execution_control_request,
)
from app.worker_service import (
    LeaseExpired,
    claim_next_execution,
    complete_execution,
    fail_execution,
    heartbeat_execution,
    start_execution,
    attach_external_run_id,
    claim_worker_execution_capability,
)
SessionFactory = Callable[[], Session]

MAX_RUNTIME_PROVIDER_LENGTH = 80
MAX_RUNTIME_RUN_ID_LENGTH = 200
MAX_RUNTIME_DETAIL_LENGTH = 16000
MAX_RUNTIME_RESULT_BYTES = 32768

class HeartbeatRenewalError(Exception):
    """Raised when the worker cannot confirm lease renewal."""

class HeartbeatShutdownError(Exception):
    """Raised when a heartbeat thread cannot stop within its deadline."""

@dataclass
class LeaseHeartbeat:
    session_factory: SessionFactory
    execution_id: str
    attempt_id: str
    worker_id: str
    lease_seconds: int
    interval_seconds: float | None = None

    _stop_event: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)
    _error: Exception | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not 15 <= self.lease_seconds <= 3600:
            raise ValueError("lease_seconds must be between 15 and 3600")
        if self.interval_seconds is None:
            self.interval_seconds = self.lease_seconds / 3
        if not 0 < self.interval_seconds < self.lease_seconds:
            raise ValueError("Heartbeat interval must be shorter than the lease")

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"lease-heartbeat-{self.attempt_id}", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            try:
                with self.session_factory() as db:
                    heartbeat_execution(
                        db, execution_id=self.execution_id, attempt_id=self.attempt_id,
                        worker_id=self.worker_id, lease_seconds=self.lease_seconds,
                    )
                    if db.get_bind().dialect.name == "postgresql":
                        renewed = db.execute(text(
                            "SELECT agency_os_private.renew_worker_execution_capability()"
                        )).scalar_one()
                        if renewed is not True:
                            raise LeaseExpired("Worker capability could not be renewed")
                    db.commit()
            except Exception as exc:
                self._error = exc
                self._stop_event.set()
                return

    def assert_healthy(self) -> None:
        if self._error is None:
            return
        if isinstance(self._error, LeaseExpired):
            raise LeaseExpired("Worker execution lease is no longer valid.") from self._error
        raise HeartbeatRenewalError(
            "Worker could not confirm execution lease renewal."
        ) from self._error

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is None:
            return
        self._thread.join(timeout=settings.worker_heartbeat_shutdown_timeout_seconds)
        if self._thread.is_alive():
            raise HeartbeatShutdownError(
                "Heartbeat thread did not stop within its shutdown deadline. "
                "Worker process termination is required."
            )

def _record_failure(
    session_factory: SessionFactory, *, execution_id: str, attempt_id: str,
    worker_id: str, error_code: str, error_message: str, retryable: bool,
    provider_usage: dict | None = None,
) -> None:
    """Persist a sanitized failure in its own transaction."""
    with session_factory() as db:
        fail_execution(
            db, execution_id=execution_id, attempt_id=attempt_id, worker_id=worker_id,
            error_code=error_code, error_message=error_message, retryable=retryable,
            provider_usage=provider_usage,
        )
        db.commit()

def _serialize_result(result: ExecutionResult) -> dict:
    """Validate and serialize bounded, structured runtime output."""
    if not isinstance(result, ExecutionResult):
        raise ValueError("Runtime returned an invalid result type")
    if not isinstance(result.status, str):
        raise ValueError("Runtime returned an invalid status")
    if result.status != "succeeded":
        raise RuntimeExecutionError("Runtime did not report a successful execution.")
    if (
        not isinstance(result.provider, str) or not result.provider.strip()
        or len(result.provider) > MAX_RUNTIME_PROVIDER_LENGTH
    ):
        raise ValueError("Runtime returned an invalid provider")
    if result.external_run_id is not None and (
        not isinstance(result.external_run_id, str)
        or not result.external_run_id.strip()
        or len(result.external_run_id) > MAX_RUNTIME_RUN_ID_LENGTH
    ):
        raise ValueError("Runtime returned an invalid external run ID")
    if not isinstance(result.detail, str) or len(result.detail) > MAX_RUNTIME_DETAIL_LENGTH:
        raise ValueError("Runtime returned invalid detail")
    payload = {
        "provider": result.provider, "external_run_id": result.external_run_id,
        "status": "succeeded", "detail": result.detail,
    }
    if result.usage is not None:
        payload["usage"] = result.usage
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(serialized) > MAX_RUNTIME_RESULT_BYTES:
        raise ValueError("Runtime result exceeds the permitted size")
    return payload

def _record_data_protection_failure(
    session_factory: SessionFactory, *, execution_id: str, attempt_id: str,
    worker_id: str, org_id: str, workspace_id: str, reason_code: str,
    event_type: str,
) -> None:
    """Persist the policy block and failed attempt atomically; never send raw data."""
    try:
        with session_factory() as db:
            record_event(
                db, org_id, None, event_type, "execution", execution_id,
                workspace_id, {"reason_code": reason_code},
            )
            fail_execution(
                db, execution_id=execution_id, attempt_id=attempt_id,
                worker_id=worker_id, error_code="DATA_PROTECTION_BLOCKED",
                error_message="Execution blocked by data-protection policy.",
                retryable=False,
            )
            db.commit()
    except Exception:
        _record_failure(
            session_factory, execution_id=execution_id, attempt_id=attempt_id,
            worker_id=worker_id, error_code="DATA_PROTECTION_AUDIT_FAILED",
            error_message="Data-protection audit could not be persisted; provider execution was blocked.",
            retryable=True,
        )


def process_one_execution(
    *, worker_id: str, lease_seconds: int = 60,
    heartbeat_interval_seconds: float | None = None,
    session_factory: SessionFactory = WorkerSessionLocal,
) -> str | None:
    """Claim and process one execution; provider work runs outside DB transactions."""
    with session_factory() as db:
        if db.get_bind().dialect.name == "postgresql":
            capability = claim_worker_execution_capability(
                db, worker_id=worker_id, lease_seconds=lease_seconds,
            )
            if capability is None:
                return None
            execution_id, attempt_id = capability.execution_id, capability.attempt_id
            db.commit()
            # Every subsequent transaction re-establishes the database-verified
            # capability. No tenant GUC or workspace inventory authorizes reads.
            session_factory = scoped_worker_capability_session_factory(
                capability, session_factory,
            )
            from app.models import Execution, ExecutionAttempt
            with session_factory() as scoped_db:
                execution = scoped_db.query(Execution).filter_by(id=execution_id).one()
                attempt = scoped_db.query(ExecutionAttempt).filter_by(
                    id=attempt_id, execution_id=execution_id,
                ).one()
                attempt_number = attempt.attempt_number
                scoped_db.commit()
        else:
            claimed = claim_next_execution(
                db, worker_id=worker_id, lease_seconds=lease_seconds,
            )
            if claimed is None:
                return None
            execution, attempt = claimed
            execution_id, attempt_id = execution.id, attempt.id
            attempt_number = attempt.attempt_number
            db.commit()

    with session_factory() as db:
        execution, _ = start_execution(
            db, execution_id=execution_id, attempt_id=attempt_id,
            worker_id=worker_id, lease_seconds=lease_seconds,
        )
        from app.models import Agent, AgentVersion, ExecutionAttempt, Task
        agent = db.query(Agent).filter_by(
            id=execution.agent_id, org_id=execution.org_id,
            workspace_id=execution.workspace_id,
        ).one()
        agent_version = None
        if execution.agent_version_id:
            agent_version = db.query(AgentVersion).filter_by(
                id=execution.agent_version_id,
                org_id=execution.org_id,
                workspace_id=execution.workspace_id,
                agent_id=execution.agent_id,
            ).one_or_none()
            if (
                agent_version is None
                or agent_version.runtime != execution.runtime
                or agent_version.data_class != execution.data_class
            ):
                fail_execution(
                    db,
                    execution_id=execution.id,
                    attempt_id=attempt.id,
                    worker_id=worker_id,
                    error_code="AGENT_VERSION_UNAVAILABLE",
                    error_message="Pinned agent configuration is unavailable or inconsistent.",
                    retryable=False,
                )
                db.commit()
                return execution.id
        task = db.query(Task).filter_by(
            id=execution.task_id, org_id=execution.org_id,
            workspace_id=execution.workspace_id,
        ).one()
        prior_attempt = (
            db.query(ExecutionAttempt)
            .filter(
                ExecutionAttempt.execution_id == execution.id,
                ExecutionAttempt.runtime == execution.runtime,
                ExecutionAttempt.external_run_id.is_not(None),
            )
            .order_by(ExecutionAttempt.attempt_number.desc())
            .first()
        )

        def persist_provider_run(external_run_id: str) -> None:
            with session_factory() as callback_db:
                attach_external_run_id(
                    callback_db, execution_id=execution_id, attempt_id=attempt_id,
                    worker_id=worker_id, external_run_id=external_run_id,
                )
                callback_db.commit()

        request = ExecutionRequest(
            org_id=execution.org_id, workspace_id=execution.workspace_id,
            task_id=execution.task_id, agent_id=execution.agent_id,
            data_class=execution.data_class, execution_id=execution.id,
            client_authorized=execution.client_authorized,
            agent_name=agent_version.name if agent_version else agent.name,
            agent_department=agent_version.department if agent_version else agent.department,
            agent_instructions=agent_version.instructions if agent_version else agent.instructions,
            runtime_config=(agent_version.runtime_config or {}) if agent_version else {},
            task_title=task.title,
            task_description=task.description,
            external_run_id=prior_attempt.external_run_id if prior_attempt else None,
            attempt_number=attempt_number,
            persist_external_run_id=persist_provider_run,
            request_metadata=execution.request_metadata or {},
        )

        def persist_resume_event(resume_token: str, provider_event_id: str) -> None:
            from app.execution_controls import persist_execution_resume_event
            with session_factory() as callback_db:
                persist_execution_resume_event(
                    callback_db, execution_id=execution_id, attempt_id=attempt_id,
                    worker_id=worker_id, resume_token=resume_token,
                    provider_event_id=provider_event_id,
                )
                callback_db.commit()

        def persist_control_event(action: str, provider_event_id: str) -> None:
            from app.execution_controls import persist_execution_control_event
            with session_factory() as callback_db:
                persist_execution_control_event(
                    callback_db, execution_id=execution_id, attempt_id=attempt_id,
                    worker_id=worker_id, action=action,
                    provider_event_id=provider_event_id,
                )
                callback_db.commit()

        def check_execution_control() -> str | None:
            with session_factory() as control_db:
                return get_execution_control_request(
                    control_db,
                    execution_id=execution_id,
                    attempt_id=attempt_id,
                    worker_id=worker_id,
                )

        request.control_check = check_execution_control
        request.persist_resume_event = persist_resume_event
        request.persist_control_event = persist_control_event
        runtime_name = execution.runtime
        execution_org_id = execution.org_id
        execution_workspace_id = execution.workspace_id
        execution_data_class = execution.data_class
        db.commit()

    try:
        request, protection_report = protect_execution_request(request)
    except DataProtectionBlocked as exc:
        _record_data_protection_failure(
            session_factory, execution_id=execution_id, attempt_id=attempt_id,
            worker_id=worker_id, org_id=execution_org_id,
            workspace_id=execution_workspace_id, reason_code=exc.code,
            event_type="execution.data_protection_blocked",
        )
        return execution_id

    if protection_report.total_redactions:
        try:
            with session_factory() as protection_db:
                record_event(
                    protection_db, execution_org_id, None,
                    "execution.data_redacted", "execution", execution_id,
                    execution_workspace_id,
                    {
                        "redaction_counts": protection_report.redaction_counts,
                        "data_class": execution_data_class.value,
                    },
                )
                protection_db.commit()
        except Exception:
            _record_failure(
                session_factory, execution_id=execution_id, attempt_id=attempt_id,
                worker_id=worker_id, error_code="DATA_PROTECTION_AUDIT_FAILED",
                error_message="Data-protection audit could not be persisted; provider execution was blocked.",
                retryable=True,
            )
            return execution_id

    heartbeat = LeaseHeartbeat(
        session_factory=session_factory, execution_id=execution_id,
        attempt_id=attempt_id, worker_id=worker_id, lease_seconds=lease_seconds,
        interval_seconds=heartbeat_interval_seconds,
    )
    heartbeat.start()
    runtime_error: tuple[str, str, bool] | None = None
    runtime_failure_usage: dict | None = None
    serialized_result: dict | None = None
    cancellation_requested = False
    pause_requested = False
    data_protection_block_code: str | None = None
    try:
        runtime = get_runtime(runtime_name)
        # A retry resumes the previous provider session. Persist that same
        # correlation ID onto the new attempt before provider work so usage
        # aggregation treats cumulative snapshots as one session, not deltas.
        if request.external_run_id:
            persist_provider_run(request.external_run_id)
        if runtime_name == "claude_managed_agents":
            request.execute_custom_tool = build_machine_tool_executor(
                session_factory=session_factory,
                request=request,
                execution_id=execution_id,
                attempt_id=attempt_id,
                worker_id=worker_id,
                session_ttl_seconds=settings.claude_managed_timeout_seconds,
            )
            if settings.claude_managed_mcp_enabled:
                request.prepare_mcp_session = build_machine_mcp_session_preparer(
                    session_factory=session_factory,
                    request=request,
                    execution_id=execution_id,
                    attempt_id=attempt_id,
                    worker_id=worker_id,
                    session_ttl_seconds=min(settings.claude_managed_timeout_seconds, 3600),
                    provider_vault_id=settings.claude_managed_mcp_vault_id,
                    max_active_vault_credentials=settings.claude_managed_mcp_max_active_credentials,
                )
                from app.session_credentials import (
                    load_provider_credential_info,
                    mark_provider_credential_archived,
                    persist_provider_credential,
                    revoke_session_credential,
                )

                def get_mcp_provider_credential() -> dict | None:
                    with session_factory() as callback_db:
                        return load_provider_credential_info(
                            callback_db, execution_id=execution_id
                        )

                def persist_mcp_provider_credential(credential_id: str, vault_id: str, provider_id: str) -> None:
                    with session_factory() as callback_db:
                        persist_provider_credential(
                            callback_db, credential_id=credential_id, vault_id=vault_id,
                            provider_credential_id=provider_id, org_id=execution_org_id,
                            workspace_id=execution_workspace_id,
                        )

                def revoke_mcp_session_credential(credential_id: str, reason: str) -> None:
                    with session_factory() as callback_db:
                        revoke_session_credential(
                            callback_db, credential_id=credential_id, reason=reason,
                            org_id=execution_org_id, workspace_id=execution_workspace_id,
                        )

                def mark_mcp_provider_credential_archived(credential_id: str, provider_id: str) -> None:
                    with session_factory() as callback_db:
                        mark_provider_credential_archived(
                            callback_db, credential_id=credential_id,
                            provider_credential_id=provider_id, org_id=execution_org_id,
                            workspace_id=execution_workspace_id,
                        )

                request.prepare_mcp_session = build_machine_mcp_session_preparer(
                    session_factory=session_factory,
                    request=request,
                    execution_id=execution_id,
                    attempt_id=attempt_id,
                    worker_id=worker_id,
                    session_ttl_seconds=min(settings.claude_managed_timeout_seconds, 3600),
                )
                request.get_mcp_provider_credential = get_mcp_provider_credential
                request.persist_mcp_provider_credential = persist_mcp_provider_credential
                request.revoke_mcp_session_credential = revoke_mcp_session_credential
                request.mark_mcp_provider_credential_archived = mark_mcp_provider_credential_archived

                def revoke_terminal_mcp_credential(reason: str) -> None:
                    if request.get_mcp_provider_credential is None:
                        return
                    info = request.get_mcp_provider_credential()
                    if isinstance(info, dict) and isinstance(info.get("credential_id"), str):
                        request.revoke_mcp_session_credential(info["credential_id"], reason)
        runtime_result = runtime.start(request)
        if request.control_check is not None and request.control_check() == "cancel":
            raise RuntimeCancelled("OS cancellation request observed after provider return.")
        runtime_result, output_protection = protect_execution_result(runtime_result)
        if output_protection.total_redactions:
            try:
                with session_factory() as audit_db:
                    record_event(
                        audit_db, execution_org_id, None,
                        "execution.output_redacted", "execution", execution_id,
                        execution_workspace_id,
                        {
                            "redaction_counts": output_protection.redaction_counts,
                            "data_class": execution_data_class.value,
                        },
                    )
                    audit_db.commit()
            except Exception:
                runtime_error = (
                    "DATA_PROTECTION_AUDIT_FAILED",
                    "Data-protection audit could not be persisted; provider output was discarded.",
                    False,
                )
        if runtime_error is None:
            serialized_result = _serialize_result(runtime_result)
    except DataProtectionBlocked as exc:
        if settings.claude_managed_mcp_enabled and "revoke_terminal_mcp_credential" in locals():
            revoke_terminal_mcp_credential("MCP_EXECUTION_DATA_PROTECTION_BLOCKED")
        data_protection_block_code = exc.code
        runtime_error = (
            "DATA_PROTECTION_BLOCKED",
            "Runtime output blocked by data-protection policy.",
            False,
        )
    except RuntimeNotConfiguredError:
        if settings.claude_managed_mcp_enabled and "revoke_terminal_mcp_credential" in locals():
            revoke_terminal_mcp_credential("MCP_RUNTIME_NOT_CONFIGURED")
        runtime_error = (
            "RUNTIME_NOT_CONFIGURED", "The requested runtime is unavailable.", False,
        )
    except RuntimeManualReviewRequired as exc:
        if isinstance(exc.usage, dict):
            runtime_failure_usage = exc.usage
        runtime_error = (
            "RUNTIME_REQUIRES_REVIEW",
            "The runtime requires human review before this execution can be treated as complete.",
            False,
        )
    except RuntimeCancelled:
        if settings.claude_managed_mcp_enabled and "revoke_terminal_mcp_credential" in locals():
            revoke_terminal_mcp_credential("MCP_EXECUTION_CANCELLED")
        cancellation_requested = True
    except RuntimePaused:
        pause_requested = True
    except RuntimeTransientError:
        runtime_error = (
            "RUNTIME_TRANSIENT_ERROR",
            "The runtime provider or network is temporarily unavailable.", True,
        )
    except RuntimeExecutionError:
        if settings.claude_managed_mcp_enabled and "revoke_terminal_mcp_credential" in locals():
            revoke_terminal_mcp_credential("MCP_RUNTIME_UNSUCCESSFUL")
        runtime_error = (
            "RUNTIME_UNSUCCESSFUL",
            "The runtime did not complete successfully.", True,
        )
    except Exception:
        runtime_error = (
            "RUNTIME_ERROR", "The runtime encountered an execution error.", True,
        )
    finally:
        heartbeat.stop()

    if data_protection_block_code is not None:
        _record_data_protection_failure(
            session_factory, execution_id=execution_id, attempt_id=attempt_id,
            worker_id=worker_id, org_id=execution_org_id,
            workspace_id=execution_workspace_id,
            reason_code=data_protection_block_code,
            event_type="execution.output_protection_blocked",
        )
        return execution_id

    heartbeat.assert_healthy()
    if pause_requested:
        from app.execution_controls import acknowledge_execution_pause
        with session_factory() as pause_db:
            current_control = get_execution_control_request(
                pause_db, execution_id=execution_id, attempt_id=attempt_id,
                worker_id=worker_id,
            )
            if current_control == "cancel":
                acknowledge_execution_cancel(
                    pause_db, execution_id=execution_id, attempt_id=attempt_id,
                    worker_id=worker_id,
                )
            else:
                acknowledge_execution_pause(
                    pause_db, execution_id=execution_id, attempt_id=attempt_id,
                    worker_id=worker_id,
                )
            pause_db.commit()
        return execution_id

    if cancellation_requested:
        with session_factory() as cancel_db:
            acknowledge_execution_cancel(
                cancel_db,
                execution_id=execution_id,
                attempt_id=attempt_id,
                worker_id=worker_id,
            )
            cancel_db.commit()
        return execution_id

    if runtime_error is not None:
        error_code, error_message, retryable = runtime_error
        _record_failure(
            session_factory, execution_id=execution_id, attempt_id=attempt_id,
            worker_id=worker_id, error_code=error_code,
            error_message=error_message, retryable=retryable,
            provider_usage=runtime_failure_usage,
        )
        return execution_id

    with session_factory() as db:
        heartbeat.assert_healthy()
        if get_execution_control_request(
            db,
            execution_id=execution_id,
            attempt_id=attempt_id,
            worker_id=worker_id,
        ) == "cancel":
            acknowledge_execution_cancel(
                db,
                execution_id=execution_id,
                attempt_id=attempt_id,
                worker_id=worker_id,
            )
            db.commit()
            return execution_id
        complete_execution(
            db, execution_id=execution_id, attempt_id=attempt_id,
            worker_id=worker_id, result=serialized_result,
        )
        db.commit()
    return execution_id
