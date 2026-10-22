"""Snapshot persistence and simulation-run execution."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from geoalchemy2.functions import ST_DWithin, ST_GeogFromText
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..categories.archetypes import get_archetype
from ..config import get_settings
from ..db import session_factory
from ..engine import model as em
from ..engine.simulate import SimulationError, simulate
from ..models import CandidateLocation, Competitor, MarketSnapshot, Project, Scenario, SimulationRun, utcnow
from ..providers.http import Cache, ProviderError
from .market import build_snapshot

log = logging.getLogger("strataiq.runs")


def point_wkt(lat: float, lng: float) -> str:
    return f"SRID=4326;POINT({lng:.7f} {lat:.7f})"


LOADING_STALE_AFTER = timedelta(minutes=5)
_background: set[asyncio.Task] = set()


def latest_snapshot(db: Session, location_id: str) -> MarketSnapshot | None:
    """Latest *usable* snapshot (complete, partial or failed — never one still loading)."""
    return db.scalars(select(MarketSnapshot).where(MarketSnapshot.location_id == location_id, MarketSnapshot.status != "loading")
                      .order_by(MarketSnapshot.retrieved_at.desc()).limit(1)).first()


def loading_snapshot(db: Session, location_id: str) -> MarketSnapshot | None:
    row = db.scalars(select(MarketSnapshot).where(MarketSnapshot.location_id == location_id, MarketSnapshot.status == "loading")
                     .order_by(MarketSnapshot.retrieved_at.desc()).limit(1)).first()
    if row and datetime.now(timezone.utc) - row.retrieved_at > LOADING_STALE_AFTER:
        row.status = "failed"
        row.errors = [{"source": "job", "message": "Loading was interrupted (server restart or timeout). Please refresh again."}]
        db.commit()
        return None
    return row


def _placeholder(project: Project, loc: CandidateLocation) -> MarketSnapshot:
    return MarketSnapshot(project_id=project.id, location_id=loc.id, status="loading", catchment_geojson={}, catchment_method=loc.catchment.get("mode", "radius"),
                          zones=[], population={"method": "unavailable", "source": None, "total": None},
                          sources=[], coverage={"level": "unknown", "note": "Loading…", "signals": [], "method": ""}, activity_points=[], errors=[])


def start_refresh(db: Session, project: Project, loc: CandidateLocation) -> MarketSnapshot:
    """Create a 'loading' snapshot and fill it in the background (live providers can take a minute)."""
    existing = loading_snapshot(db, loc.id)
    if existing:
        return existing
    ms = _placeholder(project, loc)
    db.add(ms)
    db.commit()
    db.refresh(ms)
    task = asyncio.create_task(_refresh_job(ms.id))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return ms


async def _refresh_job(snapshot_id: str) -> None:
    with session_factory()() as db:
        ms = db.get(MarketSnapshot, snapshot_id)
        if ms is None:
            return
        project, loc = db.get(Project, ms.project_id), db.get(CandidateLocation, ms.location_id)
        try:
            await refresh_snapshot(db, project, loc, into=ms)
        except Exception as e:  # never leave a job hanging in 'loading'
            log.exception("snapshot job failed %s", snapshot_id)
            db.rollback()
            ms = db.get(MarketSnapshot, snapshot_id)
            ms.status = "failed"
            ms.errors = [{"source": "job", "message": (e.message if isinstance(e, ProviderError) else type(e).__name__)[:300]}]
            ms.retrieved_at = datetime.now(timezone.utc)
            db.commit()


async def refresh_snapshot(db: Session, project: Project, loc: CandidateLocation, into: MarketSnapshot | None = None) -> MarketSnapshot:
    snap = await build_snapshot(lat=loc.lat, lng=loc.lng, catchment=loc.catchment, category=project.category,
                                manual_population=loc.manual_population, cache=Cache(session_factory()))
    now = datetime.now(timezone.utc)
    comp_src = next((s for s in snap["sources"] if s.get("layer") == "competitors"), None)
    retrieved = datetime.fromisoformat(comp_src["retrieved_at"]) if comp_src else now
    existing = {c.source_ref: c for c in db.scalars(select(Competitor).where(Competitor.project_id == project.id, Competitor.source == "osm"))}
    for c in snap["competitors"]:
        row = existing.get(c["ref"])
        updated = None
        if c.get("source_updated_at"):
            try:
                updated = datetime.fromisoformat(c["source_updated_at"].replace("Z", "+00:00"))
            except ValueError:
                updated = None
        name = c["name"] or f"Unnamed {project.category.get('label', 'business').lower()}"
        if row is None:
            db.add(Competitor(project_id=project.id, source="osm", source_ref=c["ref"], name=name[:200], lat=c["lat"], lng=c["lng"],
                              geog=point_wkt(c["lat"], c["lng"]), tags=c["tags"], source_updated_at=updated, retrieved_at=retrieved))
        else:  # refresh observed fields, keep user-entered price/quality/active
            row.name, row.lat, row.lng, row.tags = name[:200], c["lat"], c["lng"], c["tags"]
            row.geog = point_wkt(c["lat"], c["lng"])
            row.source_updated_at, row.retrieved_at = updated, retrieved
    ms = into or MarketSnapshot(project_id=project.id, location_id=loc.id)
    ms.status, ms.catchment_geojson, ms.catchment_method = snap["status"], snap["catchment_geojson"], snap["catchment_method"]
    ms.zones, ms.population = snap["zones"], snap["population"] | {"radius_km": snap["radius_km"]}
    ms.sources, ms.coverage, ms.activity_points, ms.errors = snap["sources"], snap["coverage"], snap["activity_points"], snap["errors"]
    ms.retrieved_at = now
    if into is None:
        db.add(ms)
    db.commit()
    db.refresh(ms)
    return ms


def competitors_for(db: Session, project: Project, loc: CandidateLocation, radius_km: float) -> list[Competitor]:
    reach_m = (radius_km + 1.0) * 1000
    q = select(Competitor).where(
        Competitor.project_id == project.id, Competitor.active.is_(True),
        ST_DWithin(Competitor.geog, ST_GeogFromText(point_wkt(loc.lat, loc.lng)), reach_m),
    ).order_by(Competitor.created_at)
    return list(db.scalars(q))


def _hash(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def baseline_price(project: Project) -> float | None:
    base = next((s for s in project.scenarios if s.is_baseline), None)
    return float(base.inputs["price"]) if base else None


def execute_run(db: Session, project: Project, scenario: Scenario) -> SimulationRun:
    loc = db.get(CandidateLocation, scenario.location_id)
    snap = latest_snapshot(db, loc.id) if loc else None
    arch = get_archetype(project.category["archetype"])
    inputs = dict(scenario.inputs)
    seed = int(inputs.get("seed", 42))
    run = SimulationRun(project_id=project.id, scenario_id=scenario.id, snapshot_id=snap.id if snap else None, status="running",
                        model_version=em.MODEL_VERSION, input_hash="", inputs_snapshot={}, seed=seed)
    if loc is None or snap is None:
        run.status, run.error, run.finished_at = "failed", "No market snapshot for this location yet. Load market data first.", utcnow()
        run.input_hash = _hash({"scenario": inputs})
        db.add(run)
        db.commit()
        return run
    radius = float(snap.population.get("radius_km") or arch.default_catchment_km)
    comps = competitors_for(db, project, loc, radius)
    known_prices = [c.price for c in comps if c.price]
    ref_fill = None
    if not inputs.get("reference_price") and not known_prices:
        ref_fill = baseline_price(project) or float(inputs["price"])
    biz = em.BusinessInputs(
        lat=loc.lat, lng=loc.lng, price=float(inputs["price"]), quality=float(inputs.get("quality", 0.55)),
        marketing_spend=float(inputs.get("marketing_spend", 0)), reference_price=inputs.get("reference_price") or ref_fill,
        variable_cost_per_unit=inputs.get("variable_cost_per_unit"), capacity=inputs.get("capacity") or {},
        rent=float(inputs.get("rent", 0)), payroll=float(inputs.get("payroll", 0)), utilities=float(inputs.get("utilities", 0)),
        other_fixed=float(inputs.get("other_fixed", 0)), startup_cost=float(inputs.get("startup_cost", 0)),
    )
    zones = [em.Zone(z["lat"], z["lng"], z["population"], z.get("activity", 0)) for z in snap.zones if z["population"] > 0]
    ecomps = [em.Competitor(c.id, c.name, c.lat, c.lng, price=c.price, quality=c.quality, source="user" if c.source == "user" else "osm") for c in comps]
    snapshot_inputs = {
        "scenario": inputs, "category": project.category, "location": {"lat": loc.lat, "lng": loc.lng, "catchment": loc.catchment},
        "snapshot_id": snap.id, "competitors": [{"id": c.id, "price": c.price, "quality": c.quality, "lat": c.lat, "lng": c.lng} for c in comps],
        "reference_price_filled": ref_fill, "model_version": em.MODEL_VERSION,
    }
    run.inputs_snapshot = snapshot_inputs
    run.input_hash = _hash(snapshot_inputs)
    db.add(run)
    db.commit()
    log.info("simulation start run=%s scenario=%s model=%s zones=%d comps=%d", run.id, scenario.id, em.MODEL_VERSION, len(zones), len(ecomps))
    try:
        if not zones:
            raise SimulationError("Population data is unavailable for this catchment. Enter an approximate catchment population on the market page and reload.")
        res = simulate(arch, zones, ecomps, biz, inputs.get("param_overrides") or {}, mc_draws=get_settings().mc_draws, seed=seed)
        if ref_fill is not None:
            res["summary"]["reference_price_status"] = "assumption_baseline_price"
        res["evidence"] = {
            "snapshot_id": snap.id, "retrieved_at": snap.retrieved_at.isoformat(), "catchment_method": snap.catchment_method,
            "population_method": snap.population.get("method"), "population_source": snap.population.get("source"),
            "coverage": snap.coverage, "n_competitors": len(ecomps),
            "n_user_competitors": sum(1 for c in comps if c.source == "user"),
            "n_hypothetical": sum(1 for c in comps if c.is_hypothetical),
        }
        run.results, run.status = res, "succeeded"
        run.duration_ms = res.get("duration_ms")
    except SimulationError as e:
        run.status, run.error = "failed", str(e)
    except Exception as e:  # unexpected: record and surface, never return fake results
        log.exception("simulation crashed run=%s", run.id)
        run.status, run.error = "failed", f"Internal error: {type(e).__name__}"
    run.finished_at = utcnow()
    db.commit()
    log.info("simulation end run=%s status=%s duration_ms=%s", run.id, run.status, run.duration_ms)
    return run


def latest_runs(db: Session, project: Project) -> dict[str, SimulationRun]:
    out: dict[str, SimulationRun] = {}
    rows = db.scalars(select(SimulationRun).where(SimulationRun.project_id == project.id, SimulationRun.status == "succeeded")
                      .order_by(SimulationRun.started_at.desc()))
    for r in rows:
        out.setdefault(r.scenario_id, r)
    return out
