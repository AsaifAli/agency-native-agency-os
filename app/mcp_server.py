"""Agency OS Streamable HTTP MCP transport over the OS-owned Tool Gateway.

The transport exposes only explicitly allowlisted read-only and pending-draft
operations. Service machine bearers are bound to an active path session; agent
session credentials remain execution-bound. Every list/call revalidates OS
identity, session, workspace and tool policy before using the shared gateway.
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from mcp.server import Server, ServerRequestContext
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.db import SessionLocal, set_rls_context
from app.machine_identity import MachinePrincipal, authenticate_machine_token
from app.security_models import AgentSession, MachineIdentity
from app.session_credentials import (
    SessionCredentialContext,
    authenticate_session_credential,
    load_active_session_context,
)
from app.tool_gateway import invoke_registered_tool
from app.tool_gateway_routes import _agent_authorized_tool_data_classes
from app.tool_registry import ToolSpec, get_tool, list_tools

MCP_ALLOWED_TOOL_RISK_LEVELS = frozenset({"read_only", "write_draft"})

_SESSION_PATH_RE = re.compile(r"^/(?P<session_id>[0-9a-fA-F-]{36})/?$")
@dataclass(frozen=True)
class MachineIdentitySessionContext:
    org_id: str
    workspace_id: str
    machine_identity_id: str
    session_id: str
    token_hash: str


MCPAuthContext = SessionCredentialContext | MachineIdentitySessionContext
_CURRENT_SESSION: contextvars.ContextVar[MCPAuthContext | None] = (
    contextvars.ContextVar("agency_os_mcp_session", default=None)
)


def authenticate_machine_session(
    db, authorization: str | None, session_id: str,
) -> MachineIdentitySessionContext:
    """Authenticate a Cowork/Code service bearer against one active OS session path."""
    principal = authenticate_machine_token(authorization, db)
    identity = principal.identity
    if identity.subject_type != "service" or not {
        "sessions:create", "tools:invoke"
    }.issubset(set(identity.scopes or [])):
        raise HTTPException(401, "Invalid machine session credential")
    session = db.query(AgentSession).filter_by(
        id=session_id,
        org_id=identity.org_id,
        workspace_id=identity.workspace_id,
        machine_identity_id=identity.id,
    ).with_for_update().first()
    now = datetime.now(timezone.utc)
    if session is None:
        raise HTTPException(401, "Invalid machine session credential")
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if (
        session.status != "active"
        or expires_at <= now
        or session.data_class not in {"synthetic", "public"}
        or session.data_class not in (identity.allowed_data_classes or [])
    ):
        raise HTTPException(401, "Invalid machine session credential")
    session.last_seen_at = now
    db.commit()
    return MachineIdentitySessionContext(
        org_id=identity.org_id,
        workspace_id=identity.workspace_id,
        machine_identity_id=identity.id,
        session_id=session.id,
        token_hash=identity.token_hash,
    )


def load_mcp_session_context(db, context: MCPAuthContext):
    """Revalidate a session-bound bearer or a service machine bearer on every call."""
    if isinstance(context, SessionCredentialContext):
        return load_active_session_context(db, context)
    set_rls_context(
        db,
        machine_org_id=context.org_id,
        machine_workspace_id=context.workspace_id,
        machine_identity_lookup_id=context.machine_identity_id,
    )
    identity = db.query(MachineIdentity).filter_by(
        id=context.machine_identity_id,
        org_id=context.org_id,
        workspace_id=context.workspace_id,
    ).with_for_update().first()
    session = db.query(AgentSession).filter_by(
        id=context.session_id,
        org_id=context.org_id,
        workspace_id=context.workspace_id,
        machine_identity_id=context.machine_identity_id,
    ).with_for_update().first()
    now = datetime.now(timezone.utc)
    identity_expires_at = identity.expires_at if identity is not None else None
    session_expires_at = session.expires_at if session is not None else None
    if identity_expires_at is not None and identity_expires_at.tzinfo is None:
        identity_expires_at = identity_expires_at.replace(tzinfo=timezone.utc)
    if session_expires_at is not None and session_expires_at.tzinfo is None:
        session_expires_at = session_expires_at.replace(tzinfo=timezone.utc)
    if (
        identity is None or identity.subject_type != "service"
        or identity.token_hash != context.token_hash
        or identity.revoked_at is not None or identity_expires_at <= now
        or not {"sessions:create", "tools:invoke"}.issubset(set(identity.scopes or []))
        or session is None or session.status != "active" or session_expires_at <= now
        or session.data_class not in {"synthetic", "public"}
        or session.data_class not in (identity.allowed_data_classes or [])
    ):
        raise HTTPException(401, "Invalid machine session credential")
    return MachinePrincipal(identity=identity), session


def _uses_agency_mcp_config(config=settings) -> bool:
    return bool(getattr(config, "agency_mcp_enabled", False))


def _configured_tool_keys(config=settings) -> frozenset[str]:
    configured = (
        config.agency_mcp_enabled_tool_keys
        if _uses_agency_mcp_config(config)
        else config.claude_managed_mcp_enabled_tool_keys
    )
    return frozenset(item.strip() for item in configured.split(",") if item.strip())


def _configured_public_base_url(config=settings) -> str:
    return (
        config.agency_mcp_public_base_url
        if _uses_agency_mcp_config(config)
        else config.claude_managed_mcp_public_base_url
    )


def _configured_request_limit(config=settings) -> int:
    return (
        config.agency_mcp_requests_per_minute
        if _uses_agency_mcp_config(config)
        else config.claude_managed_mcp_requests_per_minute
    )


def _configured_concurrency(config=settings) -> int:
    return (
        config.agency_mcp_max_concurrent_requests
        if _uses_agency_mcp_config(config)
        else config.claude_managed_mcp_max_concurrent_requests
    )


def _configured_body_limit(config=settings) -> int:
    return (
        config.agency_mcp_max_request_body_bytes
        if _uses_agency_mcp_config(config)
        else config.claude_managed_mcp_max_request_body_bytes
    )


def _visible_mcp_specs(
    db,
    principal: MachinePrincipal,
    session,
    *,
    enabled_tool_keys: frozenset[str],
) -> list[ToolSpec]:
    identity = principal.identity
    if identity.subject_type not in {"agent", "worker", "service"}:
        return []
    if "tools:invoke" not in (identity.scopes or []):
        return []
    # Agent identities need both machine scopes and a live workforce grant.
    # Founder-provisioned worker/service identities use their explicit machine
    # scopes as the grant; they never inherit another agent's capabilities.
    workforce_grants = (
        (_agent_authorized_tool_data_classes(db, identity) or {})
        if identity.subject_type == "agent"
        else None
    )
    visible: list[ToolSpec] = []
    for spec in list_tools():
        if (
            spec.key not in enabled_tool_keys
            or f"tool:{spec.key}" not in (identity.scopes or [])
            or spec.risk_level not in MCP_ALLOWED_TOOL_RISK_LEVELS
            or spec.requires_approval
        ):
            continue
        eligible_classes = set(identity.allowed_data_classes or []).intersection(
            spec.allowed_data_classes
        )
        if workforce_grants is not None:
            eligible_classes.intersection_update(workforce_grants.get(spec.key, set()))
        if session.data_class not in eligible_classes:
            continue
        visible.append(spec)
    return visible


class SessionPathAuthMiddleware:
    """Bind one path session to one bearer credential and enforce host/origin."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        public_base_url: str,
        session_factory=SessionLocal,
        semaphore: asyncio.Semaphore | None = None,
        requests_per_minute: int = 120,
    ) -> None:
        self.app = app
        parsed = urlparse(public_base_url)
        if (
            parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or parsed.port not in (None, 443)
        ):
            raise ValueError("Agency MCP public URL must be a public HTTPS origin")
        self.origin = f"https://{parsed.netloc}"
        self.hosts = {parsed.netloc.lower(), f"{parsed.hostname.lower()}:443"}
        self.session_factory = session_factory
        self.requests_per_minute = requests_per_minute
        self.semaphore = semaphore or asyncio.Semaphore(
            settings.claude_managed_mcp_max_concurrent_requests
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_path = scope.get("path", "")
        root_path = scope.get("root_path", "")
        # ASGI servers differ in whether a mounted application's scope.path
        # includes root_path. Normalize both valid representations before
        # matching the session UUID; never accept an arbitrary path suffix.
        if root_path and request_path.startswith(root_path):
            request_path = request_path[len(root_path):] or "/"
        match = _SESSION_PATH_RE.fullmatch(request_path)
        if match is None:
            await PlainTextResponse("Not found", status_code=404)(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        if headers.get("host", "").lower() not in self.hosts:
            await PlainTextResponse("Misdirected request", status_code=421)(scope, receive, send)
            return
        origin = headers.get("origin")
        if origin is not None and origin.rstrip("/") != self.origin:
            await PlainTextResponse("Origin not allowed", status_code=403)(scope, receive, send)
            return

        authorization = headers.get("authorization")
        db = self.session_factory()
        try:
            if isinstance(authorization, str) and authorization.startswith("Bearer aos_mi_"):
                context = authenticate_machine_session(
                    db, authorization, match.group("session_id")
                )
            else:
                context = authenticate_session_credential(
                    db, authorization, requests_per_minute=self.requests_per_minute
                )
        except HTTPException as exc:
            db.close()
            await PlainTextResponse(
                "Unauthorized" if exc.status_code != 429 else "Rate limit exceeded",
                status_code=exc.status_code if exc.status_code in (401, 429) else 401,
            )(scope, receive, send)
            return
        except Exception:
            db.rollback()
            db.close()
            await PlainTextResponse("Unauthorized", status_code=401)(scope, receive, send)
            return
        else:
            db.close()

        if context.session_id != match.group("session_id"):
            await PlainTextResponse("Unauthorized", status_code=401)(scope, receive, send)
            return

        token = _CURRENT_SESSION.set(context)
        rewritten_scope = dict(scope)
        rewritten_scope["path"] = "/"
        rewritten_scope["raw_path"] = b"/"
        try:
            async with self.semaphore:
                await self.app(rewritten_scope, receive, send)
        finally:
            _CURRENT_SESSION.reset(token)


def create_mcp_gateway(config=settings, session_factory=SessionLocal):
    """Create the low-level MCP server, its ASGI app and the auth/path wrapper."""
    if not (getattr(config, "agency_mcp_enabled", False) or config.claude_managed_mcp_enabled):
        raise RuntimeError("Agency MCP transport is disabled")
    enabled_tool_keys = _configured_tool_keys(config)
    if not enabled_tool_keys:
        raise RuntimeError("Agency MCP requires an explicit tool allowlist")
    registry = {spec.key: spec for spec in list_tools()}
    unknown = enabled_tool_keys.difference(registry)
    unsafe = {
        key for key in enabled_tool_keys.intersection(registry)
        if registry[key].risk_level not in MCP_ALLOWED_TOOL_RISK_LEVELS
        or registry[key].requires_approval
    }
    if unknown or unsafe:
        raise ValueError("Agency MCP allowlist may contain only registered read-only or pending-draft tools")

    public_base_url = _configured_public_base_url(config)
    parsed = urlparse(public_base_url)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path not in ("", "/") or parsed.port not in (None, 443)
    ):
        raise ValueError("Agency MCP public URL must be a public HTTPS origin")
    origin = f"https://{parsed.netloc}"

    async def list_tools_handler(
        ctx: ServerRequestContext,
        params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        context = _CURRENT_SESSION.get()
        if context is None:
            return ListToolsResult(tools=[])
        with session_factory() as db:
            try:
                principal, session = load_mcp_session_context(db, context)
                specs = _visible_mcp_specs(
                    db, principal, session, enabled_tool_keys=enabled_tool_keys
                )
                return ListToolsResult(tools=[
                    Tool(
                        name=spec.key,
                        description=spec.description,
                        input_schema=spec.input_model.model_json_schema(),
                    )
                    for spec in specs
                ])
            except Exception:
                db.rollback()
                return ListToolsResult(tools=[])

    async def call_tool_handler(
        ctx: ServerRequestContext,
        params: CallToolRequestParams,
    ) -> CallToolResult:
        context = _CURRENT_SESSION.get()
        if context is None:
            return CallToolResult(
                content=[TextContent(type="text", text="Tool invocation denied by OS policy.")],
                is_error=True,
            )
        spec = get_tool(params.name)
        if spec is None or params.name not in enabled_tool_keys:
            return CallToolResult(
                content=[TextContent(type="text", text="Tool invocation denied by OS policy.")],
                is_error=True,
            )
        request_id = ctx.request_id
        if request_id is None:
            return CallToolResult(
                content=[TextContent(type="text", text="Tool invocation denied by OS policy.")],
                is_error=True,
            )
        request_id_text = str(request_id)
        idempotency_key = "mcp_" + hashlib.sha256(
            f"{context.session_id}:{request_id_text}:{spec.key}".encode("utf-8")
        ).hexdigest()
        payload: dict[str, Any] = params.arguments if isinstance(params.arguments, dict) else {}
        with session_factory() as db:
            try:
                principal, session = load_mcp_session_context(db, context)
                visible = _visible_mcp_specs(
                    db, principal, session, enabled_tool_keys=enabled_tool_keys
                )
                if spec.key not in {item.key for item in visible}:
                    raise HTTPException(403, "Tool not available")
                result = invoke_registered_tool(
                    db,
                    principal,
                    session_id=session.id,
                    tool_key=spec.key,
                    payload=payload,
                    idempotency_key=idempotency_key,
                    idempotency_context={"mcp_request_id": request_id_text},
                    allowed_tool_keys={item.key for item in visible},
                    max_calls_per_session=20,
                )
                rendered = json.dumps(result.get("result", {}), ensure_ascii=False, separators=(",", ":"))
                return CallToolResult(
                    content=[TextContent(type="text", text=rendered[:64000])],
                    is_error=False,
                )
            except Exception:
                db.rollback()
                return CallToolResult(
                    content=[TextContent(type="text", text="Tool invocation denied by OS policy.")],
                    is_error=True,
                )

    server = Server(
        "Agency OS",
        version="0.1.0",
        instructions="Only OS-authorized read-only tools and reviewable pending-draft submissions are available for this exact workspace session.",
        on_list_tools=list_tools_handler,
        on_call_tool=call_tool_handler,
    )
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[parsed.hostname, f"{parsed.hostname}:*"],
        allowed_origins=[origin],
    )
    mcp_app = server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        max_request_body_size=_configured_body_limit(config),
        transport_security=transport_security,
    )
    wrapped = SessionPathAuthMiddleware(
        mcp_app,
        public_base_url=public_base_url,
        session_factory=session_factory,
        requests_per_minute=_configured_request_limit(config),
        semaphore=asyncio.Semaphore(_configured_concurrency(config)),
    )
    return server, mcp_app, wrapped
