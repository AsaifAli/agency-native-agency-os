from urllib.parse import urlsplit

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

    # Session-bound MCP endpoint. Disabled until a public HTTPS URL and strict
    # Host allowlist are configured; only read-only tools are enabled by default.
    mcp_gateway_enabled: bool = False
    mcp_public_url: str = ""
    mcp_allowed_hosts: str = ""
    mcp_allowed_origins: str = ""
    mcp_enabled_tool_keys: str = "system.health.read"
    mcp_session_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    mcp_requests_per_minute: int = Field(default=120, ge=1, le=10000)
    mcp_max_tool_calls_per_session: int = Field(default=50, ge=1, le=1000)
    mcp_max_request_body_bytes: int = Field(default=65536, ge=4096, le=1048576)
    mcp_max_concurrent_requests: int = Field(default=16, ge=1, le=256)

    # Optional signed server-to-server intake from the public agency website.
    # Disabled until a dedicated secret and fixed org/workspace mapping are configured.
    website_lead_intake_enabled: bool = False
    website_lead_intake_secret: str | None = None
    website_lead_intake_key_id: str = ""
    website_lead_intake_org_id: str = ""
    website_lead_intake_workspace_id: str = ""
    website_lead_intake_clock_skew_seconds: int = Field(default=300, ge=30, le=900)

    @model_validator(mode="after")
    def validate_retry_settings(self):
        if self.outbox_max_retry_seconds < self.outbox_base_retry_seconds:
            raise ValueError(
                "OUTBOX_MAX_RETRY_SECONDS must be greater than or equal "
                "to OUTBOX_BASE_RETRY_SECONDS"
            )
        return self

    @property
    def mcp_allowed_hosts_list(self) -> list[str]:
        return [value.strip() for value in self.mcp_allowed_hosts.split(",") if value.strip()]

    @property
    def mcp_allowed_origins_list(self) -> list[str]:
        return [value.strip() for value in self.mcp_allowed_origins.split(",") if value.strip()]

    @property
    def mcp_enabled_tool_keys_list(self) -> list[str]:
        return [value.strip() for value in self.mcp_enabled_tool_keys.split(",") if value.strip()]

    @model_validator(mode="after")
    def validate_mcp_settings(self):
        if not self.mcp_gateway_enabled:
            return self
        parsed = urlsplit(self.mcp_public_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path != "/mcp/agency-os"
        ):
            raise ValueError(
                "MCP_PUBLIC_URL must be an HTTPS URL ending exactly in /mcp/agency-os"
            )
        allowed_hosts = self.mcp_allowed_hosts_list
        if not allowed_hosts or "*" in allowed_hosts:
            raise ValueError("MCP_ALLOWED_HOSTS must contain explicit public hostnames")
        if "*" in self.mcp_allowed_origins_list:
            raise ValueError("MCP_ALLOWED_ORIGINS must contain explicit origins, not a wildcard")
        if not any(
            host in allowed_hosts
            for host in (parsed.netloc, parsed.hostname, f"{parsed.hostname}:*")
        ):
            raise ValueError("MCP_ALLOWED_HOSTS must allow the host in MCP_PUBLIC_URL")
        tool_keys = self.mcp_enabled_tool_keys_list
        if not tool_keys or len(set(tool_keys)) != len(tool_keys):
            raise ValueError("MCP_ENABLED_TOOL_KEYS must contain unique registered tool keys")
        return self


settings = Settings()
