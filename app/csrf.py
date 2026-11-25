"""Double-submit CSRF protection for browser-cookie authenticated requests."""
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.oidc_auth import validate_csrf_pair


class CookieCSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            return await call_next(request)
        session = request.cookies.get(settings.oidc_session_cookie_name)
        if not session:
            return await call_next(request)
        origin = request.headers.get("origin")
        allowed = {item.strip() for item in settings.cors_origins.split(",") if item.strip()}
        if not origin or origin not in allowed:
            return JSONResponse({"detail": "CSRF origin validation failed"}, status_code=403)
        try:
            validate_csrf_pair(
                request.cookies.get(settings.oidc_csrf_cookie_name),
                request.headers.get("x-csrf-token"),
            )
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await call_next(request)
