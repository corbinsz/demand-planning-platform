"""Delete one brand's data.

Order matters because line items point at orders. Credentials and share
links go too, so a deletion actually removes access, not just the catalog.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    AuditLog,
    IntegrationCredential,
    InventorySnapshot,
    JobLog,
    OAuthState,
    Order,
    OrderLineItem,
    Product,
    PromotionalPeriod,
    ReorderRule,
    ShareLink,
    User,
    Workspace,
)
from app.services.forecasting import invalidate_forecast_cache

_BUSINESS_TABLES = (
    OrderLineItem,
    Order,
    InventorySnapshot,
    ReorderRule,
    PromotionalPeriod,
    ShareLink,
    IntegrationCredential,
    OAuthState,
    Product,
    JobLog,
    AuditLog,
)


async def delete_workspace_data(session: AsyncSession, workspace_id: int) -> dict:
    """Remove imported and derived data. Keep the login and the empty workspace."""
    counts = {}
    for model in _BUSINESS_TABLES:
        result = await session.execute(delete(model).where(model.workspace_id == workspace_id))
        counts[model.__tablename__] = int(getattr(result, "rowcount", 0) or 0)
    invalidate_forecast_cache(workspace_id)
    return counts


async def delete_account(session: AsyncSession, workspace_id: int) -> dict:
    """Remove the workspace, its users, and every row that belonged to it."""
    counts = await delete_workspace_data(session, workspace_id)
    users = await session.execute(delete(User).where(User.workspace_id == workspace_id))
    counts["users"] = int(getattr(users, "rowcount", 0) or 0)
    workspaces = await session.execute(delete(Workspace).where(Workspace.id == workspace_id))
    counts["workspaces"] = int(getattr(workspaces, "rowcount", 0) or 0)
    invalidate_forecast_cache(workspace_id)
    return counts


async def workspace_row_counts(session: AsyncSession, workspace_id: int) -> dict:
    counts = {}
    for model in (Product, Order, OrderLineItem, InventorySnapshot):
        value = await session.scalar(
            select(func.count()).select_from(model).where(model.workspace_id == workspace_id)
        )
        counts[model.__tablename__] = int(value or 0)
    return counts
