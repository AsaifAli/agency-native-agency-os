from app.rate_limit import request_bucket


def test_authentication_routes_use_strict_bucket():
    assert request_bucket("/v1/auth/dev-token")[0] == "auth"


def test_expensive_routes_use_lower_bucket():
    assert request_bucket("/v1/orgs/o/workspaces/w/evaluations/run")[0] == "expensive"
    assert request_bucket("/v1/orgs/o/leads/research")[0] == "expensive"


def test_regular_routes_use_general_bucket():
    assert request_bucket("/v1/orgs/o/workspaces")[0] == "general"
