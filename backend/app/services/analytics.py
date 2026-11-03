"""ABC classification, dead stock, and excess stock for one workspace."""

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import and_, func, select

from app.database import async_session
from app.models.models import Order, OrderLineItem, Product
from app.services.stock import summed_stock
from app.timeutil import utcnow_naive

logger = logging.getLogger(__name__)


@dataclass
class ABCItem:
    sku: str
    title: str
    total_revenue: float
    total_units: int
    pct_of_revenue: float
    cumulative_pct: float
    abc_class: str
    current_stock: int
    days_of_stock: float | None
    daily_velocity: float


@dataclass
class DeadStockItem:
    sku: str
    title: str
    current_stock: int
    inventory_value: float
    last_sold_date: str | None
    days_since_last_sale: int | None
    total_units_sold_90d: int
    daily_velocity: float
    abc_class: str
    recommendation: str


@dataclass
class ExcessStockItem:
    sku: str
    title: str
    current_stock: int
    daily_velocity: float
    days_of_stock: float
    excess_units: int
    excess_value: float
    target_days: int
    abc_class: str
    recommendation: str


def classify_abc(cumulative_before: float) -> str:
    """Class is based on the share *before* this SKU is added.

    A product that is most of revenue stays in A. The old check happened
    after adding the share, so a 90% hero was labeled B.
    """
    if cumulative_before < 80:
        return "A"
    if cumulative_before < 95:
        return "B"
    return "C"


async def compute_abc_classification(workspace_id: int, days: int = 90) -> list[ABCItem]:
    cutoff = utcnow_naive() - timedelta(days=days)
    async with async_session() as session:
        result = await session.execute(
            select(
                OrderLineItem.sku,
                func.sum(OrderLineItem.quantity * OrderLineItem.price).label("revenue"),
                func.sum(OrderLineItem.quantity).label("units"),
            )
            .join(
                Order,
                and_(
                    Order.workspace_id == OrderLineItem.workspace_id,
                    Order.order_id == OrderLineItem.order_id,
                ),
            )
            .where(OrderLineItem.workspace_id == workspace_id, Order.created_at >= cutoff)
            .group_by(OrderLineItem.sku)
            .order_by(func.sum(OrderLineItem.quantity * OrderLineItem.price).desc())
        )
        rows = result.all()
        if not rows:
            return []
        products = await session.execute(
            select(Product.sku, Product.title).where(Product.workspace_id == workspace_id)
        )
        title_map = {r[0]: r[1] for r in products.all()}
        stock_map = await summed_stock(session, workspace_id, "shiphero")

    total_revenue = sum(float(r[1] or 0) for r in rows)
    if total_revenue <= 0:
        return []

    items = []
    cumulative = 0.0
    for sku, revenue, units in rows:
        rev = float(revenue or 0)
        qty = int(units or 0)
        pct = (rev / total_revenue) * 100
        abc_class = classify_abc(cumulative)
        cumulative += pct
        daily_velocity = round(qty / max(days, 1), 2)
        current_stock = int(stock_map.get(sku, {}).get("available") or 0)
        days_of_stock = round(current_stock / daily_velocity, 1) if daily_velocity > 0 else None
        items.append(ABCItem(
            sku=sku,
            title=title_map.get(sku, "Unknown"),
            total_revenue=round(rev, 2),
            total_units=qty,
            pct_of_revenue=round(pct, 2),
            cumulative_pct=round(cumulative, 2),
            abc_class=abc_class,
            current_stock=max(current_stock, 0),
            days_of_stock=days_of_stock,
            daily_velocity=daily_velocity,
        ))
    return items


async def abc_summary(workspace_id: int, days: int = 90) -> dict:
    items = await compute_abc_classification(workspace_id, days=days)
    summary = {
        "A": {"count": 0, "revenue": 0.0, "units": 0},
        "B": {"count": 0, "revenue": 0.0, "units": 0},
        "C": {"count": 0, "revenue": 0.0, "units": 0},
    }
    for item in items:
        bucket = summary[item.abc_class]
        bucket["count"] += 1
        bucket["revenue"] += item.total_revenue
        bucket["units"] += item.total_units
    total_skus = len(items)
    for bucket in summary.values():
        bucket["revenue"] = round(bucket["revenue"], 2)
        bucket["pct_of_skus"] = round((bucket["count"] / total_skus) * 100, 1) if total_skus else 0
    return {"summary": summary, "total_skus": total_skus, "items": items}


async def dead_stock_report(workspace_id: int, no_sale_days: int = 60, min_stock: int = 1) -> list[DeadStockItem]:
    now = utcnow_naive()
    cutoff_90d = now - timedelta(days=90)
    async with async_session() as session:
        stock_map = await summed_stock(session, workspace_id, "shiphero")
        stocked = {sku: row for sku, row in stock_map.items() if int(row["available"]) >= min_stock}
        if not stocked:
            return []
        skus = list(stocked.keys())
        last_sale = await session.execute(
            select(OrderLineItem.sku, func.max(Order.created_at))
            .join(Order, and_(Order.workspace_id == OrderLineItem.workspace_id, Order.order_id == OrderLineItem.order_id))
            .where(OrderLineItem.workspace_id == workspace_id, OrderLineItem.sku.in_(skus))
            .group_by(OrderLineItem.sku)
        )
        last_sale_map = {r[0]: r[1] for r in last_sale.all()}
        sold_90d = await session.execute(
            select(OrderLineItem.sku, func.sum(OrderLineItem.quantity))
            .join(Order, and_(Order.workspace_id == OrderLineItem.workspace_id, Order.order_id == OrderLineItem.order_id))
            .where(
                OrderLineItem.workspace_id == workspace_id,
                Order.created_at >= cutoff_90d,
                OrderLineItem.sku.in_(skus),
            )
            .group_by(OrderLineItem.sku)
        )
        sold_map = {r[0]: int(r[1] or 0) for r in sold_90d.all()}
        products = await session.execute(
            select(Product.sku, Product.title, Product.cost_price).where(
                Product.workspace_id == workspace_id, Product.sku.in_(skus)
            )
        )
        title_map = {}
        cost_map = {}
        for sku, title, cost in products.all():
            title_map[sku] = title
            cost_map[sku] = float(cost or 0)

    abc_items = await compute_abc_classification(workspace_id)
    abc_map = {item.sku: item.abc_class for item in abc_items}

    found = []
    for sku, row in stocked.items():
        stock = int(row["available"])
        last_date = last_sale_map.get(sku)
        if last_date is not None:
            if getattr(last_date, "tzinfo", None):
                last_date = last_date.replace(tzinfo=None)
            days_since = (now - last_date).days
        else:
            days_since = None
        units_90d = sold_map.get(sku, 0)
        velocity = round(units_90d / 90, 2)
        is_dead = days_since is None or days_since >= no_sale_days
        is_slow = velocity < 0.033 and stock > 10
        if not is_dead and not is_slow:
            continue
        value = round(stock * cost_map.get(sku, 0), 2)
        if days_since is None or days_since > 180:
            recommendation = "Liquidate or write off"
        elif days_since > 90:
            recommendation = "Deep discount or bundle"
        elif days_since > 60:
            recommendation = "Run promotion"
        elif is_slow:
            recommendation = "Monitor — slow mover"
        else:
            recommendation = "Review pricing"
        found.append(DeadStockItem(
            sku=sku,
            title=title_map.get(sku, "Unknown"),
            current_stock=stock,
            inventory_value=value,
            last_sold_date=last_date.isoformat() if last_date else None,
            days_since_last_sale=days_since,
            total_units_sold_90d=units_90d,
            daily_velocity=velocity,
            abc_class=abc_map.get(sku, "C"),
            recommendation=recommendation,
        ))
    found.sort(key=lambda item: item.inventory_value, reverse=True)
    logger.info("Dead stock workspace %s: %s SKUs", workspace_id, len(found))
    return found


async def excess_stock_report(workspace_id: int, target_days_of_stock: int = 90) -> list[ExcessStockItem]:
    cutoff = utcnow_naive() - timedelta(days=90)
    async with async_session() as session:
        stock_map = await summed_stock(session, workspace_id, "shiphero")
        velocity_result = await session.execute(
            select(OrderLineItem.sku, func.sum(OrderLineItem.quantity))
            .join(Order, and_(Order.workspace_id == OrderLineItem.workspace_id, Order.order_id == OrderLineItem.order_id))
            .where(OrderLineItem.workspace_id == workspace_id, Order.created_at >= cutoff)
            .group_by(OrderLineItem.sku)
        )
        velocity_map = {r[0]: round(int(r[1] or 0) / 90, 2) for r in velocity_result.all()}
        products = await session.execute(
            select(Product.sku, Product.title, Product.cost_price).where(Product.workspace_id == workspace_id)
        )
        title_map = {}
        cost_map = {}
        for sku, title, cost in products.all():
            title_map[sku] = title
            cost_map[sku] = float(cost or 0)

    abc_map = {item.sku: item.abc_class for item in await compute_abc_classification(workspace_id)}
    items = []
    for sku, row in stock_map.items():
        stock = max(int(row["available"]), 0)
        velocity = velocity_map.get(sku, 0)
        if velocity <= 0:
            continue
        days_of_stock = round(stock / velocity, 1)
        target_stock = int(velocity * target_days_of_stock)
        excess = stock - target_stock
        if excess <= 0:
            continue
        abc = abc_map.get(sku, "C")
        if days_of_stock > 365:
            recommendation = "Aggressive markdown or liquidate"
        elif days_of_stock > 180:
            recommendation = "Reduce future POs" if abc == "A" else "Bundle with fast movers or discount"
        elif abc == "A":
            recommendation = "Pause reorders"
        elif abc == "B":
            recommendation = "Run promotion"
        else:
            recommendation = "Consider markdown"
        items.append(ExcessStockItem(
            sku=sku,
            title=title_map.get(sku, "Unknown"),
            current_stock=stock,
            daily_velocity=velocity,
            days_of_stock=days_of_stock,
            excess_units=excess,
            excess_value=round(excess * cost_map.get(sku, 0), 2),
            target_days=target_days_of_stock,
            abc_class=abc,
            recommendation=recommendation,
        ))
    items.sort(key=lambda item: item.excess_value, reverse=True)
    return items
