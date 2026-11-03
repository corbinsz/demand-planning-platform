"""Shopify OAuth install. The merchant approves read-only scopes.

The app credentials (API key and secret) belong to the software owner,
not to the merchant. The merchant's access token comes back from Shopify
and is stored encrypted on that merchant's workspace.
"""

import re

import httpx

from app.config import get_settings
from app.services.credentials import SHOPIFY_SCOPES

_SHOP = re.compile(r"^[a-z0-9][a-z0-9\-]*\.myshopify\.com$")


def normalize_shop(shop: str) -> str:
    value = (shop or "").strip().lower()
    value = value.replace("https://", "").replace("http://", "").split("/")[0]
    if value and not value.endswith(".myshopify.com") and "." not in value:
        value = f"{value}.myshopify.com"
    if not _SHOP.match(value):
        raise ValueError("Use the shop's myshopify.com domain, for example northline.myshopify.com.")
    return value


def authorize_url(*, shop: str, state: str) -> str:
    settings = get_settings()
    if not settings.shopify_app_configured():
        raise RuntimeError("Shopify app credentials are not configured on this server.")
    redirect = settings.public_app_url.rstrip("/") + "/api/integrations/shopify/callback"
    scope = SHOPIFY_SCOPES
    return (
        f"https://{shop}/admin/oauth/authorize"
        f"?client_id={settings.shopify_api_key}"
        f"&scope={scope}"
        f"&redirect_uri={redirect}"
        f"&state={state}"
    )


async def exchange_code(*, shop: str, code: str) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"https://{shop}/admin/oauth/access_token",
            json={
                "client_id": settings.shopify_api_key,
                "client_secret": settings.shopify_api_secret,
                "code": code,
            },
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Shopify token exchange failed (HTTP {response.status_code}).")
    data = response.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError("Shopify did not return an access token.")
    granted = data.get("scope") or SHOPIFY_SCOPES
    # Refuse the install if Shopify handed us a write scope we did not ask for
    # and the granted set is missing the reads we need. Extra writes are
    # dropped by not using them; we still record only the read scopes we need
    # if they are present.
    needed = set(SHOPIFY_SCOPES.split(","))
    granted_set = {s.strip() for s in granted.split(",") if s.strip()}
    if not needed.issubset(granted_set):
        missing = ", ".join(sorted(needed - granted_set))
        raise RuntimeError(f"Shopify did not grant the read scopes we need ({missing}).")
    return {"access_token": token, "scope": ",".join(sorted(needed & granted_set))}
