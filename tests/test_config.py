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
