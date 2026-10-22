"""Monthly operating economics. Pure functions, array-friendly."""
from __future__ import annotations

import numpy as np

INCLUDED = [
    "Revenue = price x units sold (capacity-constrained)",
    "Variable cost = variable cost per unit x units",
    "Fixed operating cost = rent + payroll + utilities + other fixed + marketing",
]
EXCLUDED = [
    "Taxes (GST/income tax)", "Loan interest and financing", "Depreciation of equipment",
    "Working capital and inventory build-up", "Security deposits (included only in startup cash if you entered them there)",
]


def fixed_costs(rent: float, payroll: float, utilities: float, other: float, marketing: float) -> dict:
    items = {"rent": rent, "payroll": payroll, "utilities": utilities, "other_fixed": other, "marketing": marketing}
    items = {k: max(0.0, float(v or 0.0)) for k, v in items.items()}
    items["total"] = sum(items.values())
    return items


def economics(units, price: float, vc_unit, fixed_total: float, startup_cost: float, capacity: float):
    units = np.asarray(units, float)
    vc_unit = np.asarray(vc_unit, float)
    revenue = units * price
    variable = units * vc_unit
    contribution = revenue - variable
    profit = contribution - fixed_total
    margin_unit = price - vc_unit
    with np.errstate(divide="ignore", invalid="ignore"):
        be_units = np.where(margin_unit > 0, fixed_total / margin_unit, np.inf)
        payback = np.where(profit > 0, startup_cost / profit, np.inf)
        utilization = np.where(capacity > 0, units / capacity, 0.0)
        be_util = np.where(capacity > 0, be_units / capacity, np.inf)
    return {
        "revenue": revenue, "variable_cost": variable, "fixed_cost": np.full_like(revenue, fixed_total),
        "contribution": contribution, "operating_profit": profit, "break_even_units": be_units,
        "payback_months": payback, "utilization": utilization, "break_even_utilization": be_util,
        "unit_margin": margin_unit,
    }
