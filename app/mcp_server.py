"""Claude Managed Agents MCP transport over the OS-owned Tool Gateway.

The transport is intentionally read-only in its first release. Authentication is
session-scoped; every tool call revalidates the OS credential and then delegates
to the same registered-tool authorization and persistence path as HTTP callers.
"""
from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import re
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
from app.db import SessionLocal
from app.machine_identity import MachinePrincipal
from app.session_credentials import (
    SessionCredentialContext,
    authenticate_session_credential,
    load_active_session_context,
)
from app.tool_gateway import invoke_registered_tool
from app.tool_gateway_routes import _agent_authorized_tool_data_classes
from app.tool_registry import ToolSpec, get_tool, list_tools

_SESSION_PATH_RE = re.compile(r"^/(?P<session_id>[0-9a-fA-F-]{36})/?$")
_CURRENT_SESSION: contextvars.ContextVar[SessionCredentialContext | None] = (
    contextvars.ContextVar("agency_os_mcp_session", default=None)
)


def _configured_tool_keys(config=settings) -> frozenset[str]:
    return frozenset(
        item.strip()
        for item in config.claude_managed_mcp_enabled_tool_keys.split(",")
        if item.strip()
    )


def _visible_read_only_specs(
    db,
    principal: MachinePrincipal,
    session,
    *,
    enabled_tool_keys: frozenset[str],
) -> list[ToolSpec]:
    identity = principal.identity
    if identity.subject_type != "agent":
        return []
    if "tools:invoke" not in (identity.scopes or []):
        return []
    workforce_grants = _agent_authorized_tool_data_classes(db, identity) or {}
    visible: list[ToolSpec] = []
    for spec in list_tools():
        if (
            spec.key not in enabled_tool_keys
            or f"tool:{spec.key}" not in (identity.scopes or [])
            or spec.risk_level != "read_only"
            or spec.requires_approval
        ):
            continue
        eligible_classes = (
            set(identity.allowed_data_classes or [])
            .intersection(spec.allowed_data_classes)
            .intersection(workforce_grants.get(spec.key, set()))
        )
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
            raise ValueError("Claude MCP public URL must be a public HTTPS origin")
        self.origin = f"https://{parsed.netloc}"
        self.host = parsed.netloc.lower()
        self.session_factory = session_factory
        self.requests_per_minute = requests_per_minute
        self.semaphore = semaphore or asyncio.Semaphore(
            settings.claude_managed_mcp_max_concurrent_requests
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        match = _SESSION_PATH_RE.fullmatch(scope.get("path", ""))
        if match is None:
            await PlainTextResponse("Not found", status_code=404)(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        if headers.get("host", "").lower() != self.host:
            await PlainTextResponse("Misdirected request", status_code=421)(scope, receive, send)
            return
        origin = headers.get("origin")
        if origin is not None and origin.rstrip("/") != self.origin:
            await PlainTextResponse("Origin not allowed", status_code=403)(scope, receive, send)
            return

        authorization = headers.get("authorization")
        db = self.session_factory()
        try:
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
    if not config.claude_managed_mcp_enabled:
        raise RuntimeError("Claude Managed Agents MCP is disabled")
    enabled_tool_keys = _configured_tool_keys(config)
    if not enabled_tool_keys:
        raise RuntimeError("Claude Managed Agents MCP requires an explicit tool allowlist")
    registry = {spec.key: spec for spec in list_tools()}
    unknown = enabled_tool_keys.difference(registry)
    unsafe = {
        key for key in enabled_tool_keys.intersection(registry)
        if registry[key].risk_level != "read_only" or registry[key].requires_approval
    }
    if unknown or unsafe:
        raise ValueError("Claude MCP allowlist may contain only registered read-only tools")

    parsed = urlparse(config.claude_managed_mcp_public_base_url)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path not in ("", "/") or parsed.port not in (None, 443)
    ):
        raise ValueError("Claude MCP public URL must be a public HTTPS origin")
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
                principal, session = load_active_session_context(db, context)
                specs = _visible_read_only_specs(
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
                principal, session = load_active_session_context(db, context)
                visible = _visible_read_only_specs(
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
        instructions="Read-only tools are authorized by Agency OS for this exact workspace session.",
        on_list_tools=list_tools_handler,
        on_call_tool=call_tool_handler,
    )
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[parsed.netloc],
        allowed_origins=[origin],
    )
    mcp_app = server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        max_request_body_size=config.claude_managed_mcp_max_request_body_bytes,
        transport_security=transport_security,
    )
    wrapped = SessionPathAuthMiddleware(
        mcp_app,
        public_base_url=config.claude_managed_mcp_public_base_url,
        session_factory=session_factory,
        requests_per_minute=config.claude_managed_mcp_requests_per_minute,
        semaphore=asyncio.Semaphore(config.claude_managed_mcp_max_concurrent_requests),
    )
    return server, mcp_app, wrapped
