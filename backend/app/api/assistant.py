"""Voice / chat assistant endpoints.

The assistant never invents numbers. Every figure it speaks comes from:
  * the project's latest market snapshot (OpenStreetMap / WorldPop evidence), or
  * the latest succeeded simulation runs (the tested numpy engine), or
  * the rule-based decision engine.

Three entry points:
  GET  /projects/{id}/assistant/facts      compact fact sheet (used as a tool by the realtime voice agent)
  POST /projects/{id}/assistant/try-price  run a what-if price scenario through the real engine
  POST /projects/{id}/assistant/ask        intent-routed answer for the built-in browser voice mode
  POST /assistant/ask                      general product questions (no project needed)
"""
from __future__ import annotations

import copy
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import ai
from ..categories.archetypes import ARCHETYPES
from ..db import get_db, session_factory
from ..models import Project, Scenario, User, utcnow
from ..security import current_user, owned_project
from ..services.runs import competitors_for, execute_run, latest_runs, latest_snapshot
from ..engine.geo import haversine_km
from .decisions import _decision

router = APIRouter(tags=["assistant"])
log = logging.getLogger("strataiq.assistant")


# ---------------------------------------------------------------- formatting
def inr(x: float | None) -> str:
    """Indian-style rupee amount that also reads well aloud: ₹42,500 / ₹3.4 lakh / ₹1.2 crore."""
    if x is None:
        return "unknown"
    neg = x < 0
    v = abs(float(x))
    if v >= 1e7:
        s = f"₹{v / 1e7:.2f} crore".replace(".00 ", " ")
    elif v >= 1e5:
        s = f"₹{v / 1e5:.2f} lakh".replace(".00 ", " ")
    else:
        n = f"{int(round(v)):,}"
        # 1,23,456 grouping
        digits = str(int(round(v)))
        if len(digits) > 3:
            head, tail = digits[:-3], digits[-3:]
            head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
            n = f"{head},{tail}"
        s = f"₹{n}"
    return ("minus " if neg else "") + s


def pct(x: float | None) -> str:
    return "unknown" if x is None else f"{round(100 * float(x))}%"


def num(x: float | None) -> str:
    if x is None:
        return "unknown"
    return f"{int(round(float(x))):,}"


# ---------------------------------------------------------------- facts
def build_facts(db: Session, p: Project) -> dict:
    arch = ARCHETYPES[p.category["archetype"]]
    loc = p.locations[0] if p.locations else None
    facts: dict = {
        "project": p.name, "business_type": p.category.get("label"), "model_type": arch.label, "unit": arch.unit_label,
        "is_demo": p.is_demo, "location": None, "market": None, "baseline": None, "scenarios": [], "decision": None,
    }
    if loc:
        facts["location"] = {"label": loc.label, "address": loc.address, "lat": round(loc.lat, 5), "lng": round(loc.lng, 5)}
        snap = latest_snapshot(db, loc.id)
        if snap:
            radius = float(snap.population.get("radius_km") or arch.default_catchment_km)
            comps = competitors_for(db, p, loc, radius)
            ranked = sorted(comps, key=lambda c: float(haversine_km(loc.lat, loc.lng, c.lat, c.lng)))
            facts["market"] = {
                "data_retrieved_at": snap.retrieved_at.isoformat() if snap.retrieved_at else None,
                "catchment_radius_km": round(radius, 2),
                "population_in_catchment": round(float(snap.population.get("total") or 0)) or None,
                "population_source": snap.population.get("source"),
                "competitors_found": len(comps),
                "competitors_named": sum(1 for c in comps if c.name),
                "competitor_sources": sorted({s.get("name") for s in (snap.sources or []) if s.get("layer") == "competitors"}),
                "nearest_competitors": [{"name": c.name or "Unnamed", "distance_km": round(float(haversine_km(loc.lat, loc.lng, c.lat, c.lng)), 2),
                                         "price": c.price, "source": c.source} for c in ranked[:6]],
                "coverage": (snap.coverage or {}).get("level"),
                "coverage_note": (snap.coverage or {}).get("note"),
                "failed_layers": sorted({e.get("source") for e in (snap.errors or []) if e.get("source")}),
            }
    runs = latest_runs(db, p)
    for s in p.scenarios:
        r = runs.get(s.id)
        if not r:
            facts["scenarios"].append({"name": s.name, "price": s.inputs.get("price"), "status": "not run"})
            continue
        res = r.results
        mc = res.get("monte_carlo") or {}
        fin = res["finance"]
        row = {
            "name": s.name, "is_baseline": s.is_baseline, "price": res["summary"]["price"],
            "customers_or_units_per_month": round(res["summary"]["units_sold"]),
            "people_in_market": round(res["summary"]["in_market_units"]),
            "revenue_per_month": round(fin["revenue"]), "fixed_cost_per_month": round(fin["fixed_cost"]),
            "variable_cost_per_month": round(fin["variable_cost"]),
            "operating_profit_per_month": round(fin["operating_profit"]),
            "profit_p10": None if not mc else round((mc.get("profit") or {}).get("p10") or 0),
            "profit_p90": None if not mc else round((mc.get("profit") or {}).get("p90") or 0),
            "probability_of_loss": mc.get("prob_loss"),
            "break_even_units": None if fin["break_even_units"] is None else round(fin["break_even_units"]),
            "capacity_utilization": round(fin["utilization"], 3) if fin.get("utilization") is not None else None,
            "payback_months": None if fin.get("payback_months") is None else round(fin["payback_months"], 1),
            "startup_cost": fin.get("startup_cost"),
            "share_who_can_afford": [{"segment": g["label"], "afford_share": round(g["affordability_at_price"], 3)} for g in res.get("segments", [])],
            "top_competitors_by_modeled_customers": [{"name": c["name"], "modeled_units": round(c["modeled_units"]), "distance_km": round(c["distance_km"], 2)}
                                                    for c in sorted(res.get("competitors", []), key=lambda c: -c["modeled_units"])[:3]],
            "drivers": [d["label"] for d in (res.get("drivers") or [])[:3]],
        }
        curve = (res.get("sensitivity") or {}).get("price_curve") or []
        if curve:
            best = max(curve, key=lambda c: c["profit"])
            row["price_curve_best"] = {"price": round(best["price"]), "profit": round(best["profit"]), "units": round(best["units"])}
        abm = res.get("abm") or {}
        if abm:
            row["agent_simulation"] = {"agents": abm.get("n_agents"), "days": abm.get("days"), "ramp_up_week": abm.get("ramp_up_week"),
                                       "awareness_final": (abm.get("metrics") or {}).get("aware_final"),
                                       "trial_rate": (abm.get("metrics") or {}).get("trial_rate")}
        facts["scenarios"].append(row)
        if s.is_baseline:
            facts["baseline"] = row
    if runs:
        d = _decision(db, p, None)
        facts["decision"] = {"verdict": d.get("verdict"), "headline": d.get("headline"), "goal": d.get("objective_label"),
                             "best_scenario": next((r["name"] for r in d.get("ranking", []) if r.get("rank") == 1), None),
                             "next_actions": [a["action"] for a in (d.get("next_actions") or [])[:3]],
                             "risks": [r["text"] for r in (d.get("risks") or [])[:3]]}
    return facts


@router.get("/projects/{project_id}/assistant/facts")
def facts(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    return build_facts(db, p)


# ---------------------------------------------------------------- what-if runs
class TryPrice(BaseModel):
    price: float = Field(gt=0, lt=10_000_000)


def _run_price(project_id: str, price: float) -> dict:
    with session_factory()() as db:
        p = db.get(Project, project_id)
        base = next((s for s in p.scenarios if s.is_baseline), None)
        if base is None:
            raise HTTPException(409, "This project has no baseline scenario")
        name = f"Voice: price {inr(price)}"
        s = next((x for x in p.scenarios if x.name == name), None)
        if s is None:
            if len(p.scenarios) >= 12:
                s = next((x for x in p.scenarios if x.name.startswith("Voice: ")), None)
                if s is None:
                    raise HTTPException(422, "Scenario limit reached (12). Delete one first.")
                s.name = name
            else:
                s = Scenario(project_id=p.id, location_id=base.location_id, name=name, is_baseline=False, inputs={})
                db.add(s)
        inputs = copy.deepcopy(base.inputs)
        inputs["price"] = float(price)
        s.inputs = inputs
        s.location_id = base.location_id
        p.updated_at = utcnow()
        db.commit()
        runs = latest_runs(db, p)
        if base.id not in runs:
            r0 = execute_run(db, p, base)
            if r0.status != "succeeded":
                raise HTTPException(422, r0.error or "Baseline simulation failed")
        run = execute_run(db, p, s)
        if run.status != "succeeded":
            raise HTTPException(422, run.error or "Simulation failed")
        db.expire_all()
        p = db.get(Project, project_id)
        f = build_facts(db, p)
        new = next((x for x in f["scenarios"] if x["name"] == name), None)
        return {"scenario": name, "scenario_id": s.id, "run_id": run.id, "baseline": f["baseline"], "what_if": new}


@router.post("/projects/{project_id}/assistant/try-price")
async def try_price(project_id: str, body: TryPrice, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    out = await run_in_threadpool(_run_price, p.id, body.price)
    out["spoken"] = compare_sentence(out["baseline"], out["what_if"], ARCHETYPES[p.category["archetype"]].unit_label)
    return out


def compare_sentence(b: dict | None, w: dict | None, unit: str) -> str:
    if not b or not w:
        return "The scenario ran, but I could not compare it with the baseline."
    dp = w["operating_profit_per_month"] - b["operating_profit_per_month"]
    du = w["customers_or_units_per_month"] - b["customers_or_units_per_month"]
    better = "higher" if dp > 0 else "lower"
    s = (f"At {inr(w['price'])} instead of {inr(b['price'])}, the model gives about {num(w['customers_or_units_per_month'])} {unit} a month "
         f"({'+' if du >= 0 else ''}{num(du)} versus baseline) and an operating profit of {inr(w['operating_profit_per_month'])} a month, "
         f"which is {inr(abs(dp))} {better} than the baseline.")
    if w.get("probability_of_loss") is not None and b.get("probability_of_loss") is not None:
        s += f" Modeled chance of a monthly loss goes from {pct(b['probability_of_loss'])} to {pct(w['probability_of_loss'])}."
    return s


# ---------------------------------------------------------------- intent router (browser voice mode)
class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=600)
    page: str | None = None


NAV = {
    "market": ["market map", "map", "competitor map", "naksha"],
    "live": ["live", "agents", "agent simulation", "live market", "people"],
    "genome": ["dna", "genome", "market dna"],
    "simulation": ["simulation", "lab", "scenario", "simulator"],
    "decisions": ["decision", "decisions", "recommendation", "verdict page"],
    "report": ["report", "pdf"],
    "factors": ["factors", "615"],
    "monitor": ["monitor", "monitoring", "actuals"],
}

INTENTS: list[tuple[str, list[str]]] = [
    ("try_price", [r"\b(try|test|simulate|run|what if|kya hoga|check)\b.*\b(price|fee|charge|₹|rs|rupees?|\d{3,})", r"\bprice (of|at|to) \d"]),
    ("navigate", [r"\b(open|show|go to|take me|navigate|dikhao|kholo)\b"]),
    ("competitors", [r"compet", r"rival", r"\bnearby\b", r"\baround\b", r"kitne .*(gym|shop|cafe|store)", r"other (gyms|shops|cafes|stores)"]),
    ("breakeven", [r"break.?even", r"\bbep\b", r"recover", r"payback"]),
    ("risk", [r"risk", r"\bloss\b", r"nuksan", r"\bsafe\b", r"downside", r"worst"]),
    ("price", [r"price", r"pricing", r"\bfee\b", r"charge", r"kitna .*(lena|rakhu|rakhna)", r"afford"]),
    ("profit", [r"profit", r"revenue", r"\bearn", r"income", r"kamai", r"munafa", r"money", r"sales"]),
    ("customers", [r"customer", r"member", r"demand", r"how many people", r"footfall", r"orders"]),
    ("population", [r"population", r"people live", r"catchment", r"residents", r"log rehte"]),
    ("verdict", [r"should i", r"viable", r"worth", r"kya karu", r"recommend", r"verdict", r"good idea", r"open (it|here)", r"go ahead"]),
    ("next", [r"next step", r"what (should|do) i do", r"verify", r"to.?do", r"aage"]),
    ("data", [r"real data", r"source", r"where.*data", r"fake", r"accurate", r"trust"]),
    ("greet", [r"^(hi|hello|hey|namaste|namaskar)\b"]),
]


def detect(q: str) -> str:
    ql = q.lower()
    for name, pats in INTENTS:
        if name == "navigate" and not nav_target(ql):
            continue
        if any(re.search(pt, ql) for pt in pats):
            return name
    return "unknown"


_PRICE = re.compile(r"(?:₹|rs\.?|inr|rupees?)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|hazaar|hazar)?", re.I)


def parse_price(q: str) -> float | None:
    best = None
    for m in _PRICE.finditer(q):
        v = float(m.group(1).replace(",", ""))
        if m.group(2):
            v *= 1000
        if v >= 10 and (best is None or v > best):
            best = v
    return best


def nav_target(q: str) -> str | None:
    ql = q.lower()
    for seg, words in NAV.items():
        if any(w in ql for w in words):
            return seg
    return None


def answer_from_facts(intent: str, f: dict, q: str) -> str | None:
    b, m, d = f.get("baseline"), f.get("market"), f.get("decision")
    unit = f.get("unit") or "customers"
    if intent == "greet":
        return f"Namaste. I'm looking at {f['project']}, a {f['business_type'].lower()} project. Ask me about competitors, profit, risk, pricing, or say 'try price' with a number."
    if intent == "competitors":
        if not m:
            return "Market data has not loaded for this location yet. Open the market map and load live data first."
        n = m["competitors_found"]
        if n == 0:
            return ("I found no mapped competitors inside the catchment. That may mean the area is under-mapped rather than empty, "
                    "so verify on the ground before relying on it.")
        near = m["nearest_competitors"][:3]
        names = "; ".join(f"{c['name']} at {c['distance_km']} kilometres" for c in near)
        s = f"There are {n} competitors mapped within about {m['catchment_radius_km'] + 1:.1f} kilometres. The nearest are {names}."
        if b and b.get("top_competitors_by_modeled_customers"):
            top = b["top_competitors_by_modeled_customers"][0]
            s += f" In the simulation the strongest is {top['name']}, with about {num(top['modeled_units'])} {unit} a month."
        return s
    if not b:
        if intent in ("population",) and m:
            return f"About {num(m['population_in_catchment'])} people live in the {m['catchment_radius_km']} kilometre catchment, from WorldPop."
        return "There's no finished simulation yet. Run the baseline in the simulation lab and I can talk you through the numbers."
    if intent == "profit":
        s = (f"For the baseline at {inr(b['price'])}, the model estimates about {num(b['customers_or_units_per_month'])} {unit} a month, "
             f"revenue of {inr(b['revenue_per_month'])}, and operating profit of {inr(b['operating_profit_per_month'])} a month.")
        if b.get("profit_p10") is not None:
            s += f" The realistic range is {inr(b['profit_p10'])} to {inr(b['profit_p90'])}."
        return s
    if intent == "breakeven":
        if b.get("break_even_units") is None:
            return "With the current inputs the unit margin is not positive, so there is no break-even point. Price must exceed variable cost per unit."
        s = f"You need about {num(b['break_even_units'])} {unit} a month to break even. The baseline is at {num(b['customers_or_units_per_month'])}."
        if b.get("payback_months"):
            s += f" Startup cost pays back in about {b['payback_months']} months under these assumptions."
        return s
    if intent == "risk":
        s = ""
        if b.get("probability_of_loss") is not None:
            s = f"Across the uncertainty runs, the modeled chance of a monthly loss is {pct(b['probability_of_loss'])}. In a bad case, profit is about {inr(b['profit_p10'])} a month. "
        if d and d.get("risks"):
            s += "Main risks: " + " ".join(d["risks"][:2])
        return s or "Risk figures are not available for this run."
    if intent == "price":
        s = f"You're charging {inr(b['price'])}."
        aff = b.get("share_who_can_afford") or []
        if aff:
            s += " Share who can afford it: " + ", ".join(f"{a['segment'].lower()} {pct(a['afford_share'])}" for a in aff) + "."
        best = b.get("price_curve_best")
        if best:
            s += f" On the price sweep, profit peaks near {inr(best['price'])} at about {inr(best['profit'])} a month. Say 'try price' and a number to run it."
        return s
    if intent == "customers":
        s = f"The baseline captures about {num(b['customers_or_units_per_month'])} {unit} a month out of roughly {num(b['people_in_market'])} people in the market for this."
        if b.get("capacity_utilization") is not None:
            s += f" That's {pct(b['capacity_utilization'])} of your capacity."
        return s
    if intent == "population":
        if m and m.get("population_in_catchment"):
            return f"About {num(m['population_in_catchment'])} people live within {m['catchment_radius_km']} kilometres, from the WorldPop grid."
        return "Population for this catchment is not available."
    if intent == "verdict":
        if d:
            s = d["headline"]
            if d.get("next_actions"):
                s += " First thing to do: " + d["next_actions"][0]
            return s
    if intent == "next":
        if d and d.get("next_actions"):
            return "Next steps: " + " Then, ".join(d["next_actions"][:3])
    if intent == "data":
        src = ", ".join(m["competitor_sources"]) if m and m.get("competitor_sources") else "OpenStreetMap"
        return (f"Competitors come live from {src}; population from WorldPop's 100 metre grid; the people on the map are synthetic agents, "
                "not real individuals; and every number comes from the simulation engine, not from me.")
    return None


GENERAL = ("StrataIQ lets you test a business before you invest. Pick any business and any place in India or the world. "
           "It loads real competitors from OpenStreetMap and real population from WorldPop, then simulates ten thousand synthetic customers "
           "choosing between you, your competitors, or nothing, and turns that into profit, risk and break-even. "
           "Start with 'Simulate your business', or open the live demo.")


@router.post("/assistant/ask")
async def ask_general(body: Ask):
    intent = detect(body.question)
    actions = []
    if intent == "navigate" or "demo" in body.question.lower():
        if "demo" in body.question.lower():
            actions.append({"type": "demo"})
        elif any(w in body.question.lower() for w in ("start", "new", "create", "simulate")):
            actions.append({"type": "navigate", "to": "/app/projects/new"})
    return {"answer": GENERAL if intent != "greet" else "Namaste! " + GENERAL, "intent": intent, "actions": actions, "grounded": True}


@router.post("/projects/{project_id}/assistant/ask")
async def ask(project_id: str, body: Ask, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    q = body.question.strip()
    intent = detect(q)
    actions: list[dict] = []
    if intent == "try_price":
        price = parse_price(q)
        if price:
            out = await run_in_threadpool(_run_price, p.id, price)
            ans = compare_sentence(out["baseline"], out["what_if"], ARCHETYPES[p.category["archetype"]].unit_label)
            return {"answer": ans, "intent": intent, "actions": [{"type": "refresh"}, {"type": "navigate", "to": "simulation"}], "grounded": True}
        intent = "price"
    if intent == "navigate":
        seg = nav_target(q)
        if seg:
            return {"answer": f"Opening the {seg.replace('genome', 'market DNA')} view.", "intent": intent,
                    "actions": [{"type": "navigate", "to": seg}], "grounded": True}
        intent = detect(re.sub(r"\b(open|show|go to|take me|navigate|dikhao|kholo)\b", "", q.lower()))
    f = build_facts(db, p)
    text = answer_from_facts(intent, f, q)
    if text:
        return {"answer": text, "intent": intent, "actions": actions, "grounded": True}
    # Open question: let the LLM phrase an answer from the fact sheet, but only keep it if every number is grounded.
    if ai.enabled():
        sys = ("You are StrataIQ's voice analyst for an Indian small-business owner. Answer in 2-4 short spoken sentences, "
               "in the same language the user used (English or Hinglish). Use ONLY facts and numbers in the JSON. "
               "If the JSON does not contain the answer, say what you can't tell and what to check. Money in rupees, Indian style (lakh/crore).")
        resp = await ai._call(sys, f"Facts: {json.dumps(f, default=str)[:9000]}\n\nQuestion: {q}", None, 300)
        if resp:
            t = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text").strip()
            if t and ai.grounded(t, f):
                return {"answer": t, "intent": "llm", "actions": actions, "grounded": True}
    return {"answer": ("I can answer about competitors, profit, break-even, risk, pricing, customers, population and next steps, "
                       "or run a what-if: say 'try price 1500'."), "intent": "help", "actions": actions, "grounded": True}
