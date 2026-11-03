"""Reorder math that does not touch the database or a forecast model."""

from __future__ import annotations

import math


def compute_reorder(
    *,
    daily_demand: float,
    current_stock: int,
    lead_time_days: int,
    safety_stock: int,
    moq: int | None = None,
    manual_reorder_point: int | None = None,
    weeks_of_cover: int = 8,
) -> dict:
    """Return reorder point, suggested buy qty, and whether to buy.

    `moq` (the rule's reorder quantity) is a supplier minimum. It applies
    only when we actually need to buy. It is never written back as a new
    floor, which is what made suggestions ratchet upward.
    A manually raised reorder point is kept as a floor.
    """
    daily = max(float(daily_demand or 0), 0.0)
    stock = max(int(current_stock or 0), 0)
    lead = max(int(lead_time_days or 0), 0)
    safety = max(int(safety_stock or 0), 0)

    calculated_point = int(math.ceil(daily * lead) + safety)
    reorder_point = calculated_point
    if manual_reorder_point is not None:
        reorder_point = max(calculated_point, int(manual_reorder_point))

    cover_days = 7 * weeks_of_cover
    need = max(int(math.ceil(daily * cover_days)) - stock, 0)
    if need > 0 and moq:
        # A supplier minimum that would leave half a year of a slow seller
        # on the shelf is not a helpful buy. Show the real need instead.
        moq_days = (int(moq) / daily) if daily > 0 else 9999
        if moq_days > 180 and need < int(moq):
            suggested = need
        else:
            suggested = max(need, int(moq))
    else:
        suggested = need

    days_remaining = round(stock / daily, 1) if daily > 0 else None
    below = stock <= reorder_point
    return {
        "reorder_point": reorder_point,
        "suggested_reorder_qty": suggested if below else 0,
        "below_reorder_point": below,
        "days_of_stock_remaining": days_remaining,
    }


def urgency(days_remaining: float | None, lead_time: int) -> str:
    if days_remaining is None or days_remaining <= 0:
        return "critical"
    if days_remaining <= lead_time:
        return "critical"
    if days_remaining <= lead_time * 1.5:
        return "high"
    if days_remaining <= lead_time * 2:
        return "medium"
    return "low"
