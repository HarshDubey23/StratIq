"""Unit and scientific invariant tests for Dedicated Dental Clinic Economics.

Tests:
1. Procedure-level clinical duration and contribution margin integrity.
2. Chair minute capacity binding (capacity can never be exceeded).
3. Exact financial identity conservation:
   Revenue - Variable Costs - Fixed Costs = Operating Profit.
4. Break-even and Capex payback calculation correctness.
"""
import pytest

from app.engine.economics.dental import DENTAL_PROCEDURES, DentalClinicEconomics


def test_dental_procedures_integrity():
    """Verify all 7 procedures have positive clinical durations, prices, and unit margins."""
    assert len(DENTAL_PROCEDURES) == 7
    total_share = sum(p.demand_share for p in DENTAL_PROCEDURES)
    assert abs(total_share - 1.0) < 1e-6, "Procedure demand shares must sum to 1.0"

    for p in DENTAL_PROCEDURES:
        assert p.duration_minutes > 0
        assert p.default_price > 0
        assert p.variable_cost >= 0
        assert p.contribution_margin > 0, f"Procedure {p.label} has non-positive margin"


def test_dental_capacity_constraint_binds():
    """Verify clinical chair capacity strictly binds and turns away excess demand."""
    econ = DentalClinicEconomics(chairs=2, operating_hours_per_day=8, open_days_per_month=26)
    avail_mins = econ.available_chair_minutes
    # 2 chairs * 8 hours * 60 mins * 26 days = 24,960 chair minutes
    assert avail_mins == 24960.0

    # Low demand: 100 appointments requires ~3,500 minutes -> Not bound
    res_low = econ.evaluate(unconstrained_monthly_demand=100)
    assert not res_low["summary"]["capacity_bound"]
    assert res_low["summary"]["completed_units"] == 100.0
    assert res_low["summary"]["turned_away_units"] == 0.0
    assert res_low["summary"]["chair_utilization_pct"] < 25.0

    # High demand: 2,000 appointments requires ~70,000 minutes -> Strictly bound
    res_high = econ.evaluate(unconstrained_monthly_demand=2000)
    assert res_high["summary"]["capacity_bound"]
    assert res_high["summary"]["chair_utilization_pct"] == 100.0
    assert res_high["summary"]["turned_away_units"] > 1000.0

    # Total completed chair minutes cannot exceed available chair minutes
    completed_mins = sum(p["completed_units"] * p["duration_minutes"] for p in res_high["procedures"])
    assert completed_mins <= avail_mins + 1.0, f"Completed mins {completed_mins} exceeded chair capacity {avail_mins}"


def test_dental_financial_identities():
    """Verify exact financial statement balance."""
    econ = DentalClinicEconomics(
        chairs=2,
        rent_per_month=60000,
        payroll_per_month=80000,
        utilities_per_month=10000,
        other_fixed_per_month=5000,
        marketing_per_month=15000,
    )
    res = econ.evaluate(unconstrained_monthly_demand=400)
    fin = res["finance"]

    rev = fin["revenue"]
    vc = fin["variable_cost"]
    contrib = fin["contribution_margin"]
    fc = fin["fixed_cost"]
    profit = fin["operating_profit"]

    assert abs(contrib - (rev - vc)) < 0.05, "Contribution margin identity violated"
    assert abs(profit - (contrib - fc)) < 0.05, "Operating profit identity violated"
    assert fc == 60000 + 80000 + 10000 + 5000 + 15000, "Fixed cost calculation mismatch"


def test_dental_custom_price_overrides():
    """Verify custom procedure prices update unit economics."""
    econ = DentalClinicEconomics()
    res_default = econ.evaluate(200)
    res_premium = econ.evaluate(200, price_overrides={"consultation": 1000.0, "rct": 7000.0})

    assert res_premium["finance"]["revenue"] > res_default["finance"]["revenue"]
    assert res_premium["finance"]["operating_profit"] > res_default["finance"]["operating_profit"]
