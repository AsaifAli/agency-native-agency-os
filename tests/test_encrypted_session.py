from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.session import EncryptedSessionMiddleware


def test_oidc_transaction_session_cookie_is_encrypted_and_round_trips():
    app = FastAPI()
    app.add_middleware(
        EncryptedSessionMiddleware,
        secret_key="k" * 64,
        session_cookie="agency_os_oidc_state",
        max_age=600,
        https_only=True,
    )

    @app.get("/begin")
    def begin(request: Request):
        request.session["code_verifier"] = "highly-sensitive-pkce-verifier"
        request.session["nonce"] = "oidc-nonce-value"
        return {"started": True}

    @app.get("/continue")
    def continue_flow(request: Request):
        return {
            "code_verifier": request.session.get("code_verifier"),
            "nonce": request.session.get("nonce"),
        }

    client = TestClient(app, base_url="https://testserver")
    response = client.get("/begin")
    cookie = response.cookies.get("agency_os_oidc_state")
    assert cookie
    assert "highly-sensitive-pkce-verifier" not in cookie
    assert "oidc-nonce-value" not in cookie
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "secure" in response.headers["set-cookie"].lower()

    continued = client.get("/continue")
    assert continued.json() == {
        "code_verifier": "highly-sensitive-pkce-verifier",
        "nonce": "oidc-nonce-value",
    }


def test_tampered_oidc_session_cookie_is_not_trusted():
    app = FastAPI()
    app.add_middleware(EncryptedSessionMiddleware, secret_key="k" * 64)

    @app.get("/state")
    def state(request: Request):
        return {"has_state": bool(request.session)}

    client = TestClient(app)
    client.cookies.set("agency_os_oidc_state", "attacker-controlled-cookie")
    response = client.get("/state")
    assert response.json() == {"has_state": False}
