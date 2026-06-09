"""Static application configuration loaded from environment variables.

These are deploy-time settings (read from the process environment / `.env`) that
do not change at runtime: connection URLs, secrets, ports, etc. Dynamic
platform settings that the Super_Admin can change at runtime (pricing, plan
limits, JWT expiry, rate limits, themes - Req 29.4) live in the
`platform_settings` table and are served by `app.core.settings_loader`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Application ----
    app_env: str = "development"
    app_debug: bool = False
    api_workers: int = 4
    public_base_url: str = "http://localhost:8000"

    # Comma-separated list of allowed CORS origins. "*" allows all.
    cors_allow_origins: str = "*"

    # ---- PostgreSQL + TimescaleDB ----
    database_url: str = "postgresql+asyncpg://iotaps:change_me_postgres@postgres:5432/iotaps"

    # ---- Redis ----
    redis_url: str = "redis://:change_me_redis@redis:6379/0"

    # ---- MQTT ----
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_topic_root: str = "iotaps"

    # Seconds to wait for a Command_ACK before marking a command UNACKNOWLEDGED
    # (Req 9.7). 0 disables the ACK timer (no automatic timeout).
    command_ack_timeout_seconds: int = 30

    # ---- JWT / Auth ----
    jwt_secret: str = "change_me_jwt_secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_seconds: int = 900
    jwt_refresh_token_ttl_seconds: int = 2592000

    # ---- Google OAuth ----
    # Client id used to verify Google ID tokens (Req 1.2). Empty disables OAuth.
    google_oauth_client_id: str = ""

    # ---- Razorpay (Payment_Gateway, Req 17) ----
    # API keys for order creation; left empty in dev/test so no live API is hit.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    # Shared secret used to verify inbound webhook signatures (Req 17.2).
    razorpay_webhook_secret: str = ""

    # ---- Platform settings cache ----
    # TTL (seconds) for the read-through Redis cache of `platform_settings`.
    platform_settings_cache_ttl_seconds: int = 300

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def cors_origins_list(self) -> list[str]:
        raw = self.cors_allow_origins.strip()
        if raw == "*" or raw == "":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
