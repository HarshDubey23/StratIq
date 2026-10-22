"""Agent Genome endpoints: registry, single-agent X-ray, population DNA matrix, and a field survey kit.

Everything here is derived from a finished simulation run. Populations are rebuilt
deterministically from the run's stored inputs and seed when not cached.
"""
from __future__ import annotations

import base64

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from ..db import get_db, session_factory
from ..engine import genome as gm
from ..engine.simulate import SimulationError
from ..models import Project, SimulationRun, User
from ..security import current_user, owned_project
from ..services.runs import population_for_run

router = APIRouter(tags=["genome"])

_PCT: dict[str, np.ndarray] = {}


@router.get("/genome/registry")
def genome_registry():
    """All 615 agent-genome parameters: block, unit, origin, mechanism, loadings and transform."""
    return {**gm.registry_public(), "audit": gm.audit()}


def _owned_run(run_id: str, user: User, db: Session) -> SimulationRun:
    run = db.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    owned_project(run.project_id, user, db)
    if run.status != "succeeded":
        raise HTTPException(409, run.error or f"Run is {run.status}")
    if not (run.results or {}).get("abm", {}).get("genome"):
        raise HTTPException(409, "This run predates the Agent Genome. Run the scenario again to inspect agents.")
    return run


def _load(run_id: str):
    with session_factory()() as db:
        run = db.get(SimulationRun, run_id)
        try:
            pop, abm = population_for_run(db, run)
        except SimulationError as e:
            raise HTTPException(409, str(e)) from e
        pct = _PCT.get(run_id)
        if pct is None:
            pct = gm.percentiles(pop.gen.G)
            _PCT.clear()  # keep only the latest one in memory
            _PCT[run_id] = pct
        project = db.get(Project, run.project_id)
        return pop, abm, pct, dict(project.category or {}), run.results.get("summary", {})


def _final(abm: dict) -> np.ndarray:
    cols = abm["agents"]["columns"]
    ci = cols.index("last_choice")
    return np.array([r[ci] for r in abm["agents"]["rows"]], int)


@router.get("/simulation-runs/{run_id}/agents/{agent}")
async def agent_xray(run_id: str, agent: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Full 615-parameter genome of one synthetic agent and why it chose what it chose."""
    _owned_run(run_id, user, db)
    pop, abm, pct, _, _ = await run_in_threadpool(_load, run_id)
    if not 0 <= agent < pop.N:
        raise HTTPException(404, "No such agent")
    final = _final(abm)
    x = gm.explain(agent, pop.gen, pop.up, pop.names, int(final[agent]), pct)
    row = abm["agents"]["rows"][agent]
    x["summary"] = dict(zip(abm["agents"]["columns"], row))
    x["segment"] = abm["agents"]["segments"][row[abm["agents"]["columns"].index("segment")]]
    x["mode"] = abm["agents"]["modes"][row[abm["agents"]["columns"].index("mode")]]
    x["scale"] = abm["scale"]
    x["note"] = "Synthetic agent. Values are model assumptions conditioned on real local evidence, not data about a real person."
    return x


@router.get("/simulation-runs/{run_id}/genome-matrix")
async def genome_matrix(run_id: str, rows: int = Query(480, ge=60, le=1200), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Population DNA: a stratified sample of agents x 615 parameters (population percentiles, 0-100), sorted by outcome.

    Also returns the parameters that most separate your customers from competitors' customers (descriptive, under the model).
    """
    _owned_run(run_id, user, db)
    pop, abm, pct, _, _ = await run_in_threadpool(_load, run_id)
    final = _final(abm)
    cols = abm["agents"]["columns"]
    inm = np.array([r[cols.index("in_market")] for r in abm["agents"]["rows"]], bool)
    u_you = np.array([r[cols.index("u_you")] for r in abm["agents"]["rows"]], float)
    groups = [("you", inm & (final == 0)), ("competitor", inm & (final > 0)), ("none", inm & (final < 0)), ("not_in_market", ~inm)]
    rng = np.random.default_rng(7)
    quota = {"you": 0.3, "competitor": 0.3, "none": 0.25, "not_in_market": 0.15}
    picked, labels = [], []
    for g, m in groups:
        idx = np.where(m)[0]
        k = min(idx.size, max(1, int(rows * quota[g])) if idx.size else 0)
        if k:
            sel = rng.choice(idx, k, replace=False)
            sel = sel[np.argsort(-u_you[sel])]
            picked.extend(sel.tolist())
            labels.extend([g] * k)
    M = pct[np.array(picked, int)] if picked else np.zeros((0, gm.GENOME_SIZE), np.uint8)
    # separation: mean percentile of your customers minus competitors' customers, per parameter
    you, comp = groups[0][1], groups[1][1]
    sep = []
    if you.sum() >= 5 and comp.sum() >= 5:
        d = pct[you].mean(0) - pct[comp].mean(0)
        for k in np.argsort(-np.abs(d))[:16]:
            p = gm.REG[k]
            if p.key in ("ev_lat", "ev_lng", "ev_zone", "ev_in_market"):
                continue
            sep.append({"key": p.key, "label": p.label, "block": p.block, "delta_pct": round(float(d[k]), 1),
                        "you_pct": round(float(pct[you, k].mean()), 1), "competitor_pct": round(float(pct[comp, k].mean()), 1)})
    blocks, start = [], 0
    for b in gm.BLOCKS:
        n = sum(1 for p in gm.REG if p.block == b)
        blocks.append({"key": b, "label": gm.BLOCKS[b], "start": start, "size": n})
        start += n
    return {
        "rows": len(picked), "cols": gm.GENOME_SIZE, "encoding": "base64 uint8 row-major, population percentile 0-100",
        "data": base64.b64encode(np.ascontiguousarray(M).tobytes()).decode(), "agent_index": picked, "groups": labels,
        "group_counts": {g: int(m.sum()) for g, m in groups}, "blocks": blocks,
        "params": [{"key": p.key, "label": p.label, "block": p.block, "mechanism": p.mechanism, "origin": p.origin} for p in gm.REG],
        "separators": sep[:12], "n_agents": pop.N,
        "note": "Descriptive of the synthetic population under the model's assumptions; not measurements of real customers.",
    }


# ------------------------------------------------------------------ survey kit
_Q_ATTR = "How important is “{label}” when you choose a {cat}? (1 = not at all, 5 = essential)"


@router.get("/simulation-runs/{run_id}/survey-kit")
async def survey_kit(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A field questionnaire that measures the assumptions this result is most sensitive to, so real answers can replace them."""
    _owned_run(run_id, user, db)
    pop, abm, pct, category, summary = await run_in_threadpool(_load, run_id)
    cat = (category.get("label") or category.get("name") or "business").lower()
    ref = float(summary.get("reference_price") or 0)
    rel = gm.relevance(category.get("archetype") or "retail")
    attrs = sorted([(rel[i], gm.ATTRS[i]) for i in range(len(gm.ATTRS))], key=lambda x: -x[0])[:6]
    drivers = (abm.get("top_drivers_against_you") or [])[:4]
    decomp = (abm.get("decomposition") or {}).get("chose_competitor") or {}
    weakest = sorted(((v["edge"], k) for k, v in (decomp.get("channels") or {}).items()), key=lambda x: x[0])[:2]
    qs = [
        {"id": "screen", "section": "Screening", "type": "single", "text": f"In the last 3 months, have you used a {cat}?",
         "options": ["Yes, currently", "Yes, but stopped", "No, but considering", "No, not interested"], "measures": ["participation"],
         "why": "Checks the share of residents in the market (participation), the single biggest demand assumption."},
        {"id": "too_cheap", "section": "Price (Van Westendorp)", "type": "money", "text": f"At what price would a {cat} be so cheap you'd doubt its quality?",
         "measures": ["ec_wtp_multiple", "ec_quality_price_inference"], "why": "Lower bound of the acceptable price range."},
        {"id": "bargain", "section": "Price (Van Westendorp)", "type": "money", "text": "At what price would it be a bargain?", "measures": ["ec_wtp_multiple"],
         "why": "Calibrates the willingness-to-pay distribution."},
        {"id": "expensive", "section": "Price (Van Westendorp)", "type": "money", "text": "At what price would it start to feel expensive, but you'd still consider it?",
         "measures": ["ec_wtp_multiple", "ec_sticker_shock"], "why": "Sticker-shock threshold."},
        {"id": "too_expensive", "section": "Price (Van Westendorp)", "type": "money", "text": "At what price is it too expensive to consider?",
         "measures": ["ec_wtp_multiple", "ec_spend_monthly_cat"], "why": "Upper bound / hard cap of spend."},
        {"id": "hours", "section": "Timing", "type": "multi", "text": "When would you most likely go? (pick all that apply)",
         "options": ["Before 7am", "7–10am", "10am–4pm", "4–7pm", "7–10pm", "After 10pm", "Weekends"],
         "measures": ["tm_wd_*", "tm_we_*", "tm_day_*"], "why": "Replaces the assumed hour-by-hour availability profile; your hours fit depends on it."},
        {"id": "travel", "section": "Travel", "type": "single", "text": f"How far would you travel to a {cat} you like?",
         "options": ["Under 5 min", "5–10 min", "10–20 min", "20–30 min", "Over 30 min"], "measures": ["mb_dist_tol", "mb_max_trip_min"],
         "why": "Distance tolerance drives the size of your real catchment."},
        {"id": "mode", "section": "Travel", "type": "single", "text": "How would you usually get there?",
         "options": ["Walk", "Two-wheeler", "Car", "Auto", "Bus", "Metro", "Cycle"], "measures": ["mb_access_*", "mb_pref_*"], "why": "Travel-mode mix."},
    ]
    for _, (k, lbl) in attrs:
        qs.append({"id": f"imp_{k}", "section": "What matters", "type": "scale5", "text": _Q_ATTR.format(label=lbl, cat=cat),
                   "measures": [f"im_{k}", f"ex_{k}"], "why": "Measures attribute importance; the model currently assumes it from latent traits."})
    qs += [
        {"id": "current", "section": "Competition", "type": "text", "text": f"Which {cat} do you use or have used nearby? What do you like and dislike?",
         "measures": ["competitor attributes"], "why": "Competitor quality and attributes are currently assumed (unknown in OpenStreetMap)."},
        {"id": "heard", "section": "Awareness", "type": "multi", "text": f"Where do you usually find out about a new {cat}?",
         "options": [lbl for _, lbl in gm.CHANNELS[:14]], "measures": ["ch_*"], "why": "Replaces the assumed media-channel exposure."},
        {"id": "new_trust", "section": "Awareness", "type": "single", "text": f"Would you try a newly opened {cat} without online reviews?",
         "options": ["Yes, happily", "Yes, with a free trial", "Only if friends recommend it", "Probably not"],
         "measures": ["bh_trial_bias", "so_social_proof_need", "so_review_reliance"], "why": "New businesses start with no reviews; this is often what decides trial."},
        {"id": "switch", "section": "Loyalty", "type": "single", "text": f"What would make you switch from your current {cat}?",
         "options": ["Lower price", "Closer location", "Better hours", "Better quality / equipment", "Friends going", "Nothing"],
         "measures": ["rt_switch_threshold", "bh_inertia"], "why": "Switching resistance decides how much share you can win from incumbents."},
    ]
    return {
        "title": f"Field survey — {category.get('label') or 'your business'}",
        "purpose": "Measure the assumptions this simulation is most sensitive to. Real answers replace modeled values; rerun to see the effect.",
        "sample_size": {"recommended": 100, "minimum": 40, "margin_of_error_at_100": "±10 percentage points (95%, simple random sample)",
                        "how": "Intercept people inside your catchment at different times of day; avoid only asking friends or one location."},
        "reference_price": ref or None,
        "focus": {"weakest_channels_vs_competitors": [k for _, k in weakest], "top_parameters_against_you": [d["label"] for d in drivers]},
        "questions": qs,
        "note": "Questions are generated from the model's sensitivities. This kit collects REAL feedback; synthetic agents are not a substitute for it.",
    }
