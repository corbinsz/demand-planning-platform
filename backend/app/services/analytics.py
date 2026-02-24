import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, and_

from app.database import async_session
from app.models.models import (
    Product,
    Order,
    OrderLineItem,
    InventorySnapshot,
)

logger = logging.getLogger(__name__)


def _latest_stock_subquery():
    """Subquery for the latest snapshot ID per SKU from ShipHero."""
    return (
        select(
            InventorySnapshot.sku,
            func.max(InventorySnapshot.id).label("max_id"),
        )
        .where(InventorySnapshot.source == "shiphero")
        .group_by(InventorySnapshot.sku)
        .subquery()
    )


async def _get_stock_map(session) -> dict[str, int]:
    """Get latest stock per SKU using only the most recent snapshot."""
    latest = _latest_stock_subquery()
    result = await session.execute(
        select(
            InventorySnapshot.sku,
            InventorySnapshot.quantity_available,
        )
        .join(latest, InventorySnapshot.id == latest.c.max_id)
    )
    return {r[0]: int(r[1] or 0) for r in result.all()}


# ---------------------------------------------------------------------------
# ABC Classification
# ---------------------------------------------------------------------------

@dataclass
class ABCItem:
    sku: str
    title: str
    total_revenue: float
    total_units: int
    pct_of_revenue: float
    cumulative_pct: float
    abc_class: str  # A | B | C
    current_stock: int
    days_of_stock: float | None
    daily_velocity: float


async def compute_abc_classification(days: int = 90) -> list[ABCItem]:
    """
    Classify SKUs using revenue-based Pareto (80/15/5) over the last N days.
    A = top 80% of revenue, B = next 15%, C = bottom 5%.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with async_session() as session:
        # Revenue and units per SKU
        result = await session.execute(
            select(
                OrderLineItem.sku,
                func.sum(OrderLineItem.quantity * OrderLineItem.price).label("revenue"),
                func.sum(OrderLineItem.quantity).label("units"),
            )
            .join(Order, OrderLineItem.order_id == Order.order_id)
            .where(Order.created_at >= cutoff)
            .group_by(OrderLineItem.sku)
            .order_by(func.sum(OrderLineItem.quantity * OrderLineItem.price).desc())
        )
        rows = result.all()

        if not rows:
            return []

        # Product titles
        products = await session.execute(select(Product.sku, Product.title))
        title_map = {r[0]: r[1] for r in products.all()}

        # Latest stock per SKU from ShipHero (using latest snapshot only)
        stock_map = await _get_stock_map(session)

    total_revenue = sum(float(r[1] or 0) for r in rows)
    if total_revenue == 0:
        return []

    items = []
    cumulative = 0.0

    for sku, revenue, units in rows:
        rev = float(revenue or 0)
        qty = int(units or 0)
        pct = (rev / total_revenue) * 100
        cumulative += pct

        # ABC thresholds: A=0-80%, B=80-95%, C=95-100%
        if cumulative <= 80:
            abc_class = "A"
        elif cumulative <= 95:
            abc_class = "B"
        else:
            abc_class = "C"

        daily_velocity = round(qty / max(days, 1), 2)
        current_stock = stock_map.get(sku, 0)
        days_of_stock = round(current_stock / daily_velocity, 1) if daily_velocity > 0 else None

        items.append(ABCItem(
            sku=sku,
            title=title_map.get(sku, "Unknown"),
            total_revenue=round(rev, 2),
            total_units=qty,
            pct_of_revenue=round(pct, 2),
            cumulative_pct=round(cumulative, 2),
            abc_class=abc_class,
            current_stock=current_stock,
            days_of_stock=days_of_stock,
            daily_velocity=daily_velocity,
        ))

    logger.info(
        f"ABC classification: {sum(1 for i in items if i.abc_class == 'A')} A, "
        f"{sum(1 for i in items if i.abc_class == 'B')} B, "
        f"{sum(1 for i in items if i.abc_class == 'C')} C"
    )
    return items


async def abc_summary(days: int = 90) -> dict:
    """Return summary counts and revenue by ABC class."""
    items = await compute_abc_classification(days=days)
    summary = {"A": {"count": 0, "revenue": 0, "units": 0},
               "B": {"count": 0, "revenue": 0, "units": 0},
               "C": {"count": 0, "revenue": 0, "units": 0}}
    for item in items:
        c = item.abc_class
        summary[c]["count"] += 1
        summary[c]["revenue"] += item.total_revenue
        summary[c]["units"] += item.total_units

    total_skus = len(items)
    for c in summary:
        summary[c]["revenue"] = round(summary[c]["revenue"], 2)
        summary[c]["pct_of_skus"] = round((summary[c]["count"] / total_skus) * 100, 1) if total_skus else 0

    return {"summary": summary, "total_skus": total_skus, "items": items}


# ---------------------------------------------------------------------------
# Dead Stock Report
# ---------------------------------------------------------------------------

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


async def dead_stock_report(
    no_sale_days: int = 60,
    min_stock: int = 1,
) -> list[DeadStockItem]:
    """
    Identify dead stock: SKUs with inventory on hand but very low or zero
    sales in the last N days.
    """
    now = datetime.now(timezone.utc)
    cutoff_90d = now - timedelta(days=90)

    async with async_session() as session:
        # Latest stock per SKU (only most recent snapshot)
        stock_map = await _get_stock_map(session)
        stocked_skus = {sku: qty for sku, qty in stock_map.items() if qty >= min_stock}

        if not stocked_skus:
            return []

        # Last sale date per SKU
        last_sale = await session.execute(
            select(
                OrderLineItem.sku,
                func.max(Order.created_at).label("last_date"),
            )
            .join(Order, OrderLineItem.order_id == Order.order_id)
            .where(OrderLineItem.sku.in_(list(stocked_skus.keys())))
            .group_by(OrderLineItem.sku)
        )
        last_sale_map = {r[0]: r[1] for r in last_sale.all()}

        # Units sold in last 90 days per SKU
        sold_90d = await session.execute(
            select(
                OrderLineItem.sku,
                func.sum(OrderLineItem.quantity).label("units"),
            )
            .join(Order, OrderLineItem.order_id == Order.order_id)
            .where(
                and_(
                    Order.created_at >= cutoff_90d,
                    OrderLineItem.sku.in_(list(stocked_skus.keys())),
                )
            )
            .group_by(OrderLineItem.sku)
        )
        sold_90d_map = {r[0]: int(r[1] or 0) for r in sold_90d.all()}

        # Average price per SKU (for inventory value estimate)
        avg_price = await session.execute(
            select(
                OrderLineItem.sku,
                func.avg(OrderLineItem.price).label("avg_price"),
            )
            .where(OrderLineItem.sku.in_(list(stocked_skus.keys())))
            .group_by(OrderLineItem.sku)
        )
        price_map = {r[0]: float(r[1] or 0) for r in avg_price.all()}

        # Product titles
        products = await session.execute(
            select(Product.sku, Product.title)
            .where(Product.sku.in_(list(stocked_skus.keys())))
        )
        title_map = {r[0]: r[1] for r in products.all()}

    # Get ABC classification
    abc_items = await compute_abc_classification()
    abc_map = {i.sku: i.abc_class for i in abc_items}

    # Use naive now for comparison with potentially naive DB datetimes
    now_naive = now.replace(tzinfo=None)

    items = []
    for sku, stock in stocked_skus.items():
        last_date = last_sale_map.get(sku)
        if last_date:
            # Normalize to naive UTC for safe comparison
            if hasattr(last_date, 'tzinfo') and last_date.tzinfo:
                last_date_naive = last_date.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                last_date_naive = last_date
            days_since = (now_naive - last_date_naive).days
        else:
            days_since = None  # never sold

        units_90d = sold_90d_map.get(sku, 0)
        velocity = round(units_90d / 90, 2)

        # Filter: dead stock = no sales in N days OR never sold
        is_dead = (days_since is not None and days_since >= no_sale_days) or days_since is None
        # Also include very slow movers: < 1 unit per month with stock > 30 days supply
        is_slow = velocity < 0.033 and stock > 10

        if not is_dead and not is_slow:
            continue

        inv_value = round(stock * price_map.get(sku, 0), 2)

        # Recommendation
        if days_since is None or (days_since is not None and days_since > 180):
            recommendation = "Liquidate or write off"
        elif days_since > 90:
            recommendation = "Deep discount or bundle"
        elif days_since > 60:
            recommendation = "Run promotion"
        elif is_slow:
            recommendation = "Monitor — slow mover"
        else:
            recommendation = "Review pricing"

        items.append(DeadStockItem(
            sku=sku,
            title=title_map.get(sku, "Unknown"),
            current_stock=stock,
            inventory_value=inv_value,
            last_sold_date=last_date.isoformat() if last_date else None,
            days_since_last_sale=days_since,
            total_units_sold_90d=units_90d,
            daily_velocity=velocity,
            abc_class=abc_map.get(sku, "C"),
            recommendation=recommendation,
        ))

    # Sort by inventory value descending (biggest $ at risk first)
    items.sort(key=lambda x: x.inventory_value, reverse=True)

    logger.info(f"Dead stock report: {len(items)} SKUs identified")
    return items


# ---------------------------------------------------------------------------
# Excess Stock Report
# ---------------------------------------------------------------------------

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


async def excess_stock_report(target_days_of_stock: int = 90) -> list[ExcessStockItem]:
    """
    Identify SKUs with more inventory than needed for the target days of stock.
    Excess = current_stock - (daily_velocity * target_days).
    """
    async with async_session() as session:
        # Latest stock per SKU (only most recent snapshot)
        stock_map = await _get_stock_map(session)

        # Sales velocity from last 90 days
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        velocity_result = await session.execute(
            select(
                OrderLineItem.sku,
                func.sum(OrderLineItem.quantity).label("units"),
            )
            .join(Order, OrderLineItem.order_id == Order.order_id)
            .where(Order.created_at >= cutoff)
            .group_by(OrderLineItem.sku)
        )
        velocity_map = {r[0]: round(int(r[1] or 0) / 90, 2) for r in velocity_result.all()}

        # Average price
        avg_price = await session.execute(
            select(
                OrderLineItem.sku,
                func.avg(OrderLineItem.price).label("avg_price"),
            )
            .group_by(OrderLineItem.sku)
        )
        price_map = {r[0]: float(r[1] or 0) for r in avg_price.all()}

        # Titles
        products = await session.execute(select(Product.sku, Product.title))
        title_map = {r[0]: r[1] for r in products.all()}

    # ABC
    abc_items = await compute_abc_classification()
    abc_map = {i.sku: i.abc_class for i in abc_items}

    items = []
    for sku, stock in stock_map.items():
        velocity = velocity_map.get(sku, 0)
        if velocity <= 0:
            continue  # handled by dead stock report

        days_of_stock = round(stock / velocity, 1)
        target_stock = int(velocity * target_days_of_stock)
        excess = stock - target_stock

        if excess <= 0:
            continue  # not excess

        excess_value = round(excess * price_map.get(sku, 0), 2)
        abc = abc_map.get(sku, "C")

        # Recommendation based on ABC class and excess severity
        if days_of_stock > 365:
            recommendation = "Aggressive markdown or liquidate"
        elif days_of_stock > 180:
            if abc == "A":
                recommendation = "Reduce future POs"
            else:
                recommendation = "Bundle with fast movers or discount"
        else:
            if abc == "A":
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
            excess_value=excess_value,
            target_days=target_days_of_stock,
            abc_class=abc,
            recommendation=recommendation,
        ))

    # Sort by excess value descending
    items.sort(key=lambda x: x.excess_value, reverse=True)

    logger.info(f"Excess stock report: {len(items)} SKUs, ${sum(i.excess_value for i in items):,.2f} total excess value")
    return items
