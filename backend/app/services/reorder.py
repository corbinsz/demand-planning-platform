"""Reorder point, suggested quantity, and urgency.

These are the planning rules the purchase-order screen uses. They do not
talk to the database, so the tests can pin the math without a catalog.
"""

import math

WEEKS_OF_SUPPLY = 8


def calculate_urgency(days_remaining: float | None, lead_time_days: int) -> str:
    """How soon a SKU needs a purchase order, compared with supplier lead time.

    ``critical`` means stock runs out before a replenishment can arrive.
    ``high`` is inside 1.5x lead time, ``medium`` inside 2x, otherwise ``low``.
    Unknown runway (no recent sales) is treated as critical.
    """
    if days_remaining is None or days_remaining <= lead_time_days:
        return "critical"
    if days_remaining <= lead_time_days * 1.5:
        return "high"
    if days_remaining <= lead_time_days * 2:
        return "medium"
    return "low"


def compute_reorder_point(
    daily_demand: float,
    lead_time_days: int,
    safety_stock: int,
    rule_floor: int | None = None,
) -> int:
    """Units to have on hand when a replenishment order is placed.

    That is lead-time demand plus safety stock. A saved reorder rule can
    only raise the point, never lower it.
    """
    demand = max(float(daily_demand), 0.0)
    point = math.ceil(demand * lead_time_days) + max(int(safety_stock), 0)
    if rule_floor is not None:
        point = max(point, int(rule_floor))
    return point


def suggest_order_quantity(
    daily_demand: float,
    current_stock: int,
    *,
    below_reorder_point: bool,
    minimum_quantity: int | None = None,
    weeks: int = WEEKS_OF_SUPPLY,
) -> int:
    """Units to buy so on-hand covers ``weeks`` of recent daily demand.

    The configured reorder quantity is a minimum, and it applies only when
    the SKU is actually at or below its reorder point. A healthy SKU is not
    padded up to that minimum.
    """
    demand = max(float(daily_demand), 0.0)
    needed = max(math.ceil(demand * 7 * weeks) - int(current_stock), 0)
    if below_reorder_point and minimum_quantity:
        needed = max(needed, int(minimum_quantity))
    return needed
