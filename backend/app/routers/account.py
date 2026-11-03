"""Delete imported data or the whole account. Requires the owner to retype their email."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import Ctx, require_user
from app.services.deletion import delete_account, delete_workspace_data

router = APIRouter()


class ConfirmDelete(BaseModel):
    confirm: str = Field(min_length=3, max_length=320)


@router.delete("/data")
async def wipe_data(body: ConfirmDelete, ctx: Ctx = Depends(require_user), db: AsyncSession = Depends(get_db)):
    if ctx.user is None or body.confirm.strip().lower() != ctx.user.email:
        raise HTTPException(status_code=422, detail="Type your account email to confirm.")
    counts = await delete_workspace_data(db, ctx.workspace_id)
    return {"deleted": True, "counts": counts}


@router.delete("")
async def wipe_account(body: ConfirmDelete, ctx: Ctx = Depends(require_user), db: AsyncSession = Depends(get_db)):
    if ctx.user is None or body.confirm.strip().lower() != ctx.user.email:
        raise HTTPException(status_code=422, detail="Type your account email to confirm.")
    counts = await delete_account(db, ctx.workspace_id)
    return {"deleted": True, "counts": counts}
