from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "sqlite:///./agency_os.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "unsafe-development-secret-change-me"
    jwt_issuer: str = "agency-os"
    dev_auth_enabled: bool = True
    mock_runtime_enabled: bool = False
    cors_origins: str = "http://localhost:3000"
    db_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    db_pool_timeout_seconds: int = Field(default=5, ge=1, le=300)
    db_statement_timeout_ms: int = Field(default=15000, ge=1, le=300000)
    db_lock_timeout_ms: int = Field(default=5000, ge=1, le=300000)
    worker_heartbeat_shutdown_timeout_seconds: int = Field(
        default=25, ge=1, le=300
    )
    worker_lease_seconds: int = Field(
        default=60, ge=15, le=3600
    )
    worker_poll_interval_seconds: float = Field(
        default=2.0, ge=0.1, le=60
    )
    worker_maintenance_interval_seconds: int = Field(
        default=15, ge=1, le=3600
    )
    worker_maintenance_batch_size: int = Field(
        default=100, ge=1, le=1000
    )

settings = Settings()
