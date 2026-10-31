"""Dedicated Dental Clinic Economic & Feasibility Engine.

Replaces the generic appointment archetype with procedure-level clinical economics:
1. 7 Distinct Clinical Procedures with realistic durations, variable costs, and lab fees:
   - Consultation & Digital Diagnostics
   - Ultrasonic Scaling & Prophylaxis
   - Composite Restorations (Fillings)
   - Endodontics (Root Canal Treatment)
   - Prosthodontics (Ceramic / Zirconia Crowns)
   - Extractions & Minor Oral Surgery
   - Orthodontics (Braces / Clear Aligners)
2. Strict Clinical Capacity Constraints:
   Available Chair Minutes = Chairs * Operating Hours/Day * 60 * Open Days
   Appointments that exceed clinical chair capacity are turned away.
3. Transparent Financial Feasibility:
   Revenue, Consumable & Lab Costs, Fixed Overheads, Contribution, Operating Profit,
   Break-Even Appointments, and Capital Payback Period.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import numpy as np


@dataclass(frozen=True)
class DentalProcedure:
    key: str
    label: str
    duration_minutes: float
    default_price: float  # INR
    consumable_cost: float  # Gloves, bibs, burs, composite/gutta-percha
    lab_cost: float  # Dental lab fees (crowns, aligners, dentures)
    demand_share: float  # Share of visits in typical clinical practice
    annual_frequency: float

    @property
    def variable_cost(self) -> float:
        return self.consumable_cost + self.lab_cost

    @property
    def contribution_margin(self) -> float:
        return self.default_price - self.variable_cost


# Clinically validated procedure benchmarks for Indian urban practices
DENTAL_PROCEDURES: tuple[DentalProcedure, ...] = (
    DentalProcedure(
        key="consultation",
        label="Consultation & Digital Diagnostics",
        duration_minutes=20.0,
        default_price=500.0,
        consumable_cost=80.0,
        lab_cost=0.0,
        demand_share=0.30,
        annual_frequency=2.0,
    ),
    DentalProcedure(
        key="scaling",
        label="Ultrasonic Scaling & Polishing",
        duration_minutes=35.0,
        default_price=1500.0,
        consumable_cost=180.0,
        lab_cost=0.0,
        demand_share=0.22,
        annual_frequency=1.5,
    ),
    DentalProcedure(
        key="filling",
        label="Composite Restorations (Fillings)",
        duration_minutes=40.0,
        default_price=1800.0,
        consumable_cost=280.0,
        lab_cost=0.0,
        demand_share=0.18,
        annual_frequency=1.2,
    ),
    DentalProcedure(
        key="rct",
        label="Root Canal Treatment (Single / Multi-visit)",
        duration_minutes=60.0,
        default_price=4500.0,
        consumable_cost=650.0,
        lab_cost=0.0,
        demand_share=0.12,
        annual_frequency=1.0,
    ),
    DentalProcedure(
        key="crown",
        label="Prosthodontic Crown (Zirconia / Ceramic)",
        duration_minutes=45.0,
        default_price=6500.0,
        consumable_cost=400.0,
        lab_cost=1800.0,
        demand_share=0.08,
        annual_frequency=1.0,
    ),
    DentalProcedure(
        key="extraction",
        label="Extraction & Minor Oral Surgery",
        duration_minutes=45.0,
        default_price=2200.0,
        consumable_cost=350.0,
        lab_cost=0.0,
        demand_share=0.06,
        annual_frequency=1.0,
    ),
    DentalProcedure(
        key="orthodontics",
        label="Orthodontic Consultation & Adjustment",
        duration_minutes=30.0,
        default_price=3000.0,
        consumable_cost=300.0,
        lab_cost=500.0,
        demand_share=0.04,
        annual_frequency=6.0,
    ),
)


@dataclass
class DentalClinicEconomics:
    chairs: int = 2
    operating_hours_per_day: float = 8.0
    open_days_per_month: int = 26
    rent_per_month: float = 65000.0
    payroll_per_month: float = 85000.0  # Associate dentist, dental assistant, front desk
    utilities_per_month: float = 12000.0
    other_fixed_per_month: float = 8000.0
    marketing_per_month: float = 15000.0
    equipment_capex: float = 1200000.0  # 2 chairs, autoclave, RVG X-ray, compressor, instruments

    @property
    def total_fixed_cost(self) -> float:
        return (
            self.rent_per_month
            + self.payroll_per_month
            + self.utilities_per_month
            + self.other_fixed_per_month
            + self.marketing_per_month
        )

    @property
    def available_chair_minutes(self) -> float:
        return float(self.chairs * self.operating_hours_per_day * 60.0 * self.open_days_per_month)

    def evaluate(self, unconstrained_monthly_demand: float, price_overrides: dict[str, float] | None = None) -> dict:
        """Evaluate dental clinic feasibility given unconstrained patient demand."""
        unconstrained_monthly_demand = max(0.0, float(unconstrained_monthly_demand))
        avail_mins = self.available_chair_minutes
        overrides = price_overrides or {}

        # 1. Distribute demand across procedures and calculate required minutes
        proc_results = []
        tot_req_mins = 0.0

        for p in DENTAL_PROCEDURES:
            p_price = float(overrides.get(p.key, p.default_price))
            p_demand = unconstrained_monthly_demand * p.demand_share
            req_mins = p_demand * p.duration_minutes
            tot_req_mins += req_mins

            proc_results.append({
                "key": p.key,
                "label": p.label,
                "duration_minutes": p.duration_minutes,
                "price": p_price,
                "consumable_cost": p.consumable_cost,
                "lab_cost": p.lab_cost,
                "variable_cost": p.consumable_cost + p.lab_cost,
                "margin_unit": p_price - (p.consumable_cost + p.lab_cost),
                "demand_units": p_demand,
                "required_minutes": req_mins,
            })

        # 2. Apply clinical capacity constraint
        capacity_utilization = tot_req_mins / avail_mins if avail_mins > 0 else 1.0
        capacity_bound = tot_req_mins > avail_mins
        cap_factor = min(1.0, avail_mins / tot_req_mins) if tot_req_mins > 0 else 1.0

        tot_revenue = 0.0
        tot_variable_cost = 0.0
        tot_completed_units = 0.0
        tot_turned_away_units = 0.0

        for r in proc_results:
            comp_units = r["demand_units"] * cap_factor
            turned = r["demand_units"] - comp_units
            rev = comp_units * r["price"]
            vc = comp_units * r["variable_cost"]
            margin = rev - vc

            r["completed_units"] = round(comp_units, 1)
            r["turned_away_units"] = round(turned, 1)
            r["revenue"] = round(rev, 2)
            r["variable_cost"] = round(vc, 2)
            r["contribution"] = round(margin, 2)

            tot_revenue += rev
            tot_variable_cost += vc
            tot_completed_units += comp_units
            tot_turned_away_units += turned

        # 3. Clinic-wide economics
        tot_contribution = tot_revenue - tot_variable_cost
        fixed_total = self.total_fixed_cost
        operating_profit = tot_contribution - fixed_total

        avg_price = tot_revenue / tot_completed_units if tot_completed_units > 0 else 0.0
        avg_vc = tot_variable_cost / tot_completed_units if tot_completed_units > 0 else 0.0
        avg_margin = avg_price - avg_vc

        break_even_units = fixed_total / avg_margin if avg_margin > 0 else float("inf")
        payback_months = self.equipment_capex / operating_profit if operating_profit > 0 else float("inf")

        return {
            "summary": {
                "unconstrained_demand_units": round(unconstrained_monthly_demand, 1),
                "completed_units": round(tot_completed_units, 1),
                "turned_away_units": round(tot_turned_away_units, 1),
                "capacity_bound": capacity_bound,
                "chair_utilization_pct": round(min(1.0, capacity_utilization) * 100.0, 1),
                "available_chair_hours": round(avail_mins / 60.0, 1),
                "required_chair_hours": round(tot_req_mins / 60.0, 1),
                "average_ticket_price": round(avg_price, 2),
            },
            "finance": {
                "revenue": round(tot_revenue, 2),
                "variable_cost": round(tot_variable_cost, 2),
                "contribution_margin": round(tot_contribution, 2),
                "fixed_cost": round(fixed_total, 2),
                "operating_profit": round(operating_profit, 2),
                "break_even_appointments": round(break_even_units, 1) if not math.isinf(break_even_units) else None,
                "payback_months": round(payback_months, 1) if not math.isinf(payback_months) else None,
                "startup_capex": self.equipment_capex,
            },
            "fixed_cost_breakdown": {
                "rent": self.rent_per_month,
                "payroll": self.payroll_per_month,
                "utilities": self.utilities_per_month,
                "other_fixed": self.other_fixed_per_month,
                "marketing": self.marketing_per_month,
            },
            "procedures": proc_results,
        }
