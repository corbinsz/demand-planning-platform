"""Reorder math, independent of the database."""

from app.services.reorder import (
    calculate_urgency,
    compute_reorder_point,
    suggest_order_quantity,
)


def test_urgency_bands_follow_lead_time():
    lead = 10
    assert calculate_urgency(None, lead) == "critical"
    assert calculate_urgency(0, lead) == "critical"
    assert calculate_urgency(10, lead) == "critical"
    assert calculate_urgency(10.1, lead) == "high"
    assert calculate_urgency(15, lead) == "high"
    assert calculate_urgency(15.1, lead) == "medium"
    assert calculate_urgency(20, lead) == "medium"
    assert calculate_urgency(20.1, lead) == "low"


def test_reorder_point_is_lead_time_demand_plus_safety_and_respects_the_floor():
    assert compute_reorder_point(2, 14, 3) == 31
    assert compute_reorder_point(2, 14, 3, rule_floor=40) == 40
    assert compute_reorder_point(0, 14, 0) == 0


def test_suggested_quantity_covers_eight_weeks_and_floors_only_when_reordering():
    # 2 units a day * 56 days - 10 on hand.
    assert (
        suggest_order_quantity(2, 10, below_reorder_point=True, minimum_quantity=20)
        == 102
    )
    # Healthy stock is not padded up to the minimum order quantity.
    assert (
        suggest_order_quantity(2, 500, below_reorder_point=False, minimum_quantity=80)
        == 0
    )
    # At the reorder point, the saved quantity is a floor.
    assert (
        suggest_order_quantity(0.1, 5, below_reorder_point=True, minimum_quantity=24)
        == 24
    )
