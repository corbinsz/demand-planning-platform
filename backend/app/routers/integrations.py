"""Connect Shopify (OAuth) and ShipHero (refresh token) for one workspace."""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.deps import Ctx, get_ctx, require_user
from app.models.models import OAuthState
from app.security import verify_shopify_hmac
from app.services.audit import write_audit
from app.services.credentials import (
    SHOPIFY_SCOPES,
    disconnect,
    get_shiphero_auth,
    get_shopify_auth,
    public_status,
    save_shiphero_tokens,
    save_shopify_token,
)
from app.services.shiphero_auth import refresh_access_token
from app.services.shopify_oauth import authorize_url, exchange_code, normalize_shop
from app.timeutil import utcnow_naive

router = APIRouter()


class ShipHeroConnect(BaseModel):
    refresh_token: str = Field(min_length=8, max_length=4000)


class ShopStart(BaseModel):
    shop: str = Field(min_length=3, max_length=255)


@router.get("/status")
async def integration_status(ctx: Ctx = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    return await public_status(db, ctx.workspace_id)


@router.post("/shopify/start")
async def shopify_start(body: ShopStart, ctx: Ctx = Depends(require_user), db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    if not settings.shopify_app_configured():
        raise HTTPException(
            status_code=400,
            detail=(
                "This server is not set up for Shopify connect yet. "
                "The owner adds SHOPIFY_API_KEY and SHOPIFY_API_SECRET (the app, not a store token). "
                "See the deploy guide."
            ),
        )
    try:
        shop = normalize_shop(body.shop)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    state = secrets.token_urlsafe(24)
    db.add(OAuthState(
        workspace_id=ctx.workspace_id,
        state=state,
        shop_domain=shop,
        expires_at=utcnow_naive() + timedelta(minutes=15),
    ))
    await write_audit(
        db, workspace_id=ctx.workspace_id, actor_email=ctx.actor,
        action="shopify_oauth_start", resource=shop, ip=ctx.ip,
    )
    return {"authorize_url": authorize_url(shop=shop, state=state), "scopes": SHOPIFY_SCOPES}


@router.get("/shopify/callback")
async def shopify_callback(request: Request, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    params = {key: value for key, value in request.query_params.items()}
    if not settings.shopify_app_configured() or not verify_shopify_hmac(params, settings.shopify_api_secret):
        raise HTTPException(status_code=400, detail="Shopify could not be verified. Start the connection again.")
    state = params.get("state") or ""
    shop = params.get("shop") or ""
    code = params.get("code") or ""
    try:
        shop = normalize_shop(shop)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = (await db.execute(select(OAuthState).where(OAuthState.state == state))).scalar_one_or_none()
    if row is None or row.expires_at < utcnow_naive() or row.shop_domain != shop:
        raise HTTPException(status_code=400, detail="This connection link expired. Start again from Connections.")
    workspace_id = row.workspace_id
    await db.delete(row)
    try:
        granted = await exchange_code(shop=shop, code=code)
    except Exception:
        await write_audit(db, workspace_id=workspace_id, actor_email=None, action="shopify_oauth_failed", resource=shop)
        await db.commit()
        raise HTTPException(status_code=400, detail="Shopify did not finish the connection.")
    await save_shopify_token(
        db,
        workspace_id=workspace_id,
        domain=shop,
        access_token=granted["access_token"],
        scopes=granted["scope"],
    )
    await write_audit(db, workspace_id=workspace_id, actor_email=None, action="shopify_connected", resource=shop)
    return RedirectResponse(settings.frontend_url.rstrip("/") + "/connections?shopify=connected")


@router.delete("/shopify")
async def shopify_disconnect(ctx: Ctx = Depends(require_user), db: AsyncSession = Depends(get_db)):
    removed = await disconnect(db, ctx.workspace_id, "shopify")
    await write_audit(db, workspace_id=ctx.workspace_id, actor_email=ctx.actor, action="shopify_disconnected", ip=ctx.ip)
    return {"removed": removed}


@router.post("/shiphero/connect")
async def shiphero_connect(body: ShipHeroConnect, ctx: Ctx = Depends(require_user), db: AsyncSession = Depends(get_db)):
    """Store a refresh token. The ShipHero password is never accepted."""
    try:
        fresh = await refresh_access_token(body.refresh_token.strip())
    except Exception:
        raise HTTPException(status_code=400, detail="ShipHero didn't accept that refresh token.")
    await save_shiphero_tokens(
        db,
        workspace_id=ctx.workspace_id,
        access_token=fresh["access_token"],
        refresh_token=body.refresh_token.strip(),
        expires_in=fresh["expires_in"],
    )
    await write_audit(db, workspace_id=ctx.workspace_id, actor_email=ctx.actor, action="shiphero_connected", ip=ctx.ip)
    return {"connected": True}


@router.delete("/shiphero")
async def shiphero_disconnect(ctx: Ctx = Depends(require_user), db: AsyncSession = Depends(get_db)):
    removed = await disconnect(db, ctx.workspace_id, "shiphero")
    await write_audit(db, workspace_id=ctx.workspace_id, actor_email=ctx.actor, action="shiphero_disconnected", ip=ctx.ip)
    return {"removed": removed}


@router.post("/test/shopify")
async def test_shopify(ctx: Ctx = Depends(require_user), db: AsyncSession = Depends(get_db)):
    auth = await get_shopify_auth(db, ctx.workspace_id)
    if auth is None:
        return {"success": False, "error": "Shopify is not connected for this workspace."}
    import httpx
    url = f"https://{auth.domain}/admin/api/{get_settings().shopify_api_version}/shop.json"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers={"X-Shopify-Access-Token": auth.token})
        if response.status_code != 200:
            return {"success": False, "error": f"Shopify responded with HTTP {response.status_code}."}
        shop = response.json().get("shop", {})
        return {"success": True, "store_name": shop.get("name"), "domain": shop.get("myshopify_domain")}
    except httpx.HTTPError:
        return {"success": False, "error": "Could not reach Shopify."}


@router.post("/test/shiphero")
async def test_shiphero(ctx: Ctx = Depends(require_user), db: AsyncSession = Depends(get_db)):
    auth = await get_shiphero_auth(db, ctx.workspace_id)
    if auth is None:
        return {"success": False, "error": "ShipHero is not connected for this workspace."}
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://public-api.shiphero.com/graphql",
                headers={"Authorization": f"Bearer {auth.access_token}", "Content-Type": "application/json"},
                json={"query": "{ account { id } }"},
            )
        if response.status_code != 200:
            return {"success": False, "error": f"ShipHero responded with HTTP {response.status_code}."}
        data = response.json()
        if data.get("errors"):
            return {"success": False, "error": "ShipHero rejected the token."}
        return {"success": True, "account_id": (data.get("data") or {}).get("account", {}).get("id")}
    except httpx.HTTPError:
        return {"success": False, "error": "Could not reach ShipHero."}
