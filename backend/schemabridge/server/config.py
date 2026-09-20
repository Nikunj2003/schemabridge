"""Server configuration.

Settings are resolved lazily through a cached accessor rather than at import
time, so a missing value surfaces as a handled error on the request that needs
it instead of preventing the application from starting at all. Nothing here is
exposed to the browser.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Values supplied by the environment. See `.env.example`."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local", "../.env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Inference -------------------------------------------------------
    nvidia_api_key: str = Field(default="", alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1", alias="NVIDIA_BASE_URL"
    )
    nvidia_model: str = Field(default="nvidia/nemotron-3.5-lightning-30b-a3b", alias="NVIDIA_MODEL")
    # Measured against the hosted endpoint: a schema-constrained reply lands in
    # roughly 30 s with reasoning disabled, so allow headroom without letting a
    # stalled request consume the whole function budget.
    model_timeout_seconds: float = Field(default=60.0, alias="MODEL_TIMEOUT_SECONDS")

    # --- Persistence -----------------------------------------------------
    mongodb_uri: str = Field(default="", alias="MONGODB_URI")
    mongodb_db: str = Field(default="schemabridge", alias="MONGODB_DB")

    # --- Identity --------------------------------------------------------
    #: Issuer URL without a trailing slash, for example
    #: ``https://example.us.auth0.com``. The browser receives only the matching
    #: ``NEXT_PUBLIC_*`` values; API validation settings remain server-only.
    auth0_issuer: str = Field(default="", alias="AUTH0_ISSUER")
    auth0_audience: str = Field(default="", alias="AUTH0_AUDIENCE")
    auth0_jwks_cache_seconds: int = Field(default=3600, alias="AUTH0_JWKS_CACHE_SECONDS")

    # --- Optional LLM telemetry -----------------------------------------
    langfuse_enabled: bool = Field(default=False, alias="LANGFUSE_ENABLED")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")
    langfuse_capture_content: bool = Field(default=False, alias="LANGFUSE_CAPTURE_CONTENT")
    observability_api_secret: str = Field(default="", alias="OBSERVABILITY_API_SECRET")

    # --- Destination connector -------------------------------------------
    target_api_secret: str = Field(default="", alias="TARGET_API_SECRET")
    #: Where outbound delivery is sent. Must be an origin *this service* can
    #: reach, which is not always the one the browser used: in local development
    #: the browser talks to the web service and is proxied here, so the
    #: browser's origin would not resolve to the destination at all.
    target_api_origin: str | None = Field(default=None, alias="TARGET_API_ORIGIN")
    #: Port this service is listening on, used to build a loopback origin when
    #: none is configured.
    port: int = Field(default=8000, alias="PORT")

    # --- Demo safety budgets ---------------------------------------------
    #: A run now has two reasons to call out: placing unfamiliar columns, and
    #: drafting a rule from a decision. Rule drafting happens once per question, so
    #: a migration with several questions needs headroom above the single mapping
    #: call — while still being bounded, because the cap is what stops a long
    #: review from spending the allowance one correction at a time.
    max_model_requests_per_run: int = Field(default=6, alias="AI_MAX_REQUESTS_PER_RUN")
    max_model_requests_per_day: int = Field(default=400, alias="AI_MAX_REQUESTS_PER_DAY")
    #: Starts allowed for one anonymous browser session in an India calendar day.
    #: Starts allowed for one verified Google account each India calendar day.
    authenticated_migration_starts_per_day: int = Field(
        default=20, alias="AUTHENTICATED_MIGRATION_MAX_RUNS_PER_DAY"
    )
    #: Starts shared by every person deliberately using the anonymous workspace.
    anonymous_migration_starts_per_day: int = Field(
        default=100, alias="ANONYMOUS_MIGRATION_MAX_RUNS_PER_DAY"
    )
    #: Kept as a compatibility alias while deployments move to the explicit
    #: workspace settings; new code must use one of the two policies above.
    max_migration_starts_per_session_per_day: int = Field(
        default=100, alias="MIGRATION_MAX_RUNS_PER_DAY"
    )
    nvidia_requests_per_minute: int = Field(default=45, alias="NVIDIA_REQUESTS_PER_MINUTE")
    nvidia_retry_attempts: int = Field(default=3, alias="NVIDIA_RETRY_ATTEMPTS")
    nvidia_max_queue_seconds: float = Field(default=45.0, alias="NVIDIA_MAX_QUEUE_SECONDS")

    # --- Runtime ---------------------------------------------------------
    # Kept below the platform's 300 s function ceiling so a step returns a
    # checkpoint rather than being killed mid-write.
    advance_budget_seconds: float = Field(default=120.0, alias="ADVANCE_BUDGET_SECONDS")
    authenticated_retention_hours: int = Field(default=168, alias="AUTHENTICATED_RETENTION_HOURS")
    anonymous_retention_hours: int = Field(default=48, alias="ANONYMOUS_RETENTION_HOURS")
    #: The legacy checkpointer TTL remains only for records written before
    #: workspace-aware expiry is enabled.
    run_ttl_hours: int = Field(default=48, alias="RUN_TTL_HOURS")

    @property
    def has_model_access(self) -> bool:
        """Whether model assistance is configured. The agent degrades without it."""
        return bool(self.nvidia_api_key.strip())

    @property
    def has_database(self) -> bool:
        return bool(self.mongodb_uri.strip())

    @property
    def auth0_configured(self) -> bool:
        return bool(self.auth0_issuer.strip() and self.auth0_audience.strip())

    @property
    def langfuse_configured(self) -> bool:
        return bool(
            self.langfuse_enabled
            and self.langfuse_public_key.strip()
            and self.langfuse_secret_key.strip()
        )

    def require_model_key(self) -> str:
        if not self.nvidia_api_key.strip():
            raise RuntimeError(
                "NVIDIA_API_KEY is not set. Copy .env.example to .env.local and fill it in."
            )
        return self.nvidia_api_key.strip()

    def require_mongodb_uri(self) -> str:
        if not self.mongodb_uri.strip():
            raise RuntimeError(
                "MONGODB_URI is not set. Copy .env.example to .env.local and fill it in."
            )
        return self.mongodb_uri.strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance, so warm invocations do not re-read the env."""
    return Settings()
