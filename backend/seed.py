"""
Seed the database with demo data modeled after a DTC fitness brand (Otishi-style).

Run:  python -m seed
"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.database import async_session, init_db
from app.models.models import (
    Product, Order, OrderLineItem, InventorySnapshot,
    ReorderRule, PromotionalPeriod, JobLog,
)

random.seed(42)

# ---------------------------------------------------------------------------
# Product catalog — modeled after Otishi (DTC athletic / lifting brand)
# ---------------------------------------------------------------------------

SHOE_SIZES = [
    ("M4/W5.5", "4"),
    ("M5/W6.5", "5"),
    ("M6/W7.5", "6"),
    ("M7/W8.5", "7"),
    ("M8/W9.5", "8"),
    ("M9/W10.5", "9"),
    ("M10/W11.5", "10"),
    ("M11/W12.5", "11"),
    ("M12/W13.5", "12"),
    ("M13/W14.5", "13"),
    ("M14/W15.5", "14"),
]

APPAREL_SIZES = ["S", "M", "L", "XL", "XXL"]

COLORWAYS = {
    "Amaru/Black":     "AMR",
    "Andes Snow":      "AND",
    "Moonstone Gray":  "MST",
    "Petrified Sand":  "PSD",
}

APPAREL_COLORS = {
    "Obsidian": "OBS",
    "Brown":    "BRN",
    "Black":    "BLK",
    "White":    "WHT",
    "Earth Tone": "ETN",
    "Orange":   "ORG",
}

WAREHOUSES = ["Primary - NJ", "West Coast - CA"]


def _build_catalog():
    """Return list of product dicts mirroring a real Otishi-style catalog."""
    products = []

    # ---- THE OTISHI 2.0 (hero shoe, 4 colorways) ----
    shoe_colorways = [
        ("Amaru/Black",    "AMR", [s for s in SHOE_SIZES if int(s[1]) >= 7]),
        ("Andes Snow",     "AND", SHOE_SIZES),               # widest range = bestseller
        ("Moonstone Gray", "MST", [s for s in SHOE_SIZES if int(s[1]) <= 10]),
        ("Petrified Sand", "PSD", [s for s in SHOE_SIZES if int(s[1]) >= 8]),
    ]
    for cw_name, cw_code, sizes in shoe_colorways:
        parent = f"OT-20-{cw_code}"
        for size_label, size_code in sizes:
            products.append({
                "sku": f"OT-20-{cw_code}-{size_code}",
                "title": f'The Otishi 2.0 "{cw_name}" - {size_label}',
                "parent_sku": parent,
                "cost_price": Decimal("28.00"),
                "retail_price": Decimal("84.99"),
                "category": "footwear",
                "colorway": cw_name,
                "size_code": size_code,
            })

    # ---- LIFTING CLUB TEE ----
    for color, cc in [("Obsidian", "OBS"), ("Brown", "BRN")]:
        parent = "OT-LCT"
        for sz in APPAREL_SIZES:
            products.append({
                "sku": f"OT-LCT-{cc}-{sz}",
                "title": f"Lifting Club Tee - {color} / {sz}",
                "parent_sku": parent,
                "cost_price": Decimal("12.00"),
                "retail_price": Decimal("44.99"),
                "category": "apparel",
                "colorway": color,
                "size_code": sz,
            })

    # ---- DEADLIFT UNIVERSITY SWEATS ----
    for color, cc in [("Black", "BLK"), ("Brown", "BRN")]:
        parent = "OT-DUS"
        for sz in APPAREL_SIZES:
            products.append({
                "sku": f"OT-DUS-{cc}-{sz}",
                "title": f"Deadlift University Sweats - {color} / {sz}",
                "parent_sku": parent,
                "cost_price": Decimal("22.00"),
                "retail_price": Decimal("74.25"),
                "category": "apparel",
                "colorway": color,
                "size_code": sz,
            })

    # ---- CREW SOCKS 3-PACK ----
    for color, cc in [("White", "WHT"), ("Earth Tone", "ETN"), ("Black", "BLK")]:
        products.append({
            "sku": f"OT-SOX-{cc}",
            "title": f"Crew Socks 3-Pack - {color}",
            "parent_sku": "OT-SOX",
            "cost_price": Decimal("5.00"),
            "retail_price": Decimal("17.99"),
            "category": "accessories",
            "colorway": color,
            "size_code": "OS",
        })

    # ---- FIGURE 8 LIFTING STRAPS ----
    products.append({
        "sku": "OT-F8S",
        "title": "Figure 8 Lifting Straps",
        "parent_sku": None,
        "cost_price": Decimal("4.00"),
        "retail_price": Decimal("18.75"),
        "category": "accessories",
        "colorway": "Black",
        "size_code": "OS",
    })

    # ---- PERFECT SHAKER BOTTLE 28oz ----
    for color, cc in [("Black", "BLK"), ("Orange", "ORG"), ("White", "WHT")]:
        products.append({
            "sku": f"OT-SHK-{cc}",
            "title": f"Otishi Perfect Shaker Bottle 28oz - {color}",
            "parent_sku": "OT-SHK",
            "cost_price": Decimal("3.00"),
            "retail_price": Decimal("9.99"),
            "category": "accessories",
            "colorway": color,
            "size_code": "OS",
        })

    return products


# ---------------------------------------------------------------------------
# Popularity / demand weights (mirrors typical DTC sales distribution)
# ---------------------------------------------------------------------------

# Shoe colorway popularity — Andes Snow is the hero, Petrified Sand is new
COLORWAY_WEIGHT = {
    "Andes Snow": 1.8,
    "Amaru/Black": 1.3,
    "Moonstone Gray": 0.8,
    "Petrified Sand": 0.6,
}

# Shoe size distribution (bell curve peaking at M9-M10)
SHOE_SIZE_WEIGHT = {
    "4": 0.02, "5": 0.04, "6": 0.06, "7": 0.08, "8": 0.13,
    "9": 0.18, "10": 0.18, "11": 0.13, "12": 0.08, "13": 0.06, "14": 0.04,
}

# Apparel size distribution
APPAREL_SIZE_WEIGHT = {"S": 0.10, "M": 0.25, "L": 0.30, "XL": 0.25, "XXL": 0.10}

# Category base demand (daily units across all variants)
CATEGORY_DAILY_DEMAND = {
    "footwear": 18,     # ~18 pairs/day average
    "apparel": 12,      # ~12 units/day
    "accessories": 8,   # ~8 units/day
}


def _product_weight(p):
    """Relative demand weight for a product variant."""
    if p["category"] == "footwear":
        cw = COLORWAY_WEIGHT.get(p["colorway"], 1.0)
        sz = SHOE_SIZE_WEIGHT.get(p["size_code"], 0.05)
        return cw * sz
    elif p["category"] == "apparel":
        sz = APPAREL_SIZE_WEIGHT.get(p["size_code"], 0.15)
        # Lifting Club Tee outsells Deadlift Sweats 2:1
        if "Lifting Club" in p["title"]:
            return sz * 1.4
        return sz * 0.8
    else:
        # Accessories — socks > straps > shaker
        if "Socks" in p["title"]:
            return 1.2
        elif "Strap" in p["title"]:
            return 0.8
        return 0.6


def _seasonal_multiplier(dt):
    """Return demand multiplier for a given date (seasonal patterns for DTC fitness)."""
    m = dt.month
    dow = dt.weekday()
    mult = 1.0

    # New Year's resolution rush (January)
    if m == 1:
        mult *= 1.6
    # Post-resolution dip (February)
    elif m == 2:
        mult *= 0.8
    # Summer training season (June-August)
    elif m in (6, 7, 8):
        mult *= 1.25
    # Back to school / fall training (September)
    elif m == 9:
        mult *= 1.15
    # Black Friday / holiday (November-December)
    elif m == 11:
        mult *= 1.5
    elif m == 12:
        mult *= 1.7

    # Weekend bump (people browse more on weekends)
    if dow >= 5:
        mult *= 1.2

    return mult


# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------

def _generate_orders(products, days=365):
    """Generate realistic order history."""
    now = datetime.now(timezone.utc)
    orders = []
    weights = [_product_weight(p) for p in products]
    total_weight = sum(weights)
    norm_weights = [w / total_weight for w in weights]

    oid = 1000
    lid = 10000

    for day_offset in range(days, 0, -1):
        dt = now - timedelta(days=day_offset)
        mult = _seasonal_multiplier(dt)
        base_orders = int(22 * mult)
        num_orders = max(3, int(random.gauss(base_orders, base_orders * 0.25)))

        for _ in range(num_orders):
            oid += 1
            # 1-3 items per order (typical DTC basket)
            num_items = random.choices([1, 2, 3], weights=[0.55, 0.30, 0.15])[0]
            selected_indices = random.choices(range(len(products)), weights=norm_weights, k=num_items)

            line_items = []
            total = Decimal("0")
            for idx in selected_indices:
                p = products[idx]
                qty = random.choices([1, 2], weights=[0.90, 0.10])[0]
                price = p["retail_price"]
                total += price * qty
                lid += 1
                line_items.append({
                    "line_item_id": f"LI-{lid}",
                    "sku": p["sku"],
                    "quantity": qty,
                    "price": price,
                })

            hour = random.randint(7, 23)
            minute = random.randint(0, 59)
            order_time = dt.replace(hour=hour, minute=minute, second=random.randint(0, 59))

            orders.append({
                "order_id": f"ORD-{oid}",
                "shopify_order_id": f"SHP-{oid}",
                "created_at": order_time,
                "total_price": total,
                "line_items": line_items,
            })

    return orders


def _generate_inventory(products):
    """Generate current inventory snapshots from both ShipHero and Shopify."""
    now = datetime.now(timezone.utc)
    snapshots = []
    sid = 5000

    for p in products:
        w = _product_weight(p)
        # Primary warehouse gets most stock, west coast gets ~40%
        for wh_idx, wh in enumerate(WAREHOUSES):
            sid += 1
            wh_factor = 1.0 if wh_idx == 0 else 0.4

            # Base stock inversely related to sales velocity (popular items sell through faster)
            base = int((80 + random.gauss(0, 15)) * wh_factor)

            # Realistic stock conditions
            roll = random.random()
            if p["category"] == "footwear" and p["size_code"] in ("4", "5", "13", "14"):
                # Extreme sizes often sell out or have very low stock
                if roll < 0.35:
                    base = 0
                elif roll < 0.55:
                    base = random.randint(1, 5)
            elif roll < 0.06:
                base = 0  # stockout
            elif roll < 0.12:
                base = random.randint(1, 8)  # low stock
            elif roll < 0.16:
                base = random.randint(500, 900)  # excess (overordered)

            allocated = min(int(base * random.uniform(0.05, 0.20)), base)
            available = base - allocated

            # ShipHero snapshot (source of truth)
            snapshots.append({
                "snapshot_id": f"SNAP-SH-{sid}",
                "sku": p["sku"],
                "quantity_on_hand": base,
                "quantity_allocated": allocated,
                "quantity_available": available,
                "warehouse": wh,
                "source": "shiphero",
                "recorded_at": now - timedelta(hours=random.randint(0, 3)),
            })

            sid += 1
            # Shopify snapshot (slight discrepancies for realism)
            sp_on_hand = base + random.choice([0, 0, 0, 0, 0, -1, 1, -2, 2, -3])
            sp_available = max(sp_on_hand - allocated, 0)
            snapshots.append({
                "snapshot_id": f"SNAP-SP-{sid}",
                "sku": p["sku"],
                "quantity_on_hand": sp_on_hand,
                "quantity_allocated": allocated,
                "quantity_available": sp_available,
                "warehouse": wh,
                "source": "shopify",
                "recorded_at": now - timedelta(hours=random.randint(0, 6)),
            })

    return snapshots


def _generate_reorder_rules(products):
    """Generate reorder rules (footwear gets rules first, accessories last)."""
    rules = []
    seen = set()
    for p in products:
        if p["sku"] in seen:
            continue
        seen.add(p["sku"])
        # 80% of footwear, 60% of apparel, 40% of accessories have rules
        threshold = {"footwear": 0.80, "apparel": 0.60, "accessories": 0.40}
        if random.random() < threshold.get(p["category"], 0.5):
            rules.append({
                "sku": p["sku"],
                "reorder_point": random.choice([15, 20, 25, 30]),
                "reorder_quantity": random.choice([50, 100, 150, 200]),
                "lead_time_days": 21 if p["category"] == "footwear" else 14,
                "safety_stock": random.choice([5, 10, 15]),
            })
    return rules


def _generate_promotions():
    """Generate promotions matching DTC fitness brand seasonality."""
    now = datetime.now(timezone.utc)
    return [
        {
            "name": "Resolution Sale - 15% Off Sitewide",
            "start_date": now.replace(month=1, day=1),
            "end_date": now.replace(month=1, day=31),
            "discount_pct": 15.0,
            "notes": "New year, new goals. 15% off everything to kick off the year. Biggest acquisition month.",
        },
        {
            "name": "Summer Training Drop",
            "start_date": (now - timedelta(days=240)).replace(day=1),
            "end_date": (now - timedelta(days=225)).replace(day=15),
            "discount_pct": 10.0,
            "notes": "10% off footwear for summer training season launch",
        },
        {
            "name": "Black Friday / Cyber Monday",
            "start_date": now.replace(month=11, day=24) if now.month <= 11 else (now - timedelta(days=90)),
            "end_date": now.replace(month=11, day=28) if now.month <= 11 else (now - timedelta(days=86)),
            "discount_pct": 25.0,
            "notes": "25% off sitewide. Highest AOV week of the year.",
        },
        {
            "name": "Spring Colorway Launch",
            "start_date": now + timedelta(days=20),
            "end_date": now + timedelta(days=27),
            "discount_pct": 0.0,
            "notes": "New Otishi 2.0 colorway launch — no discount, hype-driven.",
        },
    ]


def _generate_job_logs():
    """Generate recent job logs so the dashboard shows sync history."""
    now = datetime.now(timezone.utc)
    logs = []
    for i, (job, hrs_ago) in enumerate([
        ("shopify_sync", 2),
        ("shiphero_sync", 1),
        ("reconciliation", 1),
        ("forecast_update", 8),
    ]):
        started = now - timedelta(hours=hrs_ago, minutes=random.randint(0, 15))
        finished = started + timedelta(seconds=random.randint(3, 45))
        logs.append({
            "job_name": job,
            "status": "success",
            "started_at": started,
            "finished_at": finished,
            "records_processed": random.randint(50, 300),
        })
    return logs


# ---------------------------------------------------------------------------
# Main seed routine
# ---------------------------------------------------------------------------

async def seed(clear=True):
    """Populate the database with demo data."""
    await init_db()

    products = _build_catalog()
    orders = _generate_orders(products)
    inventory = _generate_inventory(products)
    reorder_rules = _generate_reorder_rules(products)
    promotions = _generate_promotions()
    job_logs = _generate_job_logs()

    print(f"  Products:           {len(products)}")
    print(f"  Orders:             {len(orders)}")
    print(f"  Order line items:   {sum(len(o['line_items']) for o in orders)}")
    print(f"  Inventory snaps:    {len(inventory)}")
    print(f"  Reorder rules:      {len(reorder_rules)}")
    print(f"  Promotions:         {len(promotions)}")
    print(f"  Job logs:           {len(job_logs)}")
    print()

    async with async_session() as session:
        if clear:
            from sqlalchemy import text
            print("Clearing existing data...")
            for table in [
                "order_line_items", "orders", "inventory_snapshots",
                "reorder_rules", "promotional_periods", "products", "job_logs",
            ]:
                await session.execute(text(f"DELETE FROM {table}"))
            await session.flush()

        print("Inserting products...")
        for p in products:
            session.add(Product(
                sku=p["sku"],
                title=p["title"],
                parent_sku=p["parent_sku"],
                cost_price=p["cost_price"],
            ))
        await session.flush()

        print("Inserting orders & line items...")
        batch = 0
        for o in orders:
            session.add(Order(
                order_id=o["order_id"],
                shopify_order_id=o["shopify_order_id"],
                created_at=o["created_at"],
                total_price=o["total_price"],
            ))
            for li in o["line_items"]:
                session.add(OrderLineItem(
                    line_item_id=li["line_item_id"],
                    order_id=o["order_id"],
                    sku=li["sku"],
                    quantity=li["quantity"],
                    price=li["price"],
                ))
            batch += 1
            if batch % 1000 == 0:
                await session.flush()
                print(f"  ...{batch}/{len(orders)} orders")

        print("Inserting inventory snapshots...")
        for snap in inventory:
            session.add(InventorySnapshot(**snap))

        print("Inserting reorder rules...")
        for rule in reorder_rules:
            session.add(ReorderRule(**rule))

        print("Inserting promotions...")
        for promo in promotions:
            session.add(PromotionalPeriod(**promo))

        print("Inserting job logs...")
        for log in job_logs:
            session.add(JobLog(**log))

        await session.commit()
        print("\nDone! Database seeded successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
