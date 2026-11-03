"""Who is calling, and which brand they are allowed to see."""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.models import User, Workspace
from app.security import decode_access_token


@dataclass
class Ctx:
    workspace: Workspace
    user: User | None
    demo_anonymous: bool
    ip: str | None

    @property
    def workspace_id(self) -> int:
        return self.workspace.id

    @property
    def actor(self) -> str:
        if self.user is not None:
            return self.user.email
        return "demo-anonymous"


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return request.client.host
    return None


async def _user_from_token(db: AsyncSession, token: str) -> tuple[User, Workspace] | None:
    payload = decode_access_token(token)
    if not payload:
        return None
    sub = payload.get("sub")
    wid = payload.get("wid")
    if sub is None or wid is None:
        return None
    try:
        user_id = int(sub)
        workspace_id = int(wid)
    except (TypeError, ValueError):
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.workspace_id != workspace_id:
        return None
    ws = await db.get(Workspace, user.workspace_id)
    if ws is None:
        return None
    return user, ws


async def resolve_ctx(request: Request, db: AsyncSession, *, required: bool) -> Ctx | None:
    settings = get_settings()
    ip = _client_ip(request)
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        found = await _user_from_token(db, header.split(" ", 1)[1].strip())
        if found is None:
            raise HTTPException(status_code=401, detail="Sign in again.")
        user, ws = found
        return Ctx(workspace=ws, user=user, demo_anonymous=False, ip=ip)

    if settings.demo_mode:
        result = await db.execute(select(Workspace).where(Workspace.is_demo.is_(True)).limit(1))
        demo = result.scalar_one_or_none()
        if demo is not None:
            return Ctx(workspace=demo, user=None, demo_anonymous=True, ip=ip)

    if required:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return None


async def get_ctx(request: Request, db: AsyncSession = Depends(get_db)) -> Ctx:
    ctx = await resolve_ctx(request, db, required=True)
    assert ctx is not None
    return ctx


async def require_user(ctx: Ctx = Depends(get_ctx)) -> Ctx:
    """Mutations that must not run as the anonymous demo viewer."""
    if ctx.user is None:
        raise HTTPException(status_code=401, detail="Sign in to change this workspace.")
    return ctx
