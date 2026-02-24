from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/inventory_intel"
    database_url_sync: str = "postgresql://postgres:postgres@db:5432/inventory_intel"

    # Shopify
    shopify_store_domain: str = "your-store.myshopify.com"
    shopify_access_token: str = "shpat_placeholder"

    # ShipHero
    shiphero_api_token: str = "placeholder_token"

    # Local dev
    use_sqlite: bool = True

    # App
    secret_key: str = "change-me"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
