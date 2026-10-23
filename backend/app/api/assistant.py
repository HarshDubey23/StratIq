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
    screen: dict | None = None  # what the user is looking at right now (published by the page)
    suggested: dict | None = None  # the last action the assistant suggested ("test it" runs this)


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
    ("apply_suggestion", [r"^(ok |okay |haan |yes |ha )?(test|run|try|do|apply|karo|kar do|chalao) (it|that|this|ye|yeh|wo|woh)\b", r"^(test|run) (the )?suggestion", r"\bsuggestion (test|run|chalao)"]),
    ("strategy", [r"\b(try|test|simulate|run|what if|kya hoga|check|increase|double|badha\w*|raise|cut|reduce|spend|add)\b.*\b(marketing|ads?|advertis\w*|promotion|capacity|kitchen|staff|quality|hours|timing|open|close)\b",
                  r"\b(marketing|ads?|capacity|quality)\b.*\b(double|badha\w*|\d{2,})",
                  r"\bopen\w*\s+(from\s+)?\d{1,2}\s*(am|pm)?\s*(to|till|until|-)\s*\d", r"\b(close|band)\w*\s+(at\s+)?\d{1,2}\s*(am|pm)"]),
    ("explain_agents", [r"how (do|does|did) (the )?(agents?|people|customers) (decide|choose|pick)", r"agents? .*\b(decide|choose|chunte|select)", r"\b615\b", r"kaise (decide|choose|chun)", r"\bgenome\b.*\bwork", r"why (did|does) (this|an?) agent"]),
    ("screen", [r"what (am i|are we|is) (looking|seeing|on)", r"\bthis (page|screen|map|chart|graph)\b", r"(yeh|ye|is) (page|map|screen|chart)", r"explain (this|the map|the screen|the chart|what)", r"what do you see", r"kya dikh", r"where am i"]),
    ("start_idea", [r"\b(i want to|i wanna|i plan to|planning to|thinking of|want to) (open|start|launch)\b", r"\b(kholna|kholni|shuru karna)\b.*\b(hai|chahta|chahti)\b",
                    r"\b(new|another) (idea|analysis|business|project)\b.*\b(in|at|near|for)\b"]),
    ("find_site", [r"\b(best|better|ideal|right|optimal|top) (location|site|place|spot|area|jagah)", r"where (should|do|can) (i|we) (open|start|put|locate)", r"kahan (kholu|kholun|kholna|khole)",
                   r"\b(location|site) (finder|scan|suggest)", r"\bmove (the )?(shop|store|outlet|site)\b", r"which (location|area|site|spot) is best", r"konsi jagah"]),
    ("optimize", [r"\b(best|optimal|ideal|optimum|right) (strategy|price|plan|pricing|combination|marketing)", r"\boptimi[sz]", r"maximi[sz]e (my )?profit", r"most profit", r"sabse (zyada|jyada) (profit|munafa)",
                  r"what (price|strategy) (should|maximi)"]),
    ("explain_term", [r"\bwhat (is|are|does) (a |an |the )?(catchment|p10|p90|break.?even|awareness|capacity|wtp|willingness to pay|monte carlo|outside option|trial rate|repeat share|payback|utili[sz]ation|scenario|baseline|genome|agent|turned away|reference price|variable cost|fixed cost|operating profit)",
                      r"\b(catchment|p10|p90|break.?even|monte carlo|wtp|payback|utili[sz]ation|genome|awareness|capacity) (ka |ki |ke )?(kya|matlab|means?|meaning)", r"\bmeaning of\b", r"\bexplain (the )?(term|word)"]),
    ("tour", [r"\b(tour|guide me|walk me through|show me around|how (do i|to) use|where do i start|what do i do( first| now| next)?|next step|samjhao|kaise use|kya karu ab|aage kya)\b"]),
    ("insights", [r"insight", r"suggest", r"advice", r"advise", r"improve", r"\bgrow", r"badh", r"sujhav", r"what should i change", r"how (can|do) i (get|increase|make|win)",
                  r"what('s| is) wrong", r"problem", r"why (so )?(low|less|few)", r"kam kyu", r"analy[sz]"]),
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


_NUM = r"(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|hazaar|hazar|lakh|l)?\b"


def _val(m) -> float:
    v = float(m.group(1).replace(",", ""))
    u = (m.group(2) or "").lower()
    return v * (1e5 if u in ("lakh", "l") else 1e3 if u else 1)


def parse_strategy(q: str, cur: dict, cap_now: float | None) -> dict:
    """Turn 'double the marketing and open till 11' into input changes. Only what the user said is changed."""
    ql = q.lower()
    ch: dict = {}
    m = re.search(r"(?:marketing|ads?|advertis\w*|promotion)\D{0,25}" + _NUM, ql) or re.search(_NUM + r"\D{0,12}(?:on |for |in )?(?:marketing|ads?|advertis)", ql)
    if m:
        ch["marketing_spend"] = _val(m)
    elif re.search(r"(double|2x|twice|dugna|dogun\w*).{0,20}(marketing|ads?)|(marketing|ads?).{0,20}(double|2x|twice|dugna)", ql):
        ch["marketing_spend"] = max(2 * float(cur.get("marketing_spend") or 0), 20000)
    elif re.search(r"(increase|more|badha\w*|raise).{0,20}(marketing|ads?)", ql):
        ch["marketing_spend"] = max(1.5 * float(cur.get("marketing_spend") or 0), float(cur.get("marketing_spend") or 0) + 15000)
    m = re.search(r"capacity\D{0,20}" + _NUM, ql) or re.search(_NUM + r"\s*(?:orders?|covers?|seats?|members?)\s*(?:a|per)\s*day", ql)
    if m and cap_now:
        ch["capacity_scale"] = round(max(0.2, min(10.0, _val(m) / cap_now)), 2)
    elif re.search(r"(double|2x|twice|dugna).{0,20}(capacity|kitchen|staff)|(capacity|kitchen|staff).{0,20}(double|2x|twice)", ql):
        ch["capacity_scale"] = 2.0
    elif re.search(r"(\d{2,3})\s*%\s*more.{0,12}(capacity|kitchen|staff)", ql):
        ch["capacity_scale"] = 1 + float(re.search(r"(\d{2,3})\s*%", ql).group(1)) / 100
    elif re.search(r"(increase|more|badha\w*|add|raise).{0,20}(capacity|kitchen|staff)", ql):
        ch["capacity_scale"] = 1.5
    m = re.search(r"quality\D{0,15}(\d{1,3})", ql)
    if m:
        qv = float(m.group(1))
        ch["quality"] = min(1.0, qv / 100 if qv > 1 else qv)
    elif re.search(r"(better|improve|increase|raise|badha\w*).{0,15}quality", ql):
        ch["quality"] = min(1.0, float(cur.get("quality") or 0.55) + 0.12)
    m = re.search(r"open\D{0,10}(\d{1,2})\s*(am|pm)?\D{1,12}(\d{1,2})\s*(am|pm)?", ql)
    if m:
        o, c = float(m.group(1)), float(m.group(3))
        o += 12 if m.group(2) == "pm" and o < 12 else 0
        c += 12 if (m.group(4) == "pm" or (not m.group(4) and c < o)) and c < 12 else 0
        ch["open_hour"], ch["close_hour"] = o, min(24.0, c)
    else:
        m = re.search(r"(?:close|till|until|tak)\D{0,8}(\d{1,2})\s*(am|pm)?", ql)
        if m and re.search(r"close|till|until|tak|hours|open", ql):
            c = float(m.group(1))
            c += 12 if (m.group(2) == "pm" or not m.group(2)) and c < 12 else 0
            ch["close_hour"] = min(24.0, c)
    m = re.search(r"(?:price|fee|charge|rate)\D{0,12}(?:₹|rs\.?|inr)?\s*(\d[\d,]*)", ql)
    if m:
        ch["price"] = float(m.group(1).replace(",", ""))
    return ch


def describe_screen(sc: dict | None, unit: str) -> str:
    if not sc or not sc.get("page"):
        return ""
    pg = sc.get("page")
    if pg == "live":
        s = f"You're on the live market, day {sc.get('day')}, week {sc.get('week')}, scenario {sc.get('scenario')}. "
        if sc.get("orders_today") is not None:
            s += f"Today the simulation shows {num(sc['orders_today'])} {unit} for you"
            if sc.get("capacity_per_day"):
                s += f" against a limit of {num(sc['capacity_per_day'])} a day"
            s += f", {num(sc.get('customers_so_far'))} customers so far, {pct(sc.get('aware'))} of the market aware of you, and competitors sold {num(sc.get('competitor_sales_today'))}. "
        if sc.get("compare"):
            c = sc["compare"]
            s += f"You're comparing against {c.get('name')}: month 3 is {num(c.get('after_month3'))} versus {num(c.get('before_month3'))} {unit}. "
        if sc.get("selected_agent") is not None:
            s += f"Agent {sc['selected_agent']} is open in the X-ray. "
        return s
    if pg == "market":
        s = f"You're on the market map with {num(sc.get('competitors'))} competitors and about {num(sc.get('population'))} people in the catchment. "
        if sc.get("selected_competitor"):
            s += f"You've selected {sc['selected_competitor']}. "
        return s
    return f"You're on the {pg} page. "


def explain_agents(f: dict, view: dict | None, unit: str) -> str:
    s = ("Each of the ten thousand agents is a synthetic person placed where WorldPop says people live, with 615 personal parameters: "
         "age, income, how far and how they travel, which hours they're free, 40 things they care about and the minimum they expect on each, "
         "how they react to 16 media channels, and how price-sensitive they are. "
         "Every day, an agent first has to be in the market and aware of you, through ads, word of mouth or your signboard. "
         "Then it scores every option it can reach — you, each competitor, or buying nothing — on price against its own budget, travel time, "
         "opening hours, quality and its own tastes, adds a little personal randomness, and picks the highest score. "
         "Habits build when it returns, and a bad experience like being turned away is remembered. ")
    if view:
        s += (f"In this run, {pct(view.get('afford_share'))} of in-market people can afford your price, {pct(view.get('awareness_week12'))} knew you by week 12, "
              f"and {pct(view.get('repeat_share'))} of customers came back. ")
    s += ("Daily orders are the sum of every agent's probability of choosing you times the residents it stands for, "
          "so one agent never jumps the total by hundreds.")
    return s


GLOSSARY = {
    "catchment": "The catchment is the area your customers realistically come from — by default a circle of a few kilometres around your site, or a travel-time area. Everyone outside it is ignored.",
    "p10": "P10 is the bad-but-realistic case: in 10% of the uncertainty runs profit was this low or lower. P90 is the good case. The truth is likely between them.",
    "p90": "P90 is the good case: only 10% of the uncertainty runs did better. P10 is the bad case. Plan for P10, hope for P90.",
    "break": "Break-even is how many sales a month you need so revenue exactly covers all monthly costs. Below it you lose money every month.",
    "awareness": "Awareness is the share of people who need what you sell and have heard that you exist. Nobody can choose you before they know you; ads, word of mouth and your signboard raise it.",
    "capacity": "Capacity is the most you can serve — orders a day, seats, members or slots. Demand above capacity is turned away and some of those people go to rivals.",
    "wtp": "Willingness to pay is the highest price a person would accept. Each agent has its own, based on income and how much it values the category.",
    "willingness": "Willingness to pay is the highest price a person would accept. Each agent has its own, based on income and how much it values the category.",
    "monte": "Monte Carlo means running the model hundreds of times with the uncertain assumptions drawn from their realistic ranges, so you see a range of outcomes and the chance of a loss, not one number.",
    "outside": "The outside option is 'buy nothing' or 'buy somewhere we don't model'. Every agent compares you and your rivals with it, so demand isn't forced onto anyone.",
    "trial": "Trial rate is the share of people who knew about you and bought at least once.",
    "repeat": "Repeat share is the share of your customers who bought two or more times — the sign of a loyal base.",
    "payback": "Payback is how many months of profit it takes to earn back your startup investment.",
    "utili": "Utilisation is how full you are: sales divided by capacity. Near 100% means you're turning people away.",
    "scenario": "A scenario is one version of your plan — a price, costs, capacity and marketing. You can make several and compare them.",
    "baseline": "The baseline is your starting plan. Every other scenario is compared against it.",
    "genome": "The genome is the 615 numbers that describe one synthetic person: budget, travel, free hours, tastes, media habits, loyalty and more.",
    "agent": "An agent is one synthetic person in the simulation, placed where real people live. Each stands for a number of real residents. They are not real individuals.",
    "turned": "Turned away means people who wanted to buy from you on a day when you were already full.",
    "reference": "The reference price is the typical local price for this kind of business. Affordability is judged against it.",
    "variable": "Variable cost is what each sale costs you — ingredients, packaging, commissions. It grows with every sale.",
    "fixed": "Fixed costs are the monthly bills you pay even with zero sales — rent, salaries, utilities, marketing.",
    "operating": "Operating profit is revenue minus variable and fixed costs, before tax, loan interest and depreciation.",
}


def explain_term(q: str) -> str:
    ql = q.lower()
    for k, v in GLOSSARY.items():
        if k in ql:
            return v
    return "Ask me about any word on the screen — catchment, break-even, P10, awareness, capacity, payback — and I'll explain it simply."


GENERAL = ("StrataIQ lets you test a business before you invest. Pick any business and any place in India or the world. "
           "It loads real competitors from OpenStreetMap and real population from WorldPop, then simulates ten thousand synthetic customers "
           "choosing between you, your competitors, or nothing, and turns that into profit, risk and break-even. "
           "Start with 'Simulate your business', or open the live demo.")


@router.post("/assistant/ask")
async def ask_general(body: Ask):
    intent = detect(body.question)
    actions = []
    if intent == "start_idea":
        return {"answer": "Let me set that up — I'll find the place, load the real competitors and population, and run the simulation.",
                "intent": intent, "grounded": True, "actions": [{"type": "quickstart", "text": body.question}]}
    if intent == "explain_term":
        return {"answer": explain_term(body.question), "intent": intent, "actions": [], "grounded": True}
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
    sc = body.screen or {}
    arch = ARCHETYPES[p.category["archetype"]]
    unit = arch.unit_label
    from .insights import _run_strategy, _scenario_run, build_insights
    if intent == "explain_term":
        return {"answer": explain_term(q), "intent": intent, "actions": [], "grounded": True}
    if intent == "start_idea":
        return {"answer": "Starting a new analysis for that idea — I'll load the real market and run it.", "intent": intent, "grounded": True,
                "actions": [{"type": "quickstart", "text": q}]}
    if intent == "find_site":
        from .explore import _scenario, model_inputs
        from ..engine.explore import site_scan
        s_obj = _scenario(p, sc.get("scenario_id"))
        a_, z_, c_, b_, pr_, rad_, _l = model_inputs(db, p, s_obj)
        res = await run_in_threadpool(site_scan, a_, z_, c_, b_, pr_, rad_)
        cur, top = res["current"], res["top"]
        if not top:
            return {"answer": "I couldn't find other populated sites inside this catchment to compare.", "intent": intent, "actions": [], "grounded": True}
        t0 = top[0]
        if t0["profit"] <= cur["profit"]:
            ans = (f"Your current site is already the best in this catchment by the model: about {num(cur['demand'])} {unit} of demand a month. "
                   f"The nearest alternative gives {inr(t0['profit'])} versus your {inr(cur['profit'])}.")
        else:
            ans = (f"The best site I found is {t0['from_current_km']} kilometres from yours, with about {num(t0['people_within_1km'])} people within a kilometre "
                   f"and {t0['competitors_within_500m']} competitors within 500 metres. Same plan there: about {num(t0['units'])} {unit} and {inr(t0['profit'])} a month, "
                   f"versus {inr(cur['profit'])} at your site. Rent is assumed the same, so check local rents. I've marked the top sites on the market map.")
        return {"answer": ans, "intent": intent, "grounded": True, "actions": [{"type": "sites"}], "result": {"current": cur, "top": top}}
    if intent == "optimize":
        from .explore import best_changes
        changes, o = await best_changes(p.id, sc.get("scenario_id"))
        b, c = o["best"], o["current"]
        if not changes:
            return {"answer": f"Your current plan is already the most profitable combination I tested ({o['evaluated']} options): {inr(c['profit'])} a month.",
                    "intent": intent, "actions": [], "grounded": True}
        parts = []
        if "price" in changes:
            parts.append(f"price {inr(b['price'])}")
        if "marketing_spend" in changes:
            parts.append(f"marketing {inr(b['marketing_spend'])} a month")
        if "capacity_scale" in changes:
            parts.append(f"capacity up {round(100 * (b['capacity_scale'] - 1))} percent, with the extra staff and rent included")
        ans = (f"I tested {o['evaluated']} combinations. The most profitable: {', '.join(parts)}. That gives about {num(b['units'])} {unit} and "
               f"{inr(b['profit'])} a month versus {inr(c['profit'])} now")
        if b.get("risk") and c.get("risk"):
            ans += f", and the chance of a loss month goes from {pct(c['risk']['prob_loss'])} to {pct(b['risk']['prob_loss'])}"
        ans += ". Say 'test it' and I'll check it with the ten thousand agents on the map."
        return {"answer": ans, "intent": intent, "grounded": True, "actions": [{"type": "suggest", "action": {"label": "Best strategy", "changes": changes}}],
                "suggested": {"label": "Best strategy", "changes": changes}}
    if intent == "tour":
        from ..services.runs import latest_runs as _lr
        runs_ = _lr(db, p)
        page = (sc.get("page") or "")
        if not runs_:
            ans = "First step: open the Market map and let the live data load — real competitors and population. Then the baseline simulation runs automatically."
        elif page != "live":
            ans = ("Your baseline has run. Next, open the Live market to watch ten thousand people decide day by day. Then read my insights on the right, "
                   "test a strategy with the sliders, ask me for the best location or the best strategy, and finally check Decisions for the verdict and what to verify.")
        else:
            ans = ("You're on the live market. Press play to watch customers choose. On the right: change your strategy and run it on the map, "
                   "read my insights, or ask me 'best strategy' or 'best location'. When you're done, open Decisions for the verdict.")
        return {"answer": ans, "intent": intent, "actions": [], "grounded": True}
    if intent in ("apply_suggestion", "strategy", "insights", "screen", "explain_agents"):
        s_obj, r_obj = _scenario_run(db, p, sc.get("scenario_id"))
        ins = build_insights(r_obj.results, s_obj.inputs, unit, arch.price_label) if r_obj else None
        if intent in ("apply_suggestion", "strategy"):
            if intent == "strategy":
                cap_now = (ins or {}).get("view", {}).get("capacity_per_day")
                changes = parse_strategy(q, s_obj.inputs, cap_now)
            else:
                changes = ((body.suggested or {}).get("changes") or ((ins or {}).get("suggested") or {}).get("changes") or {})
                changes = {k: float(v) for k, v in changes.items() if k in ("price", "marketing_spend", "quality", "capacity_scale", "open_hour", "close_hour")}
            if not changes:
                return {"answer": ("Tell me what to change — for example 'double the marketing', 'capacity 200 a day', 'price 399', "
                                   "or 'open 8 am to 11 pm' — and I'll run it on the map."), "intent": intent, "actions": [], "grounded": True}
            out = await run_in_threadpool(_run_strategy, p.id, {**changes, "from_scenario_id": s_obj.id})
            return {"answer": f"I ran {out['scenario']['name'].replace('Strategy: ', '')} on the map. " + out["spoken"], "intent": intent, "grounded": True,
                    "actions": [{"type": "refresh"}, {"type": "strategy", "scenario_id": out["scenario"]["id"], "from_scenario_id": out["from"]["id"]},
                                {"type": "navigate", "to": "live"}], "result": out}
        if intent == "explain_agents":
            return {"answer": explain_agents({}, (ins or {}).get("view"), unit), "intent": intent, "actions": [], "grounded": True}
        lead = describe_screen(sc, unit) if intent == "screen" else ""
        if not ins:
            return {"answer": lead + "Run this scenario first and I'll read the results for you.", "intent": intent, "actions": [], "grounded": True}
        return {"answer": (lead + ins["spoken"]).strip(), "intent": intent, "grounded": True, "suggested": ins.get("suggested"),
                "actions": [{"type": "suggest", "action": ins["suggested"]}] if ins.get("suggested") else []}
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
