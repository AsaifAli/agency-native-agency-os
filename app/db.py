from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


is_sqlite = settings.database_url.startswith("sqlite")

if is_sqlite:
    connect_args = {
        "check_same_thread": False,
        "timeout": settings.db_connect_timeout_seconds,
    }
else:
    connect_args = {
        "connect_timeout": settings.db_connect_timeout_seconds,
        "options": (
            f"-c statement_timeout={settings.db_statement_timeout_ms} "
            f"-c lock_timeout={settings.db_lock_timeout_ms}"
        ),
    }

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_timeout=settings.db_pool_timeout_seconds,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()