"""Decision search endpoints: where to open (site scan) and which strategy to run (optimizer)."""
from __future__ import annotations

import copy

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..categories.archetypes import ARCHETYPES, get_archetype
from ..db import get_db, session_factory
from ..engine import model as em
from ..engine.explore import optimize, site_scan
from ..models import CandidateLocation, Project, Scenario, User, utcnow
from ..providers.http import ProviderError
from ..security import current_user, owned_project
from ..services.runs import competitors_for, execute_run, latest_runs, latest_snapshot, point_wkt, refresh_snapshot
from .insights import compare, run_view

router = APIRouter(tags=["explore"])
LOCATION_LABELS = [f"Location {c}" for c in "ABCDE"]


def _scenario(p: Project, scenario_id: str | None) -> Scenario:
    s = next((x for x in p.scenarios if x.id == scenario_id), None) if scenario_id else None
    s = s or next((x for x in p.scenarios if x.is_baseline), None)
    if s is None:
        raise HTTPException(409, "This project has no scenario")
    return s


def model_inputs(db: Session, p: Project, s: Scenario):
    """The same inputs ``execute_run`` uses, without running anything."""
    arch = get_archetype(p.category["archetype"])
    loc = db.get(CandidateLocation, s.location_id)
    snap = latest_snapshot(db, loc.id) if loc else None
    if loc is None or snap is None:
        raise HTTPException(409, "Load market data for this location first")
    inputs = dict(s.inputs)
    radius = float(snap.population.get("radius_km") or arch.default_catchment_km)
    comps = competitors_for(db, p, loc, radius)
    known = [c.price for c in comps if c.price]
    ref = inputs.get("reference_price") or (None if known else float(inputs["price"]))
    biz = em.BusinessInputs(
        lat=loc.lat, lng=loc.lng, price=float(inputs["price"]), quality=float(inputs.get("quality", 0.55)),
        marketing_spend=float(inputs.get("marketing_spend", 0)), reference_price=ref,
        variable_cost_per_unit=inputs.get("variable_cost_per_unit"), capacity=inputs.get("capacity") or {},
        rent=float(inputs.get("rent", 0)), payroll=float(inputs.get("payroll", 0)), utilities=float(inputs.get("utilities", 0)),
        other_fixed=float(inputs.get("other_fixed", 0)), startup_cost=float(inputs.get("startup_cost", 0)))
    zones = [em.Zone(z["lat"], z["lng"], z["population"], z.get("activity", 0)) for z in snap.zones if z["population"] > 0]
    if not zones:
        raise HTTPException(409, "Population data is unavailable for this catchment")
    ecomps = [em.Competitor(c.id, c.name, c.lat, c.lng, price=c.price, quality=c.quality, source="user" if c.source == "user" else "osm") for c in comps]
    params = em.ResolvedParams.from_archetype(arch, inputs.get("param_overrides") or {})
    return arch, zones, ecomps, biz, params, radius, loc


@router.get("/projects/{project_id}/sites")
def sites(project_id: str, scenario_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    s = _scenario(p, scenario_id)
    arch, zones, comps, biz, params, radius, loc = model_inputs(db, p, s)
    out = site_scan(arch, zones, comps, biz, params, radius)
    out["scenario"] = {"id": s.id, "name": s.name}
    out["location"] = {"id": loc.id, "label": loc.label}
    out["unit"] = arch.unit_label
    return out


@router.get("/projects/{project_id}/optimize")
def best_strategy(project_id: str, scenario_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    s = _scenario(p, scenario_id)
    arch, zones, comps, biz, params, radius, loc = model_inputs(db, p, s)
    out = optimize(arch, zones, comps, biz, params)
    out["scenario"] = {"id": s.id, "name": s.name}
    out["unit"] = arch.unit_label
    out["price_label"] = arch.price_label
    return out


class AdoptIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    from_scenario_id: str | None = None
    address: str | None = Field(default=None, max_length=300)


async def _adopt(project_id: str, body: dict) -> dict:
    with session_factory()() as db:
        p = db.get(Project, project_id)
        src = _scenario(p, body.get("from_scenario_id"))
        src_loc = db.get(CandidateLocation, src.location_id)
        if len(p.locations) >= 5:
            raise HTTPException(422, "A project can compare up to 5 locations. Delete one on the Market map first.")
        used = {l.label for l in p.locations}
        label = next(x for x in LOCATION_LABELS if x not in used)
        loc = CandidateLocation(project_id=p.id, label=label, address=body.get("address") or f"Suggested site near {src_loc.address or src_loc.label}",
                                lat=body["lat"], lng=body["lng"], geog=point_wkt(body["lat"], body["lng"]),
                                catchment=copy.deepcopy(src_loc.catchment), manual_population=None)
        db.add(loc)
        db.commit()
        try:
            await refresh_snapshot(db, p, loc)
        except ProviderError as e:
            raise HTTPException(502, f"Market data could not be loaded for the new site: {e.message[:160]}") from e
        runs = latest_runs(db, p)
        r0 = runs.get(src.id) or execute_run(db, p, src)
        s = Scenario(project_id=p.id, location_id=loc.id, name=f"{src.name} at {label}"[:120], is_baseline=False, inputs=copy.deepcopy(src.inputs))
        db.add(s)
        p.updated_at = utcnow()
        db.commit()
        run = execute_run(db, p, s)
        if run.status != "succeeded":
            raise HTTPException(422, run.error or "Simulation failed")
        unit = ARCHETYPES[p.category["archetype"]].unit_label
        before, after = run_view(r0.results), run_view(run.results)
        return {"location": {"id": loc.id, "label": label, "lat": loc.lat, "lng": loc.lng}, "scenario": {"id": s.id, "name": s.name},
                "from": {"id": src.id, "name": src.name, "run_id": r0.id}, "run_id": run.id, "before": before, "after": after,
                "comparison": compare(before, after, unit)}


@router.post("/projects/{project_id}/sites/adopt")
async def adopt_site(project_id: str, body: AdoptIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Open a suggested site as a new location: load its own live data, run the same strategy there, compare."""
    p = owned_project(project_id, user, db)
    return await _adopt(p.id, body.model_dump())


def _optimize_sync(project_id: str, scenario_id: str | None) -> dict:
    with session_factory()() as db:
        p = db.get(Project, project_id)
        s = _scenario(p, scenario_id)
        arch, zones, comps, biz, params, radius, loc = model_inputs(db, p, s)
        return optimize(arch, zones, comps, biz, params)


async def best_changes(project_id: str, scenario_id: str | None) -> tuple[dict, dict]:
    """The optimizer's best combination as strategy changes (for voice / one-click apply)."""
    o = await run_in_threadpool(_optimize_sync, project_id, scenario_id)
    b, c = o["best"], o["current"]
    ch = {}
    if b["price"] != c["price"]:
        ch["price"] = b["price"]
    if b["marketing_spend"] != c["marketing_spend"]:
        ch["marketing_spend"] = b["marketing_spend"]
    if b["capacity_scale"] != 1.0:
        ch["capacity_scale"] = b["capacity_scale"]
    return ch, o
