from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.csrf import CookieCSRFMiddleware
from app.config import settings


def test_cookie_authenticated_mutation_requires_csrf_token_and_allowed_origin(monkeypatch):
    monkeypatch.setattr(settings, "cors_origins", "https://console.example.com")
    app = FastAPI()
    app.add_middleware(CookieCSRFMiddleware)

    @app.post("/mutate")
    def mutate():
        return {"ok": True}

    client = TestClient(app)
    client.cookies.set(settings.oidc_session_cookie_name, "opaque-session")
    client.cookies.set(settings.oidc_csrf_cookie_name, "csrf-secret")

    missing = client.post("/mutate", headers={"Origin": "https://console.example.com"})
    assert missing.status_code == 403

    wrong_origin = client.post("/mutate", headers={"Origin": "https://attacker.example", "X-CSRF-Token": "csrf-secret"})
    assert wrong_origin.status_code == 403

    accepted = client.post("/mutate", headers={"Origin": "https://console.example.com", "X-CSRF-Token": "csrf-secret"})
    assert accepted.status_code == 200


def test_bearer_authenticated_mutation_is_not_forced_to_use_browser_csrf(monkeypatch):
    monkeypatch.setattr(settings, "cors_origins", "https://console.example.com")
    app = FastAPI()
    app.add_middleware(CookieCSRFMiddleware)

    @app.post("/mutate")
    def mutate():
        return {"ok": True}

    client = TestClient(app)
    response = client.post("/mutate", headers={"Authorization": "Bearer service-token"})
    assert response.status_code == 200
