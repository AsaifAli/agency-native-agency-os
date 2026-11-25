
from logging.config import fileConfig
import os

from alembic import context

from app.config import settings
from app.db import Base, engine
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
import app.models  # noqa: F401 — register all models with Base.metadata
import app.domain_models  # noqa: F401 — register Revenue/Delivery metadata
import app.telephony.models  # noqa: F401 — register telephony/outbox metadata
import app.operations_models  # noqa: F401 — register delivery operations metadata
import app.outreach.models  # noqa: F401 — register governed outbound communication metadata
import app.workforce_models  # noqa: F401 — register governed workforce metadata
import app.security_models  # noqa: F401 — register machine identity/session metadata


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
migration_database_url = os.environ.get("MIGRATION_DATABASE_URL") or settings.database_url


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    context.configure(
        url=migration_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=migration_database_url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using the application's configured database engine."""
    migration_engine = create_engine(migration_database_url, poolclass=NullPool) if os.environ.get("MIGRATION_DATABASE_URL") else engine
    with migration_engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=migration_database_url.startswith("sqlite"),
        )

        with context.begin_transaction():
            context.run_migrations()
    if migration_engine is not engine:
        migration_engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
