from typing import Literal
import ipaddress
from pydantic import Field, model_validator
from urllib.parse import urlparse
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./agency_os.db"
    process_role: Literal["api", "worker", "migration"] = "api"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "unsafe-development-secret-change-me"
    jwt_key_id: str = "key-current"
    jwt_previous_secret: str | None = None
    jwt_previous_key_id: str = "key-previous"
    jwt_issuer: str = "agency-os"
    dev_auth_enabled: bool = True
    mock_runtime_enabled: bool = False
    cors_origins: str = "http://localhost:3000"
    rate_limit_enabled: bool = False
    rate_limit_general_per_minute: int = Field(default=120, ge=1, le=10000)
    rate_limit_expensive_per_minute: int = Field(default=10, ge=1, le=1000)
    rate_limit_auth_per_minute: int = Field(default=5, ge=1, le=100)

    # Authentik is the external identity provider; Agency OS remains the
    # authority for local membership, workspace access and founder grants.
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str | None = None
    oidc_state_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_frontend_url: str = ""
    oidc_required_acr: str = ""
    oidc_session_cookie_name: str = "agency_os_session"
    oidc_state_cookie_name: str = "agency_os_oidc_state"
    oidc_csrf_cookie_name: str = "agency_os_csrf"
    oidc_session_ttl_seconds: int = Field(default=1800, ge=300, le=43200)
    browser_session_retention_days: int = Field(default=30, ge=1, le=3650)
    agent_session_metadata_retention_days: int = Field(default=90, ge=1, le=3650)
    tool_invocation_payload_retention_days: int = Field(default=180, ge=1, le=3650)

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

    # Generic Agency MCP transport for founder-provisioned Code/Cowork/service
    # identities. It does not require an Anthropic Vault.
    agency_mcp_enabled: bool = False
    agency_mcp_public_base_url: str = ""
    agency_mcp_enabled_tool_keys: str = ""
    agency_mcp_requests_per_minute: int = Field(default=120, ge=1, le=1000)
    agency_mcp_max_concurrent_requests: int = Field(default=8, ge=1, le=64)
    agency_mcp_max_request_body_bytes: int = Field(default=1048576, ge=1024, le=4194304)

    # Provider-facing Claude Managed Agents MCP remains separately opt-in and
    # requires its dedicated Anthropic Vault configuration.
    claude_managed_mcp_enabled: bool = False
    claude_managed_mcp_public_base_url: str = ""
    claude_managed_mcp_vault_id: str = ""
    claude_managed_mcp_enabled_tool_keys: str = ""
    claude_managed_mcp_requests_per_minute: int = Field(default=120, ge=1, le=1000)
    # Anthropic currently limits each Vault to 20 credentials. Keep headroom
    # for pending/manual-reconciliation credentials and serialize reservations in PostgreSQL.
    claude_managed_mcp_max_active_credentials: int = Field(default=16, ge=1, le=20)
    claude_managed_mcp_max_concurrent_requests: int = Field(default=8, ge=1, le=64)
    claude_managed_mcp_max_request_body_bytes: int = Field(default=1048576, ge=1024, le=4194304)

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
        if self.agency_mcp_enabled:
            agency_url = urlparse(self.agency_mcp_public_base_url)
            if (
                agency_url.scheme != "https" or not agency_url.hostname
                or agency_url.username or agency_url.password or agency_url.query or agency_url.fragment
                or agency_url.path not in ("", "/") or agency_url.port not in (None, 443)
            ):
                raise ValueError("AGENCY_MCP_PUBLIC_BASE_URL must be a public HTTPS origin")
            agency_host = (agency_url.hostname or "").lower().rstrip(".")
            if agency_host in {"localhost", "localhost.localdomain"} or agency_host.endswith((".localhost", ".local", ".internal", ".test")):
                raise ValueError("Agency MCP public host cannot be local or internal")
            try:
                agency_address = ipaddress.ip_address(agency_host)
            except ValueError:
                agency_address = None
            if agency_address is not None and not agency_address.is_global:
                raise ValueError("Agency MCP public host cannot be a private or reserved IP")
            if not [key.strip() for key in self.agency_mcp_enabled_tool_keys.split(",") if key.strip()]:
                raise ValueError("AGENCY_MCP_ENABLED_TOOL_KEYS must contain a reviewed tool allowlist")
        if self.claude_managed_mcp_enabled:
            mcp_url = urlparse(self.claude_managed_mcp_public_base_url)
            if not self.claude_managed_agents_enabled:
                raise ValueError("CLAUDE_MANAGED_AGENTS_ENABLED must be true when Claude MCP is enabled")
            if (
                mcp_url.scheme != "https" or not mcp_url.hostname
                or mcp_url.username or mcp_url.password or mcp_url.query or mcp_url.fragment
                or mcp_url.path not in ("", "/") or mcp_url.port not in (None, 443)
            ):
                raise ValueError("CLAUDE_MANAGED_MCP_PUBLIC_BASE_URL must be an HTTPS origin")
            host = (mcp_url.hostname or "").lower().rstrip(".")
            if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal", ".test")):
                raise ValueError("Claude MCP public host cannot be local or internal")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is not None and not address.is_global:
                raise ValueError("Claude MCP public host cannot be a private or reserved IP")
            if not self.claude_managed_mcp_vault_id.startswith("vlt_"):
                raise ValueError("CLAUDE_MANAGED_MCP_VAULT_ID must identify the dedicated Anthropic Vault")
            if not [key.strip() for key in self.claude_managed_mcp_enabled_tool_keys.split(",") if key.strip()]:
                raise ValueError("CLAUDE_MANAGED_MCP_ENABLED_TOOL_KEYS must contain a reviewed tool allowlist")
        if self.agency_mcp_enabled and self.claude_managed_mcp_enabled:
            if self.agency_mcp_public_base_url.rstrip("/") != self.claude_managed_mcp_public_base_url.rstrip("/"):
                raise ValueError("Agency MCP and Managed Agents MCP must share one public base URL when enabled together")
            agency_keys = {key.strip() for key in self.agency_mcp_enabled_tool_keys.split(",") if key.strip()}
            claude_keys = {key.strip() for key in self.claude_managed_mcp_enabled_tool_keys.split(",") if key.strip()}
            if agency_keys != claude_keys:
                raise ValueError("Agency MCP and Managed Agents MCP must share one tool allowlist when enabled together")
        if self.app_env.lower() == "production" and self.process_role != "migration":
            errors = []
            if self.dev_auth_enabled:
                errors.append("DEV_AUTH_ENABLED must be false in production")
            if self.mock_runtime_enabled:
                errors.append("MOCK_RUNTIME_ENABLED must be false in production")
            if len(self.jwt_secret) < 64 or self.jwt_secret == "unsafe-development-secret-change-me":
                errors.append("JWT_SECRET must be a secret-manager supplied value of at least 64 characters")
            if not self.jwt_key_id or len(self.jwt_key_id) > 64 or not self.jwt_key_id.replace("-", "").replace("_", "").isalnum():
                errors.append("JWT_KEY_ID must be a short alphanumeric key identifier")
            if self.jwt_previous_secret:
                if len(self.jwt_previous_secret) < 64:
                    errors.append("JWT_PREVIOUS_SECRET must be at least 64 characters during key rotation")
                if not self.jwt_previous_key_id or self.jwt_previous_key_id == self.jwt_key_id:
                    errors.append("JWT_PREVIOUS_KEY_ID must be non-empty and differ from JWT_KEY_ID")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                errors.append("DATABASE_URL must use PostgreSQL in production")
            db_password = urlparse(self.database_url).password
            database_role = urlparse(self.database_url).username
            if self.process_role == "api" and database_role != "agency_os_app":
                errors.append("API PROCESS_ROLE must use the dedicated NOBYPASSRLS agency_os_app database role")
            if self.process_role == "worker" and database_role != "agency_os_worker":
                errors.append("Worker PROCESS_ROLE must use the dedicated NOBYPASSRLS agency_os_worker database role")
            if not db_password or len(db_password) < 32 or db_password.lower() in {"change-me", "password", "postgres", "local-only-change-me"}:
                errors.append("DATABASE_URL must contain a strong, unique database password in production")
            if not self.redis_url.startswith("rediss://"):
                errors.append("REDIS_URL must use TLS (rediss://) in production")
            origins = [item.strip() for item in self.cors_origins.split(",") if item.strip()]
            if not origins or any(item == "*" or urlparse(item).scheme != "https" or not urlparse(item).netloc for item in origins):
                errors.append("CORS_ORIGINS must contain only explicit HTTPS origins in production")
            if not self.rate_limit_enabled:
                errors.append("RATE_LIMIT_ENABLED must be true in production")
            if self.oidc_issuer:
                issuer = urlparse(self.oidc_issuer)
                issuer_host = (issuer.hostname or "").lower().rstrip(".")
                issuer_invalid = (
                    issuer.scheme != "https" or not issuer_host
                    or bool(issuer.username or issuer.password)
                    or bool(issuer.query or issuer.fragment)
                    or issuer_host in {"localhost", "localhost.localdomain"}
                    or issuer_host.endswith((".localhost", ".local", ".internal", ".test"))
                )
                try:
                    issuer_port = issuer.port
                    issuer_ip = ipaddress.ip_address(issuer_host)
                except ValueError:
                    issuer_ip = None
                    try:
                        issuer_port = issuer.port
                    except ValueError:
                        issuer_invalid = True
                        issuer_port = None
                if issuer_ip is not None and not issuer_ip.is_global:
                    issuer_invalid = True
                if issuer_port not in (None, 443):
                    issuer_invalid = True
                if issuer_invalid:
                    errors.append("OIDC_ISSUER must be a public HTTPS issuer without credentials, query, fragment or non-standard port")
            if not (self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret and self.oidc_state_secret and self.oidc_redirect_uri and self.oidc_frontend_url and self.oidc_required_acr):
                errors.append("OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, OIDC_STATE_SECRET, OIDC_REDIRECT_URI, OIDC_FRONTEND_URL and OIDC_REQUIRED_ACR are required in production")
            if len(self.oidc_state_secret) < 64:
                errors.append("OIDC_STATE_SECRET must be a secret-manager supplied value of at least 64 characters")
            if self.oidc_redirect_uri and (urlparse(self.oidc_redirect_uri).scheme != "https" or not urlparse(self.oidc_redirect_uri).netloc or urlparse(self.oidc_redirect_uri).username or urlparse(self.oidc_redirect_uri).password):
                errors.append("OIDC_REDIRECT_URI must use HTTPS in production")
            if self.oidc_frontend_url and (urlparse(self.oidc_frontend_url).scheme != "https" or not urlparse(self.oidc_frontend_url).netloc or urlparse(self.oidc_frontend_url).username or urlparse(self.oidc_frontend_url).password):
                errors.append("OIDC_FRONTEND_URL must use HTTPS in production")
            if self.claude_managed_agents_enabled:
                provider_url = urlparse(self.anthropic_api_base_url)
                if provider_url.scheme != "https" or provider_url.hostname != "api.anthropic.com" or provider_url.username or provider_url.password or provider_url.port not in (None, 443):
                    errors.append("ANTHROPIC_API_BASE_URL must use the official HTTPS api.anthropic.com endpoint in production")
            if self.agency_mcp_enabled:
                agency_url = urlparse(self.agency_mcp_public_base_url)
                if (
                    agency_url.scheme != "https" or not agency_url.hostname
                    or agency_url.username or agency_url.password or agency_url.query or agency_url.fragment
                    or agency_url.path not in ("", "/") or agency_url.port not in (None, 443)
                ):
                    errors.append("AGENCY_MCP_PUBLIC_BASE_URL must be an HTTPS origin without credentials, path, query or non-standard port")
                if not [key.strip() for key in self.agency_mcp_enabled_tool_keys.split(",") if key.strip()]:
                    errors.append("AGENCY_MCP_ENABLED_TOOL_KEYS must contain an explicit tool allowlist")
            if self.claude_managed_mcp_enabled:
                mcp_url = urlparse(self.claude_managed_mcp_public_base_url)
                if not self.claude_managed_agents_enabled:
                    errors.append("CLAUDE_MANAGED_AGENTS_ENABLED must be true when Claude Managed Agents MCP is enabled")
                if (
                    mcp_url.scheme != "https" or not mcp_url.hostname
                    or mcp_url.username or mcp_url.password or mcp_url.query or mcp_url.fragment
                    or mcp_url.path not in ("", "/") or mcp_url.port not in (None, 443)
                ):
                    errors.append("CLAUDE_MANAGED_MCP_PUBLIC_BASE_URL must be an HTTPS origin without credentials, path, query or non-standard port")
                if not self.claude_managed_mcp_vault_id.startswith("vlt_"):
                    errors.append("CLAUDE_MANAGED_MCP_VAULT_ID must identify the dedicated Anthropic Vault")
                if not [key.strip() for key in self.claude_managed_mcp_enabled_tool_keys.split(",") if key.strip()]:
                    errors.append("CLAUDE_MANAGED_MCP_ENABLED_TOOL_KEYS must contain an explicit read-only or pending-draft tool allowlist")
            if errors:
                raise ValueError("; ".join(errors))
        return self


settings = Settings()
