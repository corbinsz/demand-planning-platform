"""Runtime settings, read from the environment and an optional ``.env`` file."""

from functools import lru_cache

from pydantic_settings import BaseSettings

# Values that mean "the user has not connected this integration."
# Compared case-insensitively. None of these are real credentials.
_PLACEHOLDER_SECRETS = {
    "",
    "replace-me",
    "placeholder",
    "placeholder_token",
    "shpat_placeholder",
    "your-token",
    "your_shiphero_bearer_token",
    "change-me",
    "changeme",
}


class Settings(BaseSettings):
    """Process configuration.

    Local ``uvicorn`` defaults to a SQLite file. Docker Compose sets
    ``USE_SQLITE=false`` and a PostgreSQL ``DATABASE_URL``.
    """

    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/inventory_intel"
    database_url_sync: str = "postgresql://postgres:postgres@db:5432/inventory_intel"

    shopify_store_domain: str = "your-store.myshopify.com"
    shopify_access_token: str = "replace-me"
    shiphero_api_token: str = "replace-me"

    use_sqlite: bool = True
    disable_scheduler: bool = False
    seed_on_start: bool = False

    secret_key: str = "change-me"
    cors_origins: str = (
        "http://localhost:3000,http://localhost:5173,http://localhost:8080"
    )
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def cors_origin_list(self) -> list[str]:
        """Origins allowed to call the API from a browser."""
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


def is_placeholder_secret(value: str | None) -> bool:
    """True when a token was left at a sample value and must not be sent."""
    return (value or "").strip().lower() in _PLACEHOLDER_SECRETS


@lru_cache
def get_settings() -> Settings:
    """Return the process settings, cached after the first read."""
    return Settings()
