"""Stateless Streamable HTTP MCP server for the Agency OS Tool Registry."""
from __future__ import annotations

import json

import anyio
from fastapi import HTTPException
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings

from app.config import settings
from app.db import SessionLocal
from app.mcp_auth import SessionBearerAuthMiddleware, get_mcp_request_context
from app.mcp_tools import call_session_tool, list_session_tools


def create_mcp_gateway():
    async def on_list_tools(_ctx, _params):
        request_context = get_mcp_request_context()

        def load_tools():
            with SessionLocal() as db:
                return list_session_tools(
                    db,
                    request_context,
                    enabled_tool_keys=settings.mcp_enabled_tool_keys_list,
                )

        tool_definitions = await anyio.to_thread.run_sync(load_tools)
        tools = [
            types.Tool.model_validate({
                "name": item["name"],
                "description": item["description"],
                "inputSchema": item["input_schema"],
            })
            for item in tool_definitions
        ]
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(ctx, params):
        request_context = get_mcp_request_context()
        if not isinstance(params.arguments, dict):
            return types.CallToolResult.model_validate({
                "content": [{
                    "type": "text",
                    "text": "Tool arguments must be a JSON object.",
                }],
                "isError": True,
            })

        def invoke():
            with SessionLocal() as db:
                return call_session_tool(
                    db,
                    request_context,
                    tool_name=params.name,
                    arguments=params.arguments,
                    request_id=ctx.request_id,
                    enabled_tool_keys=settings.mcp_enabled_tool_keys_list,
                    max_calls_per_session=settings.mcp_max_tool_calls_per_session,
                )

        try:
            result = await anyio.to_thread.run_sync(invoke)
        except HTTPException:
            return types.CallToolResult.model_validate({
                "content": [{
                    "type": "text",
                    "text": "Tool call denied by Agency OS policy.",
                }],
                "isError": True,
            })

        result_text = json.dumps(
            result["result"],
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        return types.CallToolResult.model_validate({
            "content": [{"type": "text", "text": result_text}],
            "isError": False,
        })

    server = Server(
        "agency-os",
        version="1.0.0",
        instructions=(
            "Agency OS tools are governed by server-side identity, workspace, "
            "session, data-class, approval and audit policy. Do not infer permission "
            "from tool visibility; a call may be denied by OS policy."
        ),
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )
    mcp_app = server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        max_request_body_size=settings.mcp_max_request_body_bytes,
        transport_security=TransportSecuritySettings(
            allowed_hosts=settings.mcp_allowed_hosts_list,
            allowed_origins=settings.mcp_allowed_origins_list,
            enable_dns_rebinding_protection=True,
        ),
        host="0.0.0.0",
    )
    authenticated_app = SessionBearerAuthMiddleware(
        mcp_app,
        session_factory=SessionLocal,
        requests_per_minute=settings.mcp_requests_per_minute,
        max_concurrent_requests=settings.mcp_max_concurrent_requests,
    )
    return mcp_app, authenticated_app
