"""Rule-based decision layer. Every statement is derived from computed results.

Input: a list of scenario results (output of ``simulate``) plus evidence
metadata about the market snapshot. Output: verdict, ranking for the user's
objective, recommendations, next verification actions and "what could make
this wrong". No LLM is involved here; an optional LLM may later *paraphrase*
this structure, never change its numbers.
"""
from __future__ import annotations

from typing import Literal

Objective = Literal["profit", "low_risk", "break_even", "growth"]

OBJECTIVE_LABELS = {
    "profit": "highest expected operating profit",
    "low_risk": "lowest modeled chance of loss",
    "break_even": "fastest payback of startup cost",
    "growth": "most customers served",
}


def _money(x):
    if x is None:
        return "n/a"
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e7:
        return f"{sign}{x / 1e7:.2f} Cr"
    if x >= 1e5:
        return f"{sign}{x / 1e5:.2f} L"
    return f"{sign}{x:,.0f}"


def _profit(r):
    mc = r.get("monte_carlo")
    return (mc or {}).get("profit", {}).get("p50") if mc else r["finance"]["operating_profit"]


def score(r: dict, objective: Objective) -> float:
    mc = r.get("monte_carlo") or {}
    if objective == "low_risk":
        pl = mc.get("prob_loss")
        p10 = (mc.get("profit") or {}).get("p10") or r["finance"]["operating_profit"] or 0
        return -(pl if pl is not None else 1.0) * 1e9 + p10
    if objective == "break_even":
        pb = r["finance"]["payback_months"]
        return -(pb if pb is not None else 1e6)
    if objective == "growth":
        return r["summary"]["units_sold"] or 0
    return _profit(r) or -1e12


def rank(scenarios: list[dict], objective: Objective) -> list[dict]:
    rows = []
    for s in scenarios:
        r = s["result"]
        mc = r.get("monte_carlo") or {}
        rows.append({
            "scenario_id": s["id"], "name": s["name"], "is_baseline": s.get("is_baseline", False),
            "score": score(r, objective),
            "units": r["summary"]["units_sold"], "profit": r["finance"]["operating_profit"],
            "profit_p10": (mc.get("profit") or {}).get("p10"), "profit_p50": (mc.get("profit") or {}).get("p50"),
            "prob_loss": mc.get("prob_loss"), "payback_months": r["finance"]["payback_months"],
            "break_even_units": r["finance"]["break_even_units"],
        })
    rows.sort(key=lambda x: -x["score"])
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return rows


def _gaps(evidence: dict, result: dict) -> list[dict]:
    gaps = []
    comps = result.get("competitors", [])
    n_unknown_price = sum(1 for c in comps if c["price_status"] == "assumed")
    if not comps:
        gaps.append({"key": "no_competitors", "severity": "high", "text": "No competitors were found in the data sources for this catchment. Either the market is unserved or the map data is incomplete.",
                     "action": "Walk or drive the catchment and add every competitor you see. An empty map is more often a data gap than an empty market."})
    if n_unknown_price:
        gaps.append({"key": "competitor_prices", "severity": "high", "text": f"{n_unknown_price} of {len(comps)} competitor prices are unknown and were assumed.",
                     "action": "Call or visit the nearest competitors to record their actual prices, then re-run."})
    if result["summary"]["reference_price_status"] != "user" and result["summary"]["reference_price_status"] != "derived_from_competitor_prices":
        gaps.append({"key": "reference_price", "severity": "high", "text": "The typical local price was not provided, so affordability is measured against your own baseline price.",
                     "action": "Enter the typical price charged locally (from competitor checks) so affordability is judged against the real market."})
    if evidence.get("population_method") == "uniform":
        gaps.append({"key": "population_spatial", "severity": "medium", "text": "Population was spread evenly across the catchment because building data was unavailable.",
                     "action": "Treat zone-level demand patterns as rough; verify where residents actually live."})
    if evidence.get("population_source") == "user":
        gaps.append({"key": "population_user", "severity": "high", "text": "Catchment population is a user-entered figure.", "action": "Confirm it against census or ward data."})
    if evidence.get("population_source") == "estimate_buildings":
        gaps.append({"key": "population_estimate", "severity": "high", "text": "Population is a rough building-count estimate because WorldPop was unavailable.",
                     "action": "Reload market data later, or enter a census/ward population figure for the catchment."})
    if evidence.get("catchment_method") == "radius":
        gaps.append({"key": "catchment_radius", "severity": "low", "text": "Catchment is a straight-line radius, not a travel-time area.", "action": "Configure a routing key to use travel-time catchments."})
    cov = evidence.get("coverage") or {}
    if cov.get("level") in ("low", "unknown"):
        gaps.append({"key": "coverage", "severity": "medium", "text": cov.get("note") or "Map coverage looks thin in this area.", "action": "Verify local businesses before making a high-cost location decision."})
    if result["finance"]["fixed_breakdown"].get("rent", 0) == 0:
        gaps.append({"key": "rent", "severity": "high", "text": "Rent is zero in this scenario.", "action": "Enter the actual quoted rent and deposit for the property."})
    return gaps


def decide(scenarios: list[dict], objective: Objective, evidence: dict, archetype_label: str) -> dict:
    if not scenarios:
        return {"verdict": "no_conclusion", "headline": "No scenario has been simulated yet.", "recommendations": [], "next_actions": [], "risks": [], "ranking": []}
    ranking = rank(scenarios, objective)
    by_id = {s["id"]: s for s in scenarios}
    best = by_id[ranking[0]["scenario_id"]]
    base = next((s for s in scenarios if s.get("is_baseline")), scenarios[0])
    r, rb = best["result"], base["result"]
    mc = r.get("monte_carlo") or {}
    pl = mc.get("prob_loss")
    p50 = _profit(r)
    gaps = _gaps(evidence, r)
    high_gaps = [g for g in gaps if g["severity"] == "high"]
    unit = r["unit_label"]

    if p50 is not None and p50 > 0 and (pl is None or pl < 0.25):
        verdict = "potentially_viable"
        head = f"'{best['name']}' appears financially viable under the current assumptions"
    elif p50 is not None and p50 < 0 and (pl is None or pl > 0.7):
        verdict = "financially_challenging"
        head = f"'{best['name']}' is financially challenging under the current inputs"
    else:
        verdict = "high_uncertainty"
        head = f"'{best['name']}' could go either way under the current assumptions"
    if high_gaps:
        head += ", but key evidence is missing and the result should be treated as provisional."
        if verdict == "high_uncertainty":
            verdict = "more_evidence_required"
    else:
        head += "."

    recs = []
    top_driver = (r.get("drivers") or [{}])[0]
    thr = ((r.get("sensitivity") or {}).get("thresholds") or {}).get("participation_break_even")
    part = r["parameters"]["participation"]["value"]
    reconsider = (
        f"Reconsider if field evidence suggests fewer than {thr * 100:.1f}% of residents use this category (model assumes {part * 100:.1f}%)."
        if thr else "Reconsider if verified demand is materially below the modeled estimate."
    )
    if best["id"] != base["id"]:
        d_profit = (r["finance"]["operating_profit"] or 0) - (rb["finance"]["operating_profit"] or 0)
        d_units = (r["summary"]["units_sold"] or 0) - (rb["summary"]["units_sold"] or 0)
        recs.append({
            "action": f"Prefer '{best['name']}' over the baseline for {OBJECTIVE_LABELS[objective]}.",
            "reason": f"Modeled monthly operating profit {_money(r['finance']['operating_profit'])} vs {_money(rb['finance']['operating_profit'])}; {r['summary']['units_sold']:.0f} vs {rb['summary']['units_sold']:.0f} {unit}.",
            "change_vs_baseline": {"operating_profit": round(d_profit, 2), "units": round(d_units, 1)},
            "main_uncertainty": top_driver.get("label", "Demand assumptions"),
            "verify_next": high_gaps[0]["action"] if high_gaps else "Run a small pilot to measure real conversion.",
            "reconsider_if": reconsider,
        })
    sens = r.get("sensitivity") or {}
    curve = sens.get("price_curve") or []
    if curve:
        best_pt = max(curve, key=lambda x: x["profit"] if x["profit"] is not None else -1e18)
        cur = r["summary"]["price"]
        if best_pt["price"] and abs(best_pt["price"] - cur) / cur > 0.08 and (best_pt["profit"] or 0) > (r["finance"]["operating_profit"] or 0):
            recs.append({
                "action": f"Test a price near {_money(best_pt['price'])} (currently {_money(cur)}).",
                "reason": f"In the price sweep, modeled profit peaks around {_money(best_pt['price'])} at {_money(best_pt['profit'])}/month.",
                "change_vs_baseline": {"operating_profit": round((best_pt['profit'] or 0) - (r['finance']['operating_profit'] or 0), 2)},
                "main_uncertainty": "Price sensitivity and competitor prices are assumptions.",
                "verify_next": "Pilot two price points (e.g. launch offer vs standard) and measure sign-ups.",
                "reconsider_if": "Competitor price checks show the local reference price differs from the model's.",
            })
    if r["summary"]["capacity_bound"]:
        recs.append({
            "action": "Capacity, not demand, limits this scenario.",
            "reason": f"Modeled demand {r['summary']['modeled_demand_units']:.0f} exceeds capacity {r['summary']['capacity_units']:.0f} {unit}.",
            "change_vs_baseline": {}, "main_uncertainty": "Whether the demand estimate holds.",
            "verify_next": "Price for the capacity you have, or plan staged expansion.", "reconsider_if": "Demand estimate falls after verification.",
        })
    mcurve = sens.get("marketing_curve") or []
    if len(mcurve) > 2:
        cur_spend = r["finance"]["fixed_breakdown"].get("marketing", 0)
        best_m = max(mcurve, key=lambda x: x["profit"] if x["profit"] is not None else -1e18)
        if best_m["spend"] is not None and abs(best_m["spend"] - cur_spend) > 0.2 * max(cur_spend, 5000) and (best_m["profit"] or 0) - (r["finance"]["operating_profit"] or 0) > 1000:
            recs.append({
                "action": f"Consider marketing spend around {_money(best_m['spend'])}/month (currently {_money(cur_spend)}).",
                "reason": f"Modeled profit at that spend is {_money(best_m['profit'])}/month.",
                "change_vs_baseline": {"operating_profit": round((best_m['profit'] or 0) - (r['finance']['operating_profit'] or 0), 2)},
                "main_uncertainty": "The awareness-response curve is an uncalibrated assumption.",
                "verify_next": "Run a tracked campaign (unique code / landing number) and measure cost per customer.",
                "reconsider_if": "Measured cost per acquired customer exceeds the unit margin.",
            })

    risks = []
    for t in (sens.get("tornado") or [])[:3]:
        risks.append({"factor": t["label"], "text": f"If {t['label'].lower()} is at the low/high end of its assumed range, monthly profit ranges from {_money(min(t['profit_at_low'], t['profit_at_high']))} to {_money(max(t['profit_at_low'], t['profit_at_high']))}.", "status": t["status"]})
    for st in sens.get("stress_tests") or []:
        if (st["delta_profit"] or 0) < 0 and (st["profit"] or 0) < 0 <= (r["finance"]["operating_profit"] or 0):
            risks.append({"factor": st["label"], "text": f"{st['label']}: profit falls to {_money(st['profit'])}/month.", "status": "stress_test"})
    for g in gaps:
        risks.append({"factor": "Data gap", "text": g["text"], "status": g["severity"]})

    next_actions = [{"action": g["action"], "why": g["text"], "priority": g["severity"]} for g in gaps]
    next_actions.append({"action": "Interview 20-30 potential customers in the catchment about price and travel.", "why": f"Participation and price sensitivity drive most of the result for {archetype_label.lower()}.", "priority": "medium"})

    return {
        "verdict": verdict, "headline": head, "objective": objective, "objective_label": OBJECTIVE_LABELS[objective],
        "best_scenario_id": best["id"], "ranking": ranking, "recommendations": recs, "next_actions": next_actions,
        "risks": risks, "gaps": gaps,
        "financial_summary": {
            "scenario": best["name"], "revenue": r["finance"]["revenue"], "operating_cost": (r["finance"]["fixed_cost"] or 0) + (r["finance"]["variable_cost"] or 0),
            "operating_profit": r["finance"]["operating_profit"], "profit_p10": (mc.get("profit") or {}).get("p10"),
            "profit_p90": (mc.get("profit") or {}).get("p90"), "prob_loss": pl, "break_even_units": r["finance"]["break_even_units"],
            "utilization": r["finance"]["utilization"], "startup_cost": r["finance"]["startup_cost"], "payback_months": r["finance"]["payback_months"],
            "unit_label": unit,
        },
        "drivers": r.get("drivers", [])[:5],
        "method_note": "Verdicts, rankings and recommendations are produced by documented rules applied to the simulation outputs. Driver importance uses Spearman rank correlation across Monte Carlo draws and one-at-a-time sensitivity, which describe the model, not proven real-world causes.",
    }
