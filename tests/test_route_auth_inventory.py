"""Fail closed when a new API route is registered without an auth boundary."""
from fastapi.routing import APIRoute

from app.auth import get_principal
from app.main import app
from app.machine_identity import get_machine_principal


PUBLIC_ROUTE_ALLOWLIST = {
    ("GET", "/v1/auth/login"),
    ("GET", "/v1/auth/callback"),
    ("GET", "/v1/auth/csrf"),
    ("POST", "/v1/auth/dev-token"),
    ("GET", "/health"),
    ("POST", "/v1/integrations/website-leads"),
}

# These endpoints deliberately do not use get_principal: logout must work for
# revoked/expired sessions, while refresh authenticates and rotates the cookie
# inside the handler. Both are protected by CookieCSRFMiddleware.
SESSION_COOKIE_ROUTE_ALLOWLIST = {
    ("POST", "/v1/auth/logout"): "authentik_logout",
    ("POST", "/v1/auth/refresh"): "refresh_browser_session",
}


def _dependency_calls(dependant):
    if dependant.call is not None:
        yield dependant.call
    for child in dependant.dependencies:
        yield from _dependency_calls(child)


def test_every_registered_api_route_has_an_explicit_auth_boundary():
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        calls = set(_dependency_calls(route.dependant))
        for method in route.methods or set():
            key = (method, route.path)
            if key in PUBLIC_ROUTE_ALLOWLIST:
                continue
            if key in SESSION_COOKIE_ROUTE_ALLOWLIST:
                assert route.endpoint.__name__ == SESSION_COOKIE_ROUTE_ALLOWLIST[key]
                assert any(m.cls.__name__ == "CookieCSRFMiddleware" for m in app.user_middleware)
                continue
            if get_principal not in calls and get_machine_principal not in calls:
                missing.append(f"{method} {route.path}")

    assert not missing, "Routes without an auth dependency or explicit public allowlist: " + ", ".join(sorted(missing))
