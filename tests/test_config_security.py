import pytest
from pydantic import ValidationError
from app.config import Settings


def production_settings(**overrides):
    values = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://agency_os:strong-password-that-is-long-enough-32chars@db.example.com/agency_os",
        "redis_url": "rediss://redis.example.com:6379/0",
        "jwt_secret": "a" * 64,
        "dev_auth_enabled": False,
        "mock_runtime_enabled": False,
        "cors_origins": "https://console.example.com",
        "rate_limit_enabled": True,
        "oidc_issuer": "https://auth.example.com/application/o/agency-os/",
        "oidc_client_id": "agency-os",
        "oidc_client_secret": "oidc-client-secret",
        "oidc_state_secret": "s" * 64,
        "oidc_redirect_uri": "https://api.example.com/v1/auth/callback",
        "oidc_frontend_url": "https://console.example.com",
        "oidc_required_acr": "urn:agency-os:aal2",
    }
    values.update(overrides)
    return values


def test_production_rejects_development_authentication():
    with pytest.raises(ValidationError, match="DEV_AUTH_ENABLED"):
        Settings(**production_settings(dev_auth_enabled=True))


def test_production_rejects_short_or_placeholder_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(**production_settings(jwt_secret="unsafe-development-secret-change-me"))


def test_production_rejects_sqlite_database():
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(**production_settings(database_url="sqlite:///./agency_os.db"))


def test_production_rejects_mock_runtime():
    with pytest.raises(ValidationError, match="MOCK_RUNTIME_ENABLED"):
        Settings(**production_settings(mock_runtime_enabled=True))


def test_production_rejects_wildcard_or_insecure_cors():
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(**production_settings(cors_origins="*"))
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(**production_settings(cors_origins="http://console.example.com"))


def test_production_requires_distributed_rate_limiting():
    with pytest.raises(ValidationError, match="RATE_LIMIT_ENABLED"):
        Settings(**production_settings(rate_limit_enabled=False))


def test_production_rejects_untrusted_claude_api_base_url():
    with pytest.raises(ValidationError, match="ANTHROPIC_API_BASE_URL"):
        Settings(**production_settings(
            claude_managed_agents_enabled=True,
            anthropic_api_base_url="https://169.254.169.254/latest/meta-data",
        ))


def test_production_accepts_official_claude_api_endpoint():
    config = Settings(**production_settings(
        claude_managed_agents_enabled=True,
        anthropic_api_base_url="https://api.anthropic.com",
    ))
    assert config.claude_managed_agents_enabled is True


def test_production_rejects_weak_database_password():
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(**production_settings(database_url="postgresql+psycopg://agency_os:change-me@db.example.com/agency_os"))


def test_production_rejects_non_tls_redis_url():
    with pytest.raises(ValidationError, match="REDIS_URL"):
        Settings(**production_settings(redis_url="redis://redis.example.com:6379/0"))


def test_production_requires_authentik_oidc_configuration():
    values = production_settings()
    values["oidc_client_secret"] = None
    with pytest.raises(ValidationError, match="OIDC_ISSUER"):
        Settings(**values)


def test_production_requires_independent_oidc_state_secret():
    with pytest.raises(ValidationError, match="OIDC_STATE_SECRET"):
        Settings(**production_settings(oidc_state_secret="too-short"))


def test_production_requires_https_oidc_redirect_and_frontend():
    with pytest.raises(ValidationError, match="OIDC_REDIRECT_URI"):
        Settings(**production_settings(oidc_redirect_uri="http://api.example.com/v1/auth/callback"))
    with pytest.raises(ValidationError, match="OIDC_FRONTEND_URL"):
        Settings(**production_settings(oidc_frontend_url="http://console.example.com"))
