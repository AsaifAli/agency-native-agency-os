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


def test_organization_routes_include_an_explicit_membership_or_role_check():
    import ast
    import inspect

    required_checks = {
        "require_membership",
        "require_role",
        "require_founder_authority",
    }
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or "{org_id}" not in route.path:
            continue
        tree = ast.parse(inspect.getsource(route.endpoint))
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        if not calls.intersection(required_checks):
            missing.append(f"{','.join(sorted(route.methods or []))} {route.path}")
    assert not missing, "Organization routes without an explicit membership/role check: " + ", ".join(sorted(missing))


def test_workspace_routes_reference_the_workspace_identifier():
    import ast
    import inspect

    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or "{workspace_id}" not in route.path:
            continue
        tree = ast.parse(inspect.getsource(route.endpoint))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        if "workspace_id" not in names:
            missing.append(f"{','.join(sorted(route.methods or []))} {route.path}")
    assert not missing, "Workspace routes that do not use their workspace identifier: " + ", ".join(sorted(missing))


def test_workspace_scoped_routes_use_the_centralized_grant_guard():
    import ast
    import inspect

    guard_calls = {
        "workspace_in_org",
        "_workspace",
        "_scope",
        "_write",
        "_write_access",
        "_read",
        "_write_or_founder",
        "_read_or_founder",
        "_project",
        "require_workspace_access",
        "require_workspace_access_from_context",
    }
    grant_admin_routes = {"create_workspace_grant", "revoke_workspace_grant"}
    workspace_collection_routes = {"list_workspaces"}
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        source = inspect.getsource(route.endpoint)
        tree = ast.parse(source)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        args = {
            arg.arg
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for arg in node.args.args
        }
        if "workspace_id" not in names and "workspace_id" not in args and "workspace_id" not in attributes:
            continue
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        if route.endpoint.__name__ in workspace_collection_routes:
            # Collection endpoints cannot accept one workspace_id; they must
            # filter the result set by the caller's active workspace grants.
            assert "WorkspaceGrant" in names
            assert "user_id" in attributes
            continue
        if route.endpoint.__name__ in grant_admin_routes:
            assert "require_founder_authority" in calls
            continue
        if not calls.intersection(guard_calls):
            missing.append(f"{','.join(sorted(route.methods or []))} {route.path}")
    assert not missing, (
        "Workspace-scoped routes missing the centralized grant guard: "
        + ", ".join(sorted(missing))
    )
