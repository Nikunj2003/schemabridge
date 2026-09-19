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
    max_model_requests_per_run: int = Field(default=3, alias="AI_MAX_REQUESTS_PER_RUN")
    max_model_requests_per_day: int = Field(default=400, alias="AI_MAX_REQUESTS_PER_DAY")
    #: Starts allowed for one anonymous browser session in an India calendar day.
    max_migration_starts_per_session_per_day: int = Field(
        default=10, alias="MIGRATION_MAX_RUNS_PER_DAY"
    )

    # --- Runtime ---------------------------------------------------------
    # Kept below the platform's 300 s function ceiling so a step returns a
    # checkpoint rather than being killed mid-write.
    advance_budget_seconds: float = Field(default=120.0, alias="ADVANCE_BUDGET_SECONDS")
    run_ttl_hours: int = Field(default=48, alias="RUN_TTL_HOURS")

    @property
    def has_model_access(self) -> bool:
        """Whether model assistance is configured. The agent degrades without it."""
        return bool(self.nvidia_api_key.strip())

    @property
    def has_database(self) -> bool:
        return bool(self.mongodb_uri.strip())

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
