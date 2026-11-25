"""ASGI bearer authentication boundary for the stateless MCP endpoint."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

import anyio
from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.session_credentials import SessionCredentialContext, authenticate_session_credential


_MCP_REQUEST_CONTEXT: ContextVar[SessionCredentialContext | None] = ContextVar(
    "agency_os_mcp_request_context",
    default=None,
)


def get_mcp_request_context() -> SessionCredentialContext:
    context = _MCP_REQUEST_CONTEXT.get()
    if context is None:
        raise RuntimeError("MCP request context is unavailable.")
    return context


class SessionBearerAuthMiddleware:
    """Authenticate every Streamable HTTP request with one session-bound token."""

    def __init__(
        self,
        app,
        *,
        session_factory,
        requests_per_minute: int = 120,
        max_concurrent_requests: int = 16,
    ):
        self.app = app
        self.session_factory = session_factory
        self.requests_per_minute = max(1, int(requests_per_minute))
        self.semaphore = anyio.Semaphore(max(1, int(max_concurrent_requests)))

    def _authenticate(self, authorization: str | None) -> SessionCredentialContext:
        with self.session_factory() as db:
            return authenticate_session_credential(
                db,
                authorization,
                requests_per_minute=self.requests_per_minute,
            )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        authorization = Headers(scope=scope).get("authorization")
        try:
            context = await anyio.to_thread.run_sync(self._authenticate, authorization)
        except HTTPException as exc:
            status = 429 if exc.status_code == 429 else 401
            headers = {"Retry-After": "60"} if status == 429 else {"WWW-Authenticate": "Bearer"}
            response = JSONResponse(
                {"error": "rate_limited" if status == 429 else "unauthorized"},
                status_code=status,
                headers=headers,
            )
            await response(scope, receive, send)
            return

        token = _MCP_REQUEST_CONTEXT.set(context)
        try:
            async with self.semaphore:
                await self.app(scope, receive, send)
        finally:
            _MCP_REQUEST_CONTEXT.reset(token)
