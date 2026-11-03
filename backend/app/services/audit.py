"""Append-only record of security-relevant actions.

Details must stay free of tokens, passwords, and raw customer payloads.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog
from app.timeutil import utcnow_naive


async def write_audit(
    session: AsyncSession,
    *,
    workspace_id: int | None,
    actor_email: str | None,
    action: str,
    resource: str | None = None,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    if detail and len(detail) > 500:
        detail = detail[:500]
    session.add(
        AuditLog(
            workspace_id=workspace_id,
            actor_email=actor_email,
            action=action,
            resource=resource,
            detail=detail,
            ip=ip,
            created_at=utcnow_naive(),
        )
    )
