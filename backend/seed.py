"""Load a synthetic demo catalog.

The brand, product names, colorways, SKUs, warehouses, and prices are
invented for this personal project. They are not a real company and they
are not copied from a real catalog.

Run from the backend directory:

    python -m seed
    python -m seed --if-empty
"""

import argparse
import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.database import async_session, init_db
from app.logging_config import configure_logging
from app.models.models import (
    InventorySnapshot,
    Order,
    OrderLineItem,
    Product,
    PromotionalPeriod,
    ReorderRule,
)
from sqlalchemy import func, select, text

logger = logging.getLogger(__name__)

DEMO_BRAND = "Veldt & Ember"
SKU_PREFIX = "VE-"

SHOE_SIZES = ["US 7", "US 8", "US 9", "US 10", "US 11", "US 12", "US 13"]
APPAREL_SIZES = ["S", "M", "L", "XL", "XXL"]

SHOE_COLORWAYS = {
    "Fog Glass": "FG",
    "Kiln Copper": "KC",
    "Paper Moss": "PM",
    "Ink Dune": "ID",
}
TEE_COLORS = {"Pebble": "PB", "Spruce": "SP"}
CREW_COLORS = {"Char": "CH", "Oat": "OT"}
SOCK_COLORS = {"Cloud": "CL", "Pine": "PN", "Sandbar": "SB"}
CUP_COLORS = {"Tin": "TN", "Rust": "RS", "Cream": "CR"}

WAREHOUSES = ["Demo North Warehouse", "Demo South Warehouse"]

COLORWAY_WEIGHT = {
    "Fog Glass": 1.8,
    "Kiln Copper": 1.3,
    "Paper Moss": 0.8,
    "Ink Dune": 0.6,
}
SHOE_SIZE_WEIGHT = {
    "US 7": 0.08,
    "US 8": 0.14,
    "US 9": 0.22,
    "US 10": 0.22,
    "US 11": 0.16,
    "US 12": 0.11,
    "US 13": 0.07,
}
APPAREL_SIZE_WEIGHT = {"S": 0.12, "M": 0.28, "L": 0.30, "XL": 0.20, "XXL": 0.10}


def _build_catalog() -> list[dict]:
    """Return the invented Veldt & Ember catalog."""
    products: list[dict] = []

    for colorway, code in SHOE_COLORWAYS.items():
        parent = f"VE-SH-{code}"
        for size in SHOE_SIZES:
            size_code = size.replace("US ", "")
            products.append(
                {
                    "sku": f"{parent}-{size_code}",
                    "title": f'Veldt Trail Shoe "{colorway}" - {size}',
                    "parent_sku": parent,
                    "cost_price": Decimal("46.00"),
                    "retail_price": Decimal("128.00"),
                    "category": "footwear",
                    "colorway": colorway,
                    "size_code": size,
                }
            )

    for color, code in TEE_COLORS.items():
        for size in APPAREL_SIZES:
            products.append(
                {
                    "sku": f"VE-TEE-{code}-{size}",
                    "title": f"Ember Day Tee - {color} / {size}",
                    "parent_sku": "VE-TEE",
                    "cost_price": Decimal("14.00"),
                    "retail_price": Decimal("42.00"),
                    "category": "apparel",
                    "colorway": color,
                    "size_code": size,
                }
            )

    for color, code in CREW_COLORS.items():
        for size in APPAREL_SIZES:
            products.append(
                {
                    "sku": f"VE-CRW-{code}-{size}",
                    "title": f"Ridge Crewneck - {color} / {size}",
                    "parent_sku": "VE-CRW",
                    "cost_price": Decimal("28.00"),
                    "retail_price": Decimal("86.00"),
                    "category": "apparel",
                    "colorway": color,
                    "size_code": size,
                }
            )

    for color, code in SOCK_COLORS.items():
        products.append(
            {
                "sku": f"VE-SOX-{code}",
                "title": f"Wool Ankle Socks 3-Pack - {color}",
                "parent_sku": "VE-SOX",
                "cost_price": Decimal("6.00"),
                "retail_price": Decimal("18.00"),
                "category": "accessories",
                "colorway": color,
                "size_code": "OS",
            }
        )

    products.append(
        {
            "sku": "VE-TOT-NT",
            "title": "Canvas Market Tote - Natural",
            "parent_sku": "VE-TOT",
            "cost_price": Decimal("8.00"),
            "retail_price": Decimal("32.00"),
            "category": "accessories",
            "colorway": "Natural",
            "size_code": "OS",
        }
    )

    for color, code in CUP_COLORS.items():
        products.append(
            {
                "sku": f"VE-CUP-{code}",
                "title": f"Enamel Camp Cup 12oz - {color}",
                "parent_sku": "VE-CUP",
                "cost_price": Decimal("7.00"),
                "retail_price": Decimal("24.00"),
                "category": "accessories",
                "colorway": color,
                "size_code": "OS",
            }
        )

    return products


def _product_weight(product: dict) -> float:
    """Relative demand weight for one variant."""
    if product["category"] == "footwear":
        return COLORWAY_WEIGHT.get(product["colorway"], 1.0) * SHOE_SIZE_WEIGHT.get(
            product["size_code"], 0.1
        )
    if product["category"] == "apparel":
        size_weight = APPAREL_SIZE_WEIGHT.get(product["size_code"], 0.15)
        if product["title"].startswith("Ember Day Tee"):
            return size_weight * 1.4
        return size_weight * 0.8
    if "Socks" in product["title"]:
        return 1.2
    if "Tote" in product["title"]:
        return 0.7
    return 0.5


def _seasonal_multiplier(moment: datetime) -> float:
    """A simple retail calendar: a January bump, a summer bump, a late-year bump."""
    month = moment.month
    multiplier = 1.0
    if month == 1:
        multiplier *= 1.5
    elif month == 2:
        multiplier *= 0.85
    elif month in (6, 7, 8):
        multiplier *= 1.2
    elif month == 11:
        multiplier *= 1.45
    elif month == 12:
        multiplier *= 1.6
    if moment.weekday() >= 5:
        multiplier *= 1.15
    return multiplier


def _generate_orders(products: list[dict], days: int = 365) -> list[dict]:
    """Build a year of orders. The random stream is local so imports stay quiet."""
    rng = random.Random(42)
    now = datetime.now(UTC)
    weights = [_product_weight(product) for product in products]
    total_weight = sum(weights)
    normalized = [weight / total_weight for weight in weights]
    orders: list[dict] = []
    order_number = 1000
    line_number = 10000

    for day_offset in range(days, 0, -1):
        moment = now - timedelta(days=day_offset)
        multiplier = _seasonal_multiplier(moment)
        base_orders = int(18 * multiplier)
        order_count = max(3, int(rng.gauss(base_orders, base_orders * 0.25)))
        for _ in range(order_count):
            order_number += 1
            item_count = rng.choices([1, 2, 3], weights=[0.6, 0.28, 0.12])[0]
            chosen = rng.choices(range(len(products)), weights=normalized, k=item_count)
            line_items = []
            total = Decimal("0")
            for index in chosen:
                product = products[index]
                quantity = rng.choices([1, 2], weights=[0.92, 0.08])[0]
                price = product["retail_price"]
                total += price * quantity
                line_number += 1
                line_items.append(
                    {
                        "line_item_id": f"LI-{line_number}",
                        "sku": product["sku"],
                        "quantity": quantity,
                        "price": price,
                    }
                )
            orders.append(
                {
                    "order_id": f"ORD-{order_number}",
                    "shopify_order_id": f"SHP-{order_number}",
                    "created_at": moment.replace(
                        hour=rng.randint(8, 21),
                        minute=rng.randint(0, 59),
                        second=rng.randint(0, 59),
                    ),
                    "total_price": total,
                    "line_items": line_items,
                }
            )
    return orders


def _generate_inventory(products: list[dict]) -> list[dict]:
    """Current snapshots for both demo warehouses and both sources."""
    rng = random.Random(7)
    now = datetime.now(UTC)
    snapshots: list[dict] = []
    snapshot_number = 5000

    for product in products:
        for warehouse_index, warehouse in enumerate(WAREHOUSES):
            snapshot_number += 1
            warehouse_factor = 1.0 if warehouse_index == 0 else 0.45
            base = max(0, int((70 + rng.gauss(0, 12)) * warehouse_factor))
            roll = rng.random()
            if product["category"] == "footwear" and product["size_code"] in (
                "US 7",
                "US 13",
            ):
                if roll < 0.3:
                    base = 0
                elif roll < 0.5:
                    base = rng.randint(1, 4)
            elif roll < 0.06:
                base = 0
            elif roll < 0.12:
                base = rng.randint(1, 6)
            elif roll < 0.16:
                base = rng.randint(400, 700)

            allocated = min(int(base * rng.uniform(0.05, 0.15)), base)
            available = max(base - allocated, 0)
            snapshots.append(
                {
                    "snapshot_id": f"SNAP-WH-{snapshot_number}",
                    "sku": product["sku"],
                    "quantity_on_hand": base,
                    "quantity_allocated": allocated,
                    "quantity_available": available,
                    "warehouse": warehouse,
                    "source": "shiphero",
                    "recorded_at": now - timedelta(hours=rng.randint(0, 3)),
                }
            )

            snapshot_number += 1
            # The store count is close to the warehouse count, not identical,
            # so the reconciliation screen has something to flag.
            store_on_hand = max(0, base + rng.choice([0, 0, 0, 0, 1, -1, 2, -2]))
            store_available = max(store_on_hand - allocated, 0)
            snapshots.append(
                {
                    "snapshot_id": f"SNAP-ST-{snapshot_number}",
                    "sku": product["sku"],
                    "quantity_on_hand": store_on_hand,
                    "quantity_allocated": allocated,
                    "quantity_available": store_available,
                    "warehouse": warehouse,
                    "source": "shopify",
                    "recorded_at": now - timedelta(hours=rng.randint(1, 6)),
                }
            )
    return snapshots


def _generate_reorder_rules(products: list[dict]) -> list[dict]:
    """Give most footwear, and some of everything else, a reorder rule."""
    rng = random.Random(11)
    rules = []
    thresholds = {"footwear": 0.8, "apparel": 0.6, "accessories": 0.45}
    seen: set[str] = set()
    for product in products:
        if product["sku"] in seen:
            continue
        seen.add(product["sku"])
        if rng.random() >= thresholds.get(product["category"], 0.5):
            continue
        rules.append(
            {
                "sku": product["sku"],
                "reorder_point": rng.choice([12, 18, 24, 30]),
                "reorder_quantity": rng.choice([24, 48, 72]),
                "lead_time_days": 21 if product["category"] == "footwear" else 12,
                "safety_stock": rng.choice([4, 8, 12]),
            }
        )
    return rules


def _generate_promotions(now: datetime) -> list[dict]:
    """A past event, an event in progress, and a future event."""
    year = now.year
    return [
        {
            "name": "Demo winter sample sale",
            "start_date": datetime(year, 1, 6, tzinfo=UTC),
            "end_date": datetime(year, 1, 20, tzinfo=UTC),
            "discount_pct": 15.0,
            "notes": "Synthetic past promotion. The forecast does not adjust for it.",
        },
        {
            "name": "Demo week in progress",
            "start_date": now - timedelta(days=2),
            "end_date": now + timedelta(days=5),
            "discount_pct": 10.0,
            "notes": "Synthetic current promotion so the page has an active row.",
        },
        {
            "name": "Demo late-year sale",
            "start_date": datetime(year, 11, 20, tzinfo=UTC),
            "end_date": datetime(year, 11, 27, tzinfo=UTC),
            "discount_pct": 20.0,
            "notes": "Synthetic calendar entry. Not applied to the demand model.",
        },
        {
            "name": "Demo upcoming color drop",
            "start_date": now + timedelta(days=21),
            "end_date": now + timedelta(days=28),
            "discount_pct": 0.0,
            "notes": "Future synthetic event with no discount.",
        },
    ]


async def _product_count() -> int:
    async with async_session() as session:
        count = await session.scalar(select(func.count(Product.id)))
        return int(count or 0)


async def seed(clear: bool = True, if_empty: bool = False) -> None:
    """Insert the synthetic catalog, a year of orders, and opening stock."""
    await init_db()
    if if_empty and await _product_count() > 0:
        logger.info("Database already has products; leaving demo data in place")
        print("Database already has products; seed skipped.")
        return

    now = datetime.now(UTC)
    products = _build_catalog()
    orders = _generate_orders(products)
    inventory = _generate_inventory(products)
    reorder_rules = _generate_reorder_rules(products)
    promotions = _generate_promotions(now)
    line_count = sum(len(order["line_items"]) for order in orders)

    summary = (
        f"{DEMO_BRAND}: {len(products)} SKUs, {len(orders)} orders, "
        f"{line_count} line items, {len(inventory)} snapshots"
    )
    logger.info("Seeding %s", summary)
    print(summary)

    async with async_session() as session:
        if clear:
            logger.info("Clearing existing demo tables")
            for table in (
                "order_line_items",
                "orders",
                "inventory_snapshots",
                "reorder_rules",
                "promotional_periods",
                "products",
                "job_logs",
            ):
                await session.execute(text(f"DELETE FROM {table}"))
            await session.flush()

        for product in products:
            session.add(
                Product(
                    sku=product["sku"],
                    title=product["title"],
                    parent_sku=product["parent_sku"],
                    cost_price=product["cost_price"],
                )
            )
        await session.flush()

        for index, order in enumerate(orders, start=1):
            session.add(
                Order(
                    order_id=order["order_id"],
                    shopify_order_id=order["shopify_order_id"],
                    created_at=order["created_at"],
                    total_price=order["total_price"],
                )
            )
            for line in order["line_items"]:
                session.add(
                    OrderLineItem(
                        line_item_id=line["line_item_id"],
                        order_id=order["order_id"],
                        sku=line["sku"],
                        quantity=line["quantity"],
                        price=line["price"],
                    )
                )
            if index % 1000 == 0:
                await session.flush()
                logger.info("Inserted %s/%s orders", index, len(orders))

        for snapshot in inventory:
            session.add(InventorySnapshot(**snapshot))
        for rule in reorder_rules:
            session.add(ReorderRule(**rule))
        for promo in promotions:
            session.add(PromotionalPeriod(**promo))
        await session.commit()

    logger.info("Seed finished")
    print("Done. Synthetic demo data is loaded.")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Load the synthetic Veldt & Ember demo catalog"
    )
    parser.add_argument(
        "--if-empty",
        action="store_true",
        help="Do nothing when the products table already has rows",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Insert without deleting existing rows",
    )
    args = parser.parse_args()
    configure_logging()
    asyncio.run(seed(clear=not args.no_clear, if_empty=args.if_empty))


if __name__ == "__main__":
    main()
