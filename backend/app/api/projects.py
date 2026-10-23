from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..categories.archetypes import ARCHETYPES
from ..config import get_settings
from ..db import get_db
from ..models import CandidateLocation, Competitor, MarketSnapshot, Project, Scenario, User, utcnow
from ..providers.http import ProviderError
from ..schemas import CompetitorIn, CompetitorPatch, LocationIn, LocationPatch, ProjectCreate, ProjectPatch
from ..security import current_user, owned_project
from ..services.runs import competitors_for, latest_runs, latest_snapshot, loading_snapshot, point_wkt, refresh_snapshot, start_refresh
from .serialize import competitor_out, location_out, project_out, scenario_out, snapshot_out

router = APIRouter(tags=["projects"])
log = logging.getLogger("strataiq.api")

LOCATION_LABELS = ["Location A", "Location B", "Location C", "Location D", "Location E"]


def _summary(db: Session, p: Project) -> dict | None:
    runs = latest_runs(db, p)
    base = next((s for s in p.scenarios if s.is_baseline), None)
    if not base or base.id not in runs:
        return None
    r = runs[base.id].results
    return {"scenario": base.name, "units_sold": r["summary"]["units_sold"], "unit_label": r["unit_label"],
            "operating_profit": r["finance"]["operating_profit"], "prob_loss": (r.get("monte_carlo") or {}).get("prob_loss"),
            "run_at": runs[base.id].finished_at.isoformat() if runs[base.id].finished_at else None}


def _data_kinds(db: Session, p: Project) -> dict:
    snaps = db.scalars(select(MarketSnapshot.id).where(MarketSnapshot.project_id == p.id)).first()
    user_comps = db.scalar(select(Competitor.id).where(Competitor.project_id == p.id, Competitor.source == "user").limit(1))
    return {"connected_sources": bool(snaps), "user_provided": True, "demo": p.is_demo, "synthetic_estimates": True,
            "user_competitors": bool(user_comps)}


@router.get("/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ps = db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.updated_at.desc()))
    out = []
    for p in ps:
        d = project_out(p, _summary(db, p))
        d["data_kinds"] = _data_kinds(db, p)
        out.append(d)
    return out


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Project(owner_id=user.id, name=body.name.strip(), objective=body.objective, decision_goal=body.decision_goal,
                category=body.category.model_dump(), profile=body.profile, status="created")
    db.add(p)
    db.flush()
    loc = CandidateLocation(project_id=p.id, label=body.location.label or "Location A", address=body.location.address,
                            lat=body.location.lat, lng=body.location.lng, geog=point_wkt(body.location.lat, body.location.lng),
                            catchment=body.location.catchment.model_dump(), manual_population=body.location.manual_population)
    if not loc.catchment.get("radius_km"):
        loc.catchment["radius_km"] = ARCHETYPES[p.category["archetype"]].default_catchment_km
    db.add(loc)
    db.flush()
    db.add(Scenario(project_id=p.id, location_id=loc.id, name="Baseline", is_baseline=True, inputs=body.baseline.model_dump()))
    db.commit()
    db.refresh(p)
    return project_out(p)


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    runs = latest_runs(db, p)
    d = project_out(p, _summary(db, p))
    d["scenarios"] = [scenario_out(s, runs.get(s.id)) for s in p.scenarios]
    d["archetype"] = ARCHETYPES[p.category["archetype"]].to_public()
    d["data_kinds"] = _data_kinds(db, p)
    d["snapshots"] = {l.id: (lambda s: {"id": s.id, "retrieved_at": s.retrieved_at.isoformat(), "status": s.status} if s else None)(latest_snapshot(db, l.id)) for l in p.locations}
    return d


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, body: ProjectPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    data = body.model_dump(exclude_unset=True)
    if "category" in data and data["category"] is not None:
        p.category = body.category.model_dump()
    for k in ("name", "decision_goal", "profile", "status"):
        if data.get(k) is not None:
            setattr(p, k, data[k])
    p.updated_at = utcnow()
    db.commit()
    return project_out(p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    db.delete(p)
    db.commit()
    return Response(status_code=204)


# ---------------- locations ----------------
@router.post("/projects/{project_id}/locations", status_code=201)
def add_location(project_id: str, body: LocationIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    if len(p.locations) >= 5:
        raise HTTPException(422, "A project can compare up to 5 candidate locations")
    used = {l.label for l in p.locations}
    label = body.label if body.label and body.label not in used else next(x for x in LOCATION_LABELS if x not in used)
    cat = body.catchment.model_dump()
    if not cat.get("radius_km"):
        cat["radius_km"] = ARCHETYPES[p.category["archetype"]].default_catchment_km
    loc = CandidateLocation(project_id=p.id, label=label, address=body.address, lat=body.lat, lng=body.lng,
                            geog=point_wkt(body.lat, body.lng), catchment=cat, manual_population=body.manual_population)
    db.add(loc)
    p.updated_at = utcnow()
    db.commit()
    return location_out(loc)


@router.patch("/projects/{project_id}/locations/{location_id}")
def patch_location(project_id: str, location_id: str, body: LocationPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    loc = db.get(CandidateLocation, location_id)
    if not loc or loc.project_id != p.id:
        raise HTTPException(404, "Location not found")
    data = body.model_dump(exclude_unset=True)
    if "label" in data and data["label"]:
        loc.label = data["label"]
    if body.catchment is not None:
        loc.catchment = body.catchment.model_dump()
        if not loc.catchment.get("radius_km"):
            loc.catchment["radius_km"] = ARCHETYPES[p.category["archetype"]].default_catchment_km
    if "manual_population" in data:
        loc.manual_population = data["manual_population"] or None
    db.commit()
    return location_out(loc)


@router.delete("/projects/{project_id}/locations/{location_id}", status_code=204)
def delete_location(project_id: str, location_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    loc = db.get(CandidateLocation, location_id)
    if not loc or loc.project_id != p.id:
        raise HTTPException(404, "Location not found")
    if len(p.locations) <= 1:
        raise HTTPException(422, "A project needs at least one location")
    if any(s.location_id == loc.id and s.is_baseline for s in p.scenarios):
        raise HTTPException(422, "The baseline scenario uses this location; move the baseline first")
    db.delete(loc)
    db.commit()
    return Response(status_code=204)


# ---------------- market evidence ----------------
@router.post("/projects/{project_id}/locations/{location_id}/refresh")
async def refresh_market(project_id: str, location_id: str, response: Response, wait: bool = Query(default=False),
                         user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Start loading live evidence. Returns 202 + a 'loading' snapshot to poll, or the finished snapshot with wait=true."""
    p = owned_project(project_id, user, db)
    loc = db.get(CandidateLocation, location_id)
    if not loc or loc.project_id != p.id:
        raise HTTPException(404, "Location not found")
    if wait or get_settings().serverless:
        try:
            snap = await refresh_snapshot(db, p, loc)
        except ProviderError as e:
            raise HTTPException(502, f"Market data could not be loaded: {e.message[:200]}") from e
        return snapshot_out(snap)
    snap = start_refresh(db, p, loc)
    response.status_code = 202
    return snapshot_out(snap)


@router.get("/projects/{project_id}/snapshots/{snapshot_id}")
def snapshot_status(project_id: str, snapshot_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    s = db.get(MarketSnapshot, snapshot_id)
    if s is None or s.project_id != p.id:
        raise HTTPException(404, "Snapshot not found")
    if s.status == "loading":
        loading_snapshot(db, s.location_id)  # marks stale jobs as failed
        db.refresh(s)
    return {"id": s.id, "status": s.status, "errors": s.errors, "location_id": s.location_id}


@router.get("/projects/{project_id}/market")
def market(project_id: str, location_id: str | None = Query(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    loc = next((l for l in p.locations if l.id == location_id), None) if location_id else (p.locations[0] if p.locations else None)
    if loc is None:
        raise HTTPException(404, "Location not found")
    snap = latest_snapshot(db, loc.id)
    radius = float((snap.population.get("radius_km") if snap else None) or loc.catchment.get("radius_km") or 3)
    comps = competitors_for(db, p, loc, radius) if snap else []
    inactive = list(db.scalars(select(Competitor).where(Competitor.project_id == p.id, Competitor.active.is_(False))))
    from ..engine.geo import haversine_km
    out_comps = []
    for c in comps + inactive:
        d = competitor_out(c)
        d["distance_km"] = round(float(haversine_km(loc.lat, loc.lng, c.lat, c.lng)), 3)
        out_comps.append(d)
    out_comps.sort(key=lambda x: x["distance_km"])
    loading = loading_snapshot(db, loc.id)
    return {"location": location_out(loc), "snapshot": snapshot_out(snap) if snap else None, "competitors": out_comps,
            "loading_snapshot_id": loading.id if loading else None,
            "locations": [location_out(l) for l in p.locations], "category": p.category}


@router.post("/projects/{project_id}/competitors", status_code=201)
def add_competitor(project_id: str, body: CompetitorIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    c = Competitor(project_id=p.id, source="user", source_ref=None, name=body.name.strip(), lat=body.lat, lng=body.lng,
                   geog=point_wkt(body.lat, body.lng), tags={}, price=body.price, price_status="user" if body.price else "unknown",
                   quality=body.quality, quality_status="user" if body.quality is not None else "unknown",
                   is_hypothetical=body.is_hypothetical, notes=body.notes, retrieved_at=utcnow())
    db.add(c)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, "Competitor already exists") from e
    return competitor_out(c)


@router.patch("/projects/{project_id}/competitors/{competitor_id}")
def patch_competitor(project_id: str, competitor_id: str, body: CompetitorPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    c = db.get(Competitor, competitor_id)
    if not c or c.project_id != p.id:
        raise HTTPException(404, "Competitor not found")
    if body.clear_price:
        c.price, c.price_status = None, "unknown"
    elif body.price is not None:
        c.price, c.price_status = (body.price or None), ("user" if body.price else "unknown")
    if body.clear_quality:
        c.quality, c.quality_status = None, "unknown"
    elif body.quality is not None:
        c.quality, c.quality_status = body.quality, "user"
    if body.active is not None:
        c.active = body.active
    if body.notes is not None:
        c.notes = body.notes
    db.commit()
    return competitor_out(c)


@router.delete("/projects/{project_id}/competitors/{competitor_id}", status_code=204)
def delete_competitor(project_id: str, competitor_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    c = db.get(Competitor, competitor_id)
    if not c or c.project_id != p.id:
        raise HTTPException(404, "Competitor not found")
    if c.source != "user":
        raise HTTPException(422, "Mapped competitors cannot be deleted; exclude them instead (set active=false)")
    db.delete(c)
    db.commit()
    return Response(status_code=204)


@router.get("/factors/registry")
def factor_registry():
    from ..factors.registry import DOMAINS, FACTORS, counts
    return {"domains": DOMAINS, "counts": counts(), "definitions": [f.as_dict() for f in FACTORS]}


@router.get("/projects/{project_id}/factors")
def project_factors(project_id: str, scenario_id: str | None = Query(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """All 615 factor definitions with values for this project's scenario (computed / user / assumed / simulated / pending / unavailable)."""
    from ..factors.compute import compute
    from ..models import ActualOutcome
    p = owned_project(project_id, user, db)
    scen = next((s for s in p.scenarios if s.id == scenario_id), None) or next((s for s in p.scenarios if s.is_baseline), None)
    if scen is None:
        raise HTTPException(404, "Scenario not found")
    loc = db.get(CandidateLocation, scen.location_id)
    snap = latest_snapshot(db, loc.id)
    radius = float((snap.population.get("radius_km") if snap else None) or loc.catchment.get("radius_km") or 3)
    comps = competitors_for(db, p, loc, radius) if snap else []
    inactive = list(db.scalars(select(Competitor).where(Competitor.project_id == p.id, Competitor.active.is_(False))))
    run = latest_runs(db, p).get(scen.id)
    n_act = len(list(db.scalars(select(ActualOutcome.id).where(ActualOutcome.project_id == p.id))))
    out = compute(p, ARCHETYPES[p.category["archetype"]], loc, snap, comps + inactive, scen.inputs, run.results if run else None, n_act)
    out["scenario"] = {"id": scen.id, "name": scen.name, "run_id": run.id if run else None}
    return out
