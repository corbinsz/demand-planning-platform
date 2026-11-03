"""Load and save per-workspace Shopify and ShipHero credentials.

Environment tokens are a single-brand fallback only. They are ignored as
soon as a second workspace exists, so one server cannot accidentally
apply Brand A's token to Brand B.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.models import IntegrationCredential, Workspace
from app.security import decrypt_secret, encrypt_secret
from app.timeutil import utcnow_naive

# Read-only Shopify scopes. Do not add write scopes.
SHOPIFY_SCOPES = "read_products,read_orders,read_inventory,read_locations"


@dataclass
class ShopifyAuth:
    domain: str
    token: str
    scopes: str
    source: str  # workspace | env


@dataclass
class ShipHeroAuth:
    access_token: str
    source: str


async def _env_fallback_allowed(session: AsyncSession) -> bool:
    settings = get_settings()
    if not settings.allow_env_credentials:
        return False
    count = await session.scalar(select(func.count(Workspace.id)))
    return int(count or 0) <= 1


def _load_row_token(row: IntegrationCredential, field: str) -> str | None:
    raw = getattr(row, field)
    if not raw:
        return None
    return decrypt_secret(raw)


async def get_shopify_auth(session: AsyncSession, workspace_id: int) -> ShopifyAuth | None:
    result = await session.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.workspace_id == workspace_id,
            IntegrationCredential.provider == "shopify",
            IntegrationCredential.status == "connected",
        )
    )
    row = result.scalar_one_or_none()
    if row and row.access_token_enc and row.shop_domain:
        try:
            token = _load_row_token(row, "access_token_enc")
        except ValueError:
            return None
        if token:
            return ShopifyAuth(
                domain=row.shop_domain,
                token=token,
                scopes=row.scopes or SHOPIFY_SCOPES,
                source="workspace",
            )
    if await _env_fallback_allowed(session):
        settings = get_settings()
        if settings.shopify_env_configured():
            return ShopifyAuth(
                domain=settings.shopify_store_domain.strip(),
                token=settings.shopify_access_token.strip(),
                scopes=SHOPIFY_SCOPES,
                source="env",
            )
    return None


async def get_shiphero_auth(session: AsyncSession, workspace_id: int) -> ShipHeroAuth | None:
    result = await session.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.workspace_id == workspace_id,
            IntegrationCredential.provider == "shiphero",
            IntegrationCredential.status == "connected",
        )
    )
    row = result.scalar_one_or_none()
    if row and row.access_token_enc:
        try:
            token = _load_row_token(row, "access_token_enc")
        except ValueError:
            token = None
        expired = row.access_expires_at is not None and row.access_expires_at <= utcnow_naive()
        if token and not expired:
            return ShipHeroAuth(access_token=token, source="workspace")
        if row.refresh_token_enc:
            try:
                refresh = decrypt_secret(row.refresh_token_enc)
            except ValueError:
                refresh = None
            if refresh:
                from app.services.shiphero_auth import refresh_access_token

                try:
                    fresh = await refresh_access_token(refresh)
                except Exception:
                    row.status = "error"
                    row.last_error = "ShipHero refresh failed. Reconnect the refresh token."
                    return None
                row.access_token_enc = encrypt_secret(fresh["access_token"])
                row.access_expires_at = utcnow_naive() + timedelta(seconds=int(fresh.get("expires_in") or 86400))
                row.status = "connected"
                row.last_error = None
                row.updated_at = utcnow_naive()
                return ShipHeroAuth(access_token=fresh["access_token"], source="workspace")
    if await _env_fallback_allowed(session):
        settings = get_settings()
        if settings.shiphero_env_configured():
            return ShipHeroAuth(access_token=settings.shiphero_api_token.strip(), source="env")
    return None


async def save_shopify_token(
    session: AsyncSession,
    *,
    workspace_id: int,
    domain: str,
    access_token: str,
    scopes: str,
) -> None:
    await _upsert(
        session,
        workspace_id=workspace_id,
        provider="shopify",
        shop_domain=domain,
        access_token=access_token,
        refresh_token=None,
        expires_at=None,
        scopes=scopes,
    )


async def save_shiphero_tokens(
    session: AsyncSession,
    *,
    workspace_id: int,
    access_token: str,
    refresh_token: str,
    expires_in: int,
) -> None:
    await _upsert(
        session,
        workspace_id=workspace_id,
        provider="shiphero",
        shop_domain=None,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=utcnow_naive() + timedelta(seconds=max(int(expires_in or 0), 60)),
        scopes="read_inventory read_purchase_orders read_inventory_changes",
    )


async def _upsert(
    session: AsyncSession,
    *,
    workspace_id: int,
    provider: str,
    shop_domain: str | None,
    access_token: str,
    refresh_token: str | None,
    expires_at,
    scopes: str,
) -> None:
    result = await session.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.workspace_id == workspace_id,
            IntegrationCredential.provider == provider,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = IntegrationCredential(workspace_id=workspace_id, provider=provider)
        session.add(row)
    row.shop_domain = shop_domain
    row.access_token_enc = encrypt_secret(access_token)
    row.refresh_token_enc = encrypt_secret(refresh_token) if refresh_token else None
    row.access_expires_at = expires_at
    row.scopes = scopes
    row.status = "connected"
    row.last_error = None
    row.updated_at = utcnow_naive()
    if row.connected_at is None:
        row.connected_at = utcnow_naive()


async def disconnect(session: AsyncSession, workspace_id: int, provider: str) -> bool:
    result = await session.execute(
        select(IntegrationCredential).where(
            IntegrationCredential.workspace_id == workspace_id,
            IntegrationCredential.provider == provider,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    return True


async def public_status(session: AsyncSession, workspace_id: int) -> dict:
    """Connection status safe to show in the browser. Never includes tokens."""
    result = await session.execute(
        select(IntegrationCredential).where(IntegrationCredential.workspace_id == workspace_id)
    )
    rows = {r.provider: r for r in result.scalars().all()}
    settings = get_settings()

    def pack(provider: str, env_ready: bool) -> dict:
        row = rows.get(provider)
        if row is None:
            return {
                "connected": False,
                "source": "env" if env_ready else None,
                "shop_domain": None,
                "scopes": None,
                "status": "not_connected",
                "last_error": None,
            }
        return {
            "connected": row.status == "connected",
            "source": "workspace",
            "shop_domain": row.shop_domain,
            "scopes": row.scopes,
            "status": row.status,
            "last_error": row.last_error,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    env_ok = await _env_fallback_allowed(session)
    return {
        "shopify": pack("shopify", bool(env_ok and settings.shopify_env_configured())),
        "shiphero": pack("shiphero", bool(env_ok and settings.shiphero_env_configured())),
        "shopify_oauth_ready": settings.shopify_app_configured(),
        "shopify_scopes": SHOPIFY_SCOPES,
        "env_fallback_enabled": bool(env_ok),
    }
