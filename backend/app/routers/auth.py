"""Accounts. One login owns one workspace (one brand)."""

import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import Ctx, get_ctx, resolve_ctx
from app.models.models import User, Workspace
from app.security import (
    create_access_token,
    hash_password,
    password_problem,
    verify_password,
)
from app.services.audit import write_audit

router = APIRouter()

_attempts: dict[str, list[float]] = defaultdict(list)


class RegisterBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)
    workspace_name: str = Field(min_length=2, max_length=200)


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


def _normal_email(value: str) -> str:
    email = value.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return email


def _slug(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return (cleaned or "brand")[:60]


def _limited(ip: str) -> bool:
    now = time.time()
    recent = [stamp for stamp in _attempts[ip] if now - stamp < 60]
    _attempts[ip] = recent
    return len(recent) >= 8


@router.get("/session")
async def session(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = await resolve_ctx(request, db, required=False)
    if ctx is None:
        raise HTTPException(status_code=401, detail="Sign in required.")
    return _public_session(ctx)


def _public_session(ctx: Ctx) -> dict:
    return {
        "authenticated": ctx.user is not None,
        "demo_anonymous": ctx.demo_anonymous,
        "demo_mode": ctx.demo_anonymous or ctx.workspace.is_demo,
        "email": ctx.user.email if ctx.user else None,
        "workspace": {
            "id": ctx.workspace.id,
            "name": ctx.workspace.name,
            "slug": ctx.workspace.slug,
            "is_demo": ctx.workspace.is_demo,
        },
    }


@router.post("/register")
async def register(body: RegisterBody, request: Request, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if _limited(ip):
        raise HTTPException(status_code=429, detail="Too many attempts. Wait a minute and try again.")
    email = _normal_email(body.email)
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    taken = (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none()
    if taken:
        raise HTTPException(status_code=409, detail="That email is already registered.")
    slug = _slug(body.workspace_name)
    suffix = 1
    base = slug
    while (await db.execute(select(Workspace.id).where(Workspace.slug == slug))).scalar_one_or_none():
        suffix += 1
        slug = f"{base}-{suffix}"
    workspace = Workspace(name=body.workspace_name.strip(), slug=slug, is_demo=False)
    db.add(workspace)
    await db.flush()
    user = User(
        workspace_id=workspace.id,
        email=email,
        password_hash=hash_password(body.password),
        role="owner",
    )
    db.add(user)
    await db.flush()
    await write_audit(db, workspace_id=workspace.id, actor_email=email, action="register", ip=ip)
    token = create_access_token(user_id=user.id, workspace_id=workspace.id, email=email)
    return {"token": token, "session": _public_session(Ctx(workspace, user, False, ip))}


@router.post("/login")
async def login(body: LoginBody, request: Request, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if _limited(ip):
        raise HTTPException(status_code=429, detail="Too many attempts. Wait a minute and try again.")
    _attempts[ip].append(time.time())
    email = _normal_email(body.email)
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        await write_audit(db, workspace_id=user.workspace_id if user else None, actor_email=email, action="login_failure", ip=ip)
        await db.commit()
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    workspace = await db.get(Workspace, user.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    await write_audit(db, workspace_id=workspace.id, actor_email=email, action="login_success", ip=ip)
    token = create_access_token(user_id=user.id, workspace_id=workspace.id, email=email)
    return {"token": token, "session": _public_session(Ctx(workspace, user, False, ip))}


@router.get("/me")
async def me(ctx: Ctx = Depends(get_ctx)):
    return _public_session(ctx)
