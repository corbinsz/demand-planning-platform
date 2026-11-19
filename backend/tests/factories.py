"""Insert a few rows into the test database without going through HTTP."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.models import (
    InventorySnapshot,
    Order,
    OrderLineItem,
    Product,
    ReorderRule,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tests.support import DB_PATH

_engine = create_engine(f"sqlite:///{DB_PATH}")
_ids = {"snap": 0, "line": 0, "order": 0}


def _session() -> Session:
    return Session(_engine)


def add_product(
    sku: str, title: str, cost: str = "10.00", parent_sku: str | None = None
) -> None:
    """Insert one product."""
    with _session() as session:
        session.add(
            Product(
                sku=sku,
                title=title,
                cost_price=Decimal(cost),
                parent_sku=parent_sku,
            )
        )
        session.commit()


def add_order(
    sku_lines: list[tuple[str, int, str]],
    total: str,
    when: datetime | None = None,
) -> str:
    """Insert one order and its line items. ``sku_lines`` is (sku, qty, price)."""
    _ids["order"] += 1
    order_id = f"T-ORD-{_ids['order']}"
    created = when or (datetime.now(UTC) - timedelta(days=1))
    with _session() as session:
        session.add(
            Order(
                order_id=order_id,
                shopify_order_id=f"T-SHP-{_ids['order']}",
                created_at=created,
                total_price=Decimal(total),
            )
        )
        for sku, quantity, price in sku_lines:
            _ids["line"] += 1
            session.add(
                OrderLineItem(
                    line_item_id=f"T-LI-{_ids['line']}",
                    order_id=order_id,
                    sku=sku,
                    quantity=quantity,
                    price=Decimal(price),
                )
            )
        session.commit()
    return order_id


def add_snapshot(
    sku: str,
    *,
    source: str,
    warehouse: str,
    on_hand: int,
    available: int | None = None,
    allocated: int = 0,
    when: datetime | None = None,
) -> None:
    """Insert one inventory snapshot. Call older rows first so ids stay ordered."""
    _ids["snap"] += 1
    sellable = on_hand if available is None else available
    with _session() as session:
        session.add(
            InventorySnapshot(
                snapshot_id=f"T-SNAP-{_ids['snap']}",
                sku=sku,
                quantity_on_hand=on_hand,
                quantity_allocated=allocated,
                quantity_available=sellable,
                warehouse=warehouse,
                source=source,
                recorded_at=when or datetime.now(UTC),
            )
        )
        session.commit()


def add_rule(
    sku: str,
    *,
    reorder_point: int = 10,
    reorder_quantity: int = 20,
    lead_time_days: int = 14,
    safety_stock: int = 0,
) -> None:
    """Insert one reorder rule."""
    with _session() as session:
        session.add(
            ReorderRule(
                sku=sku,
                reorder_point=reorder_point,
                reorder_quantity=reorder_quantity,
                lead_time_days=lead_time_days,
                safety_stock=safety_stock,
            )
        )
        session.commit()
