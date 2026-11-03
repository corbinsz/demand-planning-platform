"""Reorder point, safety stock, and order quantity."""

import math

import pytest

from app.services.reorder import compute_reorder, urgency


def test_reorder_point_is_lead_time_demand_plus_safety():
    plan = compute_reorder(daily_demand=2, current_stock=100, lead_time_days=10, safety_stock=7)
    assert plan["reorder_point"] == math.ceil(2 * 10) + 7


def test_safety_stock_alone_can_trigger_a_buy():
    plan = compute_reorder(daily_demand=0, current_stock=2, lead_time_days=14, safety_stock=10)
    assert plan["reorder_point"] == 10
    assert plan["below_reorder_point"] is True
    assert plan["suggested_reorder_qty"] == 8


def test_zero_velocity_exactly_at_safety_does_not_ask_for_more_units():
    plan = compute_reorder(daily_demand=0, current_stock=10, lead_time_days=14, safety_stock=10)
    assert plan["reorder_point"] == 10
    assert plan["below_reorder_point"] is True
    assert plan["suggested_reorder_qty"] == 0


def test_safety_is_included_in_the_cover_buy():
    without = compute_reorder(daily_demand=1, current_stock=0, lead_time_days=7, safety_stock=0)
    with_safety = compute_reorder(daily_demand=1, current_stock=0, lead_time_days=7, safety_stock=12)
    assert with_safety["suggested_reorder_qty"] == without["suggested_reorder_qty"] + 12


def test_manual_reorder_point_is_a_floor_not_a_ceiling():
    plan = compute_reorder(
        daily_demand=1,
        current_stock=5,
        lead_time_days=7,
        safety_stock=0,
        manual_reorder_point=40,
    )
    assert plan["reorder_point"] == 40
    assert plan["below_reorder_point"] is True


def test_manual_floor_does_not_shrink_a_higher_calculated_point():
    plan = compute_reorder(
        daily_demand=5,
        current_stock=0,
        lead_time_days=10,
        safety_stock=0,
        manual_reorder_point=3,
    )
    assert plan["reorder_point"] == 50


def test_healthy_stock_suggests_nothing_even_with_a_minimum():
    plan = compute_reorder(
        daily_demand=1,
        current_stock=400,
        lead_time_days=14,
        safety_stock=5,
        moq=100,
    )
    assert plan["below_reorder_point"] is False
    assert plan["suggested_reorder_qty"] == 0


def test_moq_applies_when_the_real_need_is_smaller_but_still_sensible():
    plan = compute_reorder(
        daily_demand=3,
        current_stock=0,
        lead_time_days=14,
        safety_stock=0,
        moq=40,
    )
    # 8 weeks * 3 = 168, which is above the minimum, so the cover wins.
    assert plan["suggested_reorder_qty"] == math.ceil(3 * 56)


def test_moq_is_used_when_it_does_not_create_a_half_year_of_stock():
    plan = compute_reorder(
        daily_demand=2,
        current_stock=100,
        lead_time_days=14,
        safety_stock=0,
        moq=30,
    )
    # point = 28, stock 100 is healthy. No order.
    assert plan["suggested_reorder_qty"] == 0
    low = compute_reorder(
        daily_demand=2,
        current_stock=5,
        lead_time_days=14,
        safety_stock=0,
        moq=30,
    )
    assert low["suggested_reorder_qty"] >= 30


def test_negative_inputs_are_treated_as_zero():
    plan = compute_reorder(daily_demand=-4, current_stock=-3, lead_time_days=-1, safety_stock=-8)
    assert plan["reorder_point"] == 0
    assert plan["suggested_reorder_qty"] == 0
    assert plan["days_of_stock_remaining"] is None


def test_days_remaining_uses_the_demand_rate():
    plan = compute_reorder(daily_demand=2, current_stock=9, lead_time_days=1, safety_stock=0)
    assert plan["days_of_stock_remaining"] == 4.5


def test_urgency_buckets():
    assert urgency(None, 10) == "critical"
    assert urgency(0, 10) == "critical"
    assert urgency(10, 10) == "critical"
    assert urgency(14, 10) == "high"
    assert urgency(18, 10) == "medium"
    assert urgency(30, 10) == "low"


@pytest.mark.parametrize(
    "days,lead,expected",
    [(1, 20, "critical"), (21, 14, "high"), (28, 14, "medium"), (29, 14, "low")],
)
def test_urgency_edges(days, lead, expected):
    assert urgency(days, lead) == expected
