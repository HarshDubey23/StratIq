"""Analyst layer: reads a finished run the way a consultant would, and tests strategies through the real engine.

Everything here is computed from stored run results (static choice model + Monte Carlo + 10,000-agent simulation).
No number is invented: each insight carries the figures it is based on, and each suggested action is a concrete
input change that can be run through the same engine (``POST /projects/{id}/strategy``).
"""
from __future__ import annotations

import copy
from statistics import mean

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..categories.archetypes import ARCHETYPES
from ..db import get_db, session_factory
from ..models import Project, Scenario, SimulationRun, User, utcnow
from ..security import current_user, owned_project
from ..services.runs import execute_run, latest_runs

router = APIRouter(tags=["insights"])

MAX_SCENARIOS = 12


def _inr(x: float | None) -> str:
    from .assistant import inr
    return inr(x)


def _n(x: float | None) -> str:
    return "unknown" if x is None else f"{int(round(float(x))):,}"


def _pct(x: float | None) -> str:
    return "unknown" if x is None else f"{round(100 * float(x))}%"


def _avg(xs: list, n: int = 28) -> float:
    xs = [float(x) for x in (xs or [])][-n:]
    return mean(xs) if xs else 0.0


# ---------------------------------------------------------------- compact view of one run
def run_view(res: dict) -> dict:
    """The handful of numbers a person reads off the live page, for one run."""
    abm = res.get("abm") or {}
    daily = abm.get("daily") or {}
    m = abm.get("metrics") or {}
    mu = abm.get("monthly_units") or []
    mf = abm.get("monthly_finance") or []
    fin = res.get("finance") or {}
    mc = res.get("monte_carlo") or {}
    you, turned, demand = daily.get("units_you") or [], daily.get("turned_away") or [], daily.get("demand_you") or []
    return {
        "price": (res.get("summary") or {}).get("price"),
        "static_units_per_month": (res.get("summary") or {}).get("units_sold"),
        "static_profit_per_month": fin.get("operating_profit"),
        "probability_of_loss": mc.get("prob_loss"),
        "break_even_units": fin.get("break_even_units"),
        "agent_month_units": [round(float(x)) for x in mu],
        "agent_month_profit": [round(float(x.get("profit") or 0)) for x in mf],
        "month3_units": round(float(mu[-1])) if mu else None,
        "month3_profit": round(float(mf[-1]["profit"])) if mf else None,
        "orders_per_day_last4w": round(_avg(you)),
        "demand_per_day_last4w": round(_avg(demand)) if demand else None,
        "turned_away_per_day_last4w": round(_avg(turned)),
        "capacity_per_day": abm.get("capacity_per_day"),
        "awareness_week12": m.get("aware_final"),
        "trial_rate": m.get("trial_rate"),
        "repeat_share": m.get("repeat_share"),
        "customers_total": m.get("customers_total"),
        "afford_share": m.get("afford_share"),
        "mean_trip_km": m.get("mean_trip_km"),
        "ramp_up_week": abm.get("ramp_up_week"),
        "agents": abm.get("n_agents"), "residents_per_agent": abm.get("scale"),
        "daily_units": [round(float(x), 1) for x in you],
    }


# ---------------------------------------------------------------- insights
def build_insights(res: dict, inputs: dict, unit: str, price_label: str = "price") -> dict:
    """Rule-based diagnosis of one run. Each item: what we see (with numbers), why it matters, a testable action."""
    v = run_view(res)
    abm = res.get("abm") or {}
    sens = res.get("sensitivity") or {}
    items: list[dict] = []
    price = float(inputs.get("price") or v["price"] or 0)
    spend = float(inputs.get("marketing_spend") or 0)

    # 1. capacity: demand the kitchen / floor can't serve
    cap = v["capacity_per_day"]
    if cap and v["turned_away_per_day_last4w"] and v["turned_away_per_day_last4w"] > 0.08 * max(1.0, v["orders_per_day_last4w"]):
        lost = v["turned_away_per_day_last4w"]
        items.append({
            "key": "capacity", "impact": lost * 30 * max(0.0, price - float((res.get("summary") or {}).get("variable_cost_per_unit") or 0)),
            "title": "Capacity is the bottleneck",
            "detail": (f"In the last four simulated weeks you served about {_n(v['orders_per_day_last4w'])} {unit} a day — your limit is "
                       f"{_n(cap)} — and about {_n(lost)} more a day wanted you but were turned away."),
            "action": {"label": "Test 50% more capacity", "changes": {"capacity_scale": 1.5}},
        })
    # 2. awareness
    aw = v["awareness_week12"]
    mcurve = sens.get("marketing_curve") or []
    best_m = max(mcurve, key=lambda c: c["profit"]) if mcurve else None
    if aw is not None and aw < 0.6:
        tgt = best_m["spend"] if best_m and best_m["spend"] > spend * 1.1 else max(spend * 2, spend + 20000)
        items.append({
            "key": "awareness", "impact": (best_m["profit"] - float(v["static_profit_per_month"] or 0)) if best_m else 0,
            "title": "Too few people know you exist",
            "detail": (f"After 12 weeks only {_pct(aw)} of people in the market for this have heard of you, with {_inr(spend)} a month on marketing."
                       + (f" The marketing sweep peaks near {_inr(best_m['spend'])} a month." if best_m else "")),
            "action": {"label": f"Test {_inr(tgt)}/month marketing", "changes": {"marketing_spend": round(tgt, -2)}},
        })
    # 3. price
    curve = sens.get("price_curve") or []
    if curve:
        best = max(curve, key=lambda c: c["profit"])
        cur = float(v["static_profit_per_month"] or 0)
        if best["profit"] > cur * 1.08 + 5000 and abs(best["price"] - price) / max(price, 1) > 0.04:
            items.append({
                "key": "price", "impact": best["profit"] - cur,
                "title": "Your price is not the profit-maximising one",
                "detail": (f"At {_inr(price)} the model gives {_inr(cur)} a month. The price sweep peaks near {_inr(best['price'])} "
                           f"with about {_n(best['units'])} {unit} and {_inr(best['profit'])} a month."),
                "action": {"label": f"Test {price_label.lower()} {_inr(best['price'])}", "changes": {"price": round(best["price"])}},
            })
    if v["afford_share"] is not None and v["afford_share"] < 0.5:
        items.append({
            "key": "afford", "impact": 0,
            "title": "Most people can't afford you",
            "detail": f"Only {_pct(v['afford_share'])} of in-market people have a willingness to pay at or above {_inr(price)}.",
            "action": {"label": f"Test {_inr(round(price * 0.88))}", "changes": {"price": round(price * 0.88)}},
        })
    # 4. retention
    if v["repeat_share"] is not None and v["trial_rate"] and v["repeat_share"] < 0.25:
        q = float(inputs.get("quality") or 0.55)
        items.append({
            "key": "retention", "impact": 0,
            "title": "People try you but don't come back",
            "detail": f"{_pct(v['trial_rate'])} of aware people tried you, but only {_pct(v['repeat_share'])} of customers bought twice or more.",
            "action": {"label": "Test higher quality", "changes": {"quality": round(min(1.0, q + 0.12), 2)}},
        })
    # 5. growth trend
    mu = v["agent_month_units"]
    if len(mu) >= 2 and mu[0] > 0:
        g = mu[-1] / mu[0] - 1
        items.append({
            "key": "trend", "impact": 0, "title": "Growing" if g > 0.05 else ("Flat" if g > -0.05 else "Shrinking"),
            "detail": (f"Agent simulation: month 1 about {_n(mu[0])} {unit}, month {len(mu)} about {_n(mu[-1])} "
                       f"({'+' if g >= 0 else ''}{round(100 * g)}%)."
                       + (" Growth stops at your capacity." if cap and mu[-1] >= 0.95 * cap * 30 else "")),
            "action": None,
        })
    # 6. who beats you, and why
    comps = sorted(res.get("competitors") or [], key=lambda c: -float(c.get("modeled_units") or 0))
    drivers = [d["label"] for d in (abm.get("top_drivers_against_you") or [])[:3]]
    if comps:
        c0 = comps[0]
        items.append({
            "key": "competition", "impact": 0, "title": f"Strongest rival: {c0['name']}",
            "detail": (f"{c0['name']} at {round(float(c0.get('distance_km') or 0), 2)} km wins about {_n(c0.get('modeled_units'))} {unit} a month in the model."
                       + (f" Among people who chose someone else, the factors that hurt you most: {', '.join(drivers)}." if drivers else "")),
            "action": None,
        })
    # 7. risk
    pl = v["probability_of_loss"]
    if pl is not None and pl >= 0.25:
        items.append({"key": "risk", "impact": 0, "title": "High chance of a loss month",
                      "detail": f"Across the uncertainty runs, {_pct(pl)} of outcomes lose money in a month.", "action": None})

    actionable = sorted([i for i in items if i.get("action")], key=lambda i: -float(i.get("impact") or 0))
    other = [i for i in items if not i.get("action")]
    ordered = actionable + other
    spoken = " ".join(f"{i['title']}: {i['detail']}" for i in ordered[:3])
    if actionable:
        spoken += f" My suggestion: {actionable[0]['action']['label'].lower()} — say 'test it' or press the button and I'll run it on the map."
    return {"view": v, "insights": ordered, "spoken": spoken or "The run looks balanced; no single lever stands out.",
            "suggested": actionable[0]["action"] if actionable else None}


def _scenario_run(db: Session, p: Project, scenario_id: str | None) -> tuple[Scenario, SimulationRun | None]:
    s = next((x for x in p.scenarios if x.id == scenario_id), None) if scenario_id else None
    s = s or next((x for x in p.scenarios if x.is_baseline), None) or (p.scenarios[0] if p.scenarios else None)
    if s is None:
        raise HTTPException(409, "This project has no scenario")
    return s, latest_runs(db, p).get(s.id)


@router.get("/projects/{project_id}/insights")
def insights(project_id: str, scenario_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    s, r = _scenario_run(db, p, scenario_id)
    if r is None:
        raise HTTPException(409, "Run this scenario first")
    arch = ARCHETYPES[p.category["archetype"]]
    out = build_insights(r.results, s.inputs, arch.unit_label, arch.price_label)
    out["scenario"] = {"id": s.id, "name": s.name}
    return out


# ---------------------------------------------------------------- strategy test
class StrategyIn(BaseModel):
    from_scenario_id: str | None = None
    price: float | None = Field(default=None, gt=0, lt=10_000_000)
    marketing_spend: float | None = Field(default=None, ge=0, le=100_000_000)
    quality: float | None = Field(default=None, ge=0, le=1)
    capacity_scale: float | None = Field(default=None, gt=0, le=10)
    open_hour: float | None = Field(default=None, ge=0, le=24)
    close_hour: float | None = Field(default=None, ge=0, le=24)
    name: str | None = Field(default=None, max_length=80)


def apply_changes(arch, inputs: dict, ch: dict) -> tuple[dict, list[str]]:
    out = copy.deepcopy(inputs)
    label: list[str] = []
    if ch.get("price") is not None:
        out["price"] = float(ch["price"])
        label.append(_inr(out["price"]))
    if ch.get("marketing_spend") is not None:
        out["marketing_spend"] = float(ch["marketing_spend"])
        label.append(f"ads {_inr(out['marketing_spend'])}")
    if ch.get("quality") is not None:
        out["quality"] = float(ch["quality"])
        label.append(f"quality {round(100 * out['quality'])}")
    if ch.get("capacity_scale"):
        cap = dict(out.get("capacity") or {})
        for f in arch.capacity_fields:
            base = cap.get(f.key, f.default)
            # scale the throughput field(s); keep days-open untouched
            if base is not None and "days" not in f.key:
                cap[f.key] = round(float(base) * float(ch["capacity_scale"]), 2)
                break
        out["capacity"] = cap
        # capacity is not free (same rule as the optimizer, engine/explore.py): staff and utilities scale with it,
        # rent rises by half the increase, startup cost by 35% per 100% added
        sc = float(ch["capacity_scale"])
        out["payroll"] = float(out.get("payroll") or 0) * sc
        out["utilities"] = float(out.get("utilities") or 0) * sc
        out["rent"] = float(out.get("rent") or 0) * (1 + 0.5 * (sc - 1))
        out["startup_cost"] = float(out.get("startup_cost") or 0) * (1 + 0.35 * max(0.0, sc - 1))
        label.append(f"capacity ×{ch['capacity_scale']:g}")
    if ch.get("open_hour") is not None or ch.get("close_hour") is not None:
        off = dict(out.get("offer") or {"open_hour": None, "close_hour": None, "weekend_open": True, "attributes": {}})
        if ch.get("open_hour") is not None:
            off["open_hour"] = float(ch["open_hour"])
        if ch.get("close_hour") is not None:
            off["close_hour"] = float(ch["close_hour"])
        out["offer"] = off
        label.append(f"hours {int(off.get('open_hour') or 0)}–{int(off.get('close_hour') or 24)}")
    return out, label


def compare(before: dict, after: dict, unit: str) -> dict:
    def d(k):
        a, b = after.get(k), before.get(k)
        return None if a is None or b is None else a - b
    du, dp = d("month3_units"), d("month3_profit")
    grow = (du or 0) > 0.02 * max(1, before.get("month3_units") or 1)
    better = (dp or 0) > 0
    verdict = ("better" if better else "worse") if dp is not None else "unknown"
    s = (f"Month 3 in the agent simulation: {_n(after.get('month3_units'))} {unit} versus {_n(before.get('month3_units'))} before "
         f"({'+' if (du or 0) >= 0 else ''}{_n(du)}), and profit {_inr(after.get('month3_profit'))} versus {_inr(before.get('month3_profit'))}. ")
    if after.get("awareness_week12") is not None and before.get("awareness_week12") is not None:
        s += f"Awareness {_pct(before['awareness_week12'])} to {_pct(after['awareness_week12'])}. "
    if (after.get("turned_away_per_day_last4w") or 0) > 0.08 * max(1, after.get("orders_per_day_last4w") or 1):
        s += f"You are still turning away about {_n(after['turned_away_per_day_last4w'])} {unit} a day. "
    s += ("So this strategy grows the business and makes more money." if grow and better else
          "Sales grow, but profit falls — the extra customers cost more than they bring." if grow and not better else
          "Profit improves even though volume doesn't grow." if better else
          "This strategy does not help; I'd keep the earlier one.")
    return {"delta_units_month3": du, "delta_profit_month3": dp, "grows": grow, "verdict": verdict, "spoken": s}


def _run_strategy(project_id: str, body: dict) -> dict:
    with session_factory()() as db:
        p = db.get(Project, project_id)
        arch = ARCHETYPES[p.category["archetype"]]
        src = next((x for x in p.scenarios if x.id == body.get("from_scenario_id")), None) or next((x for x in p.scenarios if x.is_baseline), None)
        if src is None:
            raise HTTPException(409, "This project has no baseline scenario")
        runs = latest_runs(db, p)
        r0 = runs.get(src.id)
        if r0 is None:
            r0 = execute_run(db, p, src)
            if r0.status != "succeeded":
                raise HTTPException(422, r0.error or "Simulation failed")
        before = run_view(r0.results)
        inputs, label = apply_changes(arch, src.inputs, body)
        if not label:
            raise HTTPException(422, "Change at least one thing: price, marketing, quality, capacity or hours")
        name = (body.get("name") or ("Strategy: " + " · ".join(label)))[:120]
        s = next((x for x in p.scenarios if x.name == name), None)
        if s is None:
            if len(p.scenarios) >= MAX_SCENARIOS:
                pool = [x for x in p.scenarios if not x.is_baseline and (x.name.startswith("Strategy:") or x.name.startswith("Voice:"))]
                pool = pool or [x for x in p.scenarios if not x.is_baseline and x.id != src.id]
                if not pool:
                    raise HTTPException(422, "Scenario limit reached (12). Delete one first.")
                s = sorted(pool, key=lambda x: x.updated_at or x.created_at)[0]
                s.name = name
            else:
                s = Scenario(project_id=p.id, location_id=src.location_id, name=name, is_baseline=False, inputs={})
                db.add(s)
        s.inputs, s.location_id = inputs, src.location_id
        s.updated_at = p.updated_at = utcnow()
        db.commit()
        run = execute_run(db, p, s)
        if run.status != "succeeded":
            raise HTTPException(422, run.error or "Simulation failed")
        after = run_view(run.results)
        cmp = compare(before, after, arch.unit_label)
        ins = build_insights(run.results, inputs, arch.unit_label, arch.price_label)
        return {"scenario": {"id": s.id, "name": s.name}, "from": {"id": src.id, "name": src.name, "run_id": r0.id},
                "run_id": run.id, "before": before, "after": after, "comparison": cmp, "next_insights": ins["insights"][:3],
                "spoken": cmp["spoken"]}


@router.post("/projects/{project_id}/strategy")
async def test_strategy(project_id: str, body: StrategyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    return await run_in_threadpool(_run_strategy, p.id, body.model_dump())
