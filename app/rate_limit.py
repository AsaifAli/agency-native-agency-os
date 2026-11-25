"""Distributed request throttling for API abuse and costly operations."""
from __future__ import annotations

import hashlib

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings


def request_bucket(path: str) -> tuple[str, int]:
    normalized = path.lower()
    if normalized.startswith("/v1/auth/"):
        return "auth", settings.rate_limit_auth_per_minute
    if any(part in normalized for part in ("/research", "/evaluations", "/execute", "/website-intake", "/managed-agents")):
        return "expensive", settings.rate_limit_expensive_per_minute
    return "general", settings.rate_limit_general_per_minute


def _identity(request: Request) -> str:
    # Do not trust X-Forwarded-For unless a trusted proxy layer has normalized it.
    ip = request.client.host if request.client else "unknown"
    bearer = request.headers.get("authorization", "")
    token_fingerprint = hashlib.sha256(bearer.encode("utf-8")).hexdigest()[:16] if bearer else "anonymous"
    return hashlib.sha256(f"{ip}:{token_fingerprint}".encode("utf-8")).hexdigest()


class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True) if settings.rate_limit_enabled else None

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if self.redis is None or request.url.path in {"/health", "/openapi.json", "/docs", "/redoc"}:
            return await call_next(request)
        bucket, limit = request_bucket(request.url.path)
        key = f"agency-os:ratelimit:v1:{bucket}:{_identity(request)}"
        try:
            count = await self.redis.eval(
                "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return n",
                1,
                key,
            )
        except RedisError:
            # Never silently disable protection in production when Redis is down.
            if settings.app_env.lower() == "production":
                return JSONResponse({"detail": "Rate limiting temporarily unavailable"}, status_code=503)
            return await call_next(request)
        if int(count) > limit:
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
