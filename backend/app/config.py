from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database. Docker sets DATABASE_URL to Postgres. Local SQLite is opt-in.
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/inventory_intel"
    database_url_sync: str = "postgresql://postgres:postgres@db:5432/inventory_intel"
    use_sqlite: bool = False
    sqlite_path: str = ""

    # Optional single-brand fallback. Leave blank. Prefer per-workspace connect.
    # Ignored when more than one workspace exists, so one env token cannot leak
    # into a second brand.
    allow_env_credentials: bool = False
    shopify_store_domain: str = ""
    shopify_access_token: str = ""
    shiphero_api_token: str = ""
    shopify_api_key: str = ""
    shopify_api_secret: str = ""
    shopify_api_version: str = "2026-10"

    # App
    secret_key: str = "change-me"
    token_encryption_key: str = ""
    token_ttl_days: int = 7
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    log_level: str = "INFO"
    demo_mode: bool = False
    auto_seed: bool = False
    scheduler_enabled: bool = True
    warm_forecasts: bool = True
    public_app_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"

    # Weekly email. Leave blank to keep the digest as an in-app preview only.
    # Times in the scheduler are Mountain Time (Utah): Monday 8:00am is 15:00 UTC
    # during standard time. See docs/DEPLOY.md before turning sending on.
    digest_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def shopify_env_configured(self) -> bool:
        token = (self.shopify_access_token or "").strip()
        domain = (self.shopify_store_domain or "").strip()
        if not token or not domain:
            return False
        if token in {"shpat_placeholder", "shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}:
            return False
        if domain.startswith("your-store"):
            return False
        return True

    def shiphero_env_configured(self) -> bool:
        token = (self.shiphero_api_token or "").strip()
        if not token or token in {"placeholder_token", "your_shiphero_bearer_token"}:
            return False
        return True

    def shopify_app_configured(self) -> bool:
        return bool((self.shopify_api_key or "").strip() and (self.shopify_api_secret or "").strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
