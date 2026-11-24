from pydantic import Field, model_validator
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
    worker_lease_seconds: int = Field(default=60, ge=15, le=3600)
    worker_poll_interval_seconds: float = Field(default=2.0, ge=0.1, le=60)
    worker_maintenance_interval_seconds: int = Field(default=15, ge=1, le=3600)
    worker_maintenance_batch_size: int = Field(default=100, ge=1, le=1000)

    outbox_lease_seconds: int = Field(default=120, ge=15, le=3600)
    outbox_base_retry_seconds: int = Field(default=15, ge=1, le=3600)
    outbox_max_retry_seconds: int = Field(default=3600, ge=1, le=86400)

    # Claude Managed Agents is beta and remains opt-in. Keep credentials in
    # environment/secrets management; never place them in agent prompts.
    claude_managed_agents_enabled: bool = False
    anthropic_api_key: str | None = None
    anthropic_api_base_url: str = "https://api.anthropic.com"
    anthropic_api_version: str = "2026-10-21"
    anthropic_managed_agents_beta: str = "managed-agents-2026-04-01"
    claude_managed_agent_id: str = ""
    claude_managed_environment_id: str = ""
    claude_managed_session_budget_cents: int = Field(default=250, ge=1, le=100000)
    claude_managed_timeout_seconds: int = Field(default=900, ge=30, le=3600)
    claude_managed_poll_interval_seconds: float = Field(default=2.0, ge=0.2, le=30)
    anthropic_request_timeout_seconds: float = Field(default=20.0, ge=1, le=120)

    @model_validator(mode="after")
    def validate_retry_settings(self):
        if self.outbox_max_retry_seconds < self.outbox_base_retry_seconds:
            raise ValueError(
                "OUTBOX_MAX_RETRY_SECONDS must be greater than or equal "
                "to OUTBOX_BASE_RETRY_SECONDS"
            )
        return self


settings = Settings()
