from pydantic import ValidationError
import pytest

from app.config import Settings


def test_outbox_retry_configuration_rejects_max_below_base():
    with pytest.raises(ValidationError, match="OUTBOX_MAX_RETRY_SECONDS"):
        Settings(
            _env_file=None,
            outbox_base_retry_seconds=120,
            outbox_max_retry_seconds=30,
        )


def test_outbox_retry_configuration_accepts_equal_bounds():
    settings = Settings(
        _env_file=None,
        outbox_base_retry_seconds=30,
        outbox_max_retry_seconds=30,
    )
    assert settings.outbox_base_retry_seconds == 30
    assert settings.outbox_max_retry_seconds == 30


def _production_worker_settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env="production",
        process_role="worker",
        database_url=database_url,
        redis_url="rediss://redis.example.test:6380/0",
        jwt_secret="j" * 80,
        jwt_key_id="worker-test-key",
        dev_auth_enabled=False,
        mock_runtime_enabled=False,
        rate_limit_enabled=True,
        cors_origins="https://agency.example.com",
        oidc_issuer="https://identity.example.com",
        oidc_client_id="agency-os",
        oidc_client_secret="c" * 40,
        oidc_state_secret="s" * 80,
        oidc_redirect_uri="https://agency.example.com/v1/auth/callback",
        oidc_frontend_url="https://agency.example.com",
        oidc_required_acr="urn:example:mfa",
    )


def test_production_worker_accepts_dedicated_nobypassrls_database_role():
    settings = _production_worker_settings(
        "postgresql+psycopg://agency_os_worker:" + "p" * 40 + "@db.example.com/agency"
    )
    assert settings.process_role == "worker"


def test_production_worker_rejects_api_database_role_with_correct_security_contract():
    with pytest.raises(ValidationError, match="NOBYPASSRLS"):
        _production_worker_settings(
            "postgresql+psycopg://agency_os_app:" + "p" * 40 + "@db.example.com/agency"
        )
