"""Guard against test collection order binding the app engine to a live DB."""
from app.db import engine
from app.config import settings


def test_default_pytest_engine_uses_isolated_sqlite_database():
    assert settings.database_url.startswith("sqlite:///")
    assert engine.dialect.name == "sqlite"
