"""Snapshot persistence and simulation-run execution."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
from geoalchemy2.functions import ST_DWithin, ST_GeogFromText
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..categories.archetypes import get_archetype
from ..config import get_settings
from ..db import session_factory
from ..engine import model as em
from ..engine import genome as gm
from ..engine.abm import build_population, cache_get, cache_put, run_abm
from ..engine.economics import behaviour as eb
from ..engine.economics import income as ei
from ..engine.simulate import SimulationError, simulate
from ..models import CandidateLocation, Competitor, MarketSnapshot, Project, Scenario, SimulationRun, utcnow
from ..providers import routing as rt
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


def recover_stale_loading_snapshots(db: Session, max_age: timedelta = LOADING_STALE_AFTER) -> int:
    """Finds all orphaned snapshots stuck in 'loading' longer than max_age and marks them failed."""
    cutoff = datetime.now(timezone.utc) - max_age
    stale_rows = list(db.scalars(
        select(MarketSnapshot).where(
            MarketSnapshot.status == "loading",
            MarketSnapshot.retrieved_at < cutoff,
        )
    ))
    for row in stale_rows:
        row.status = "failed"
        row.errors = [{"source": "job", "message": "Loading was interrupted (server restart or timeout). Please refresh again."}]
        row.retrieved_at = datetime.now(timezone.utc)
    if stale_rows:
        db.commit()
        log.warning("Recovered %d stale loading market snapshot(s)", len(stale_rows))
    return len(stale_rows)


def start_refresh(db: Session, project: Project, loc: CandidateLocation) -> MarketSnapshot:
    """Create a 'loading' snapshot and fill it in the background (live providers can take a minute)."""
    recover_stale_loading_snapshots(db)
    existing = loading_snapshot(db, loc.id)
    if existing:
        return existing
    ms = _placeholder(project, loc)
    db.add(ms)
    db.commit()
    db.refresh(ms)
    task = asyncio.create_task(_refresh_job(ms.id), name=f"snapshot-refresh-{ms.id}")
    _background.add(task)
    task.add_done_callback(_background.discard)
    return ms



async def _refresh_job(snapshot_id: str, timeout_seconds: float = 180.0) -> None:
    with session_factory()() as db:
        ms = db.get(MarketSnapshot, snapshot_id)
        if ms is None:
            return
        project = db.get(Project, ms.project_id)
        loc = db.get(CandidateLocation, ms.location_id)
        if not project or not loc:
            log.error("snapshot job failed: project or location missing for snapshot %s", snapshot_id)
            ms.status = "failed"
            ms.errors = [{"source": "job", "message": "Associated project or location was deleted"}]
            ms.retrieved_at = datetime.now(timezone.utc)
            db.commit()
            return

        error_message: str | None = None
        try:
            await asyncio.wait_for(
                refresh_snapshot(db, project, loc, into=ms),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            log.warning("snapshot job timed out %s after %.1fs", snapshot_id, timeout_seconds)
            error_message = f"Market data fetch timed out after {int(timeout_seconds)}s."
        except asyncio.CancelledError:
            log.warning("snapshot job was cancelled %s", snapshot_id)
            error_message = "Snapshot refresh was cancelled."
        except Exception as e:  # never leave a job hanging in 'loading'
            log.exception("snapshot job failed %s", snapshot_id)
            error_message = (e.message if isinstance(e, ProviderError) else type(e).__name__)[:300]

        if error_message:
            try:
                db.rollback()
                ms = db.get(MarketSnapshot, snapshot_id)
                if ms:
                    ms.status = "failed"
                    ms.errors = [{"source": "job", "message": error_message}]
                    ms.retrieved_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception:
                log.exception("critical error recording failure for snapshot %s", snapshot_id)



async def refresh_snapshot(db: Session, project: Project, loc: CandidateLocation, into: MarketSnapshot | None = None) -> MarketSnapshot:
    snap = await build_snapshot(lat=loc.lat, lng=loc.lng, catchment=loc.catchment, category=project.category,
                                manual_population=loc.manual_population, cache=Cache(session_factory()))
    now = datetime.now(timezone.utc)
    comp_src = next((s for s in snap["sources"] if s.get("layer") == "competitors"), None)
    retrieved = datetime.fromisoformat(comp_src["retrieved_at"]) if comp_src else now
    existing = {c.source_ref: c for c in db.scalars(select(Competitor).where(Competitor.project_id == project.id, Competitor.source.in_(("osm", "foursquare"))))}
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
            db.add(Competitor(project_id=project.id, source="foursquare" if c["ref"].startswith("fsq/") else "osm", source_ref=c["ref"], name=name[:200], lat=c["lat"], lng=c["lng"],
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


EVIDENCE_VERSION = "real-data-1"  # bump when the evidence layer changes (part of the run's input hash)


class MarketInputs:
    """Everything the run needs from the snapshot's real-data layers, built identically for a run and its re-inspection."""

    def __init__(self, arch, category_key: str | None, snap: MarketSnapshot, seed: int, circuity: float, speed_kmh: float):
        keep = [i for i, z in enumerate(snap.zones) if z["population"] > 0]
        self.zones = [em.Zone(snap.zones[i]["lat"], snap.zones[i]["lng"], snap.zones[i]["population"], snap.zones[i].get("activity", 0)) for i in keep]
        self.zone_ll = np.array([[z.lat, z.lng] for z in self.zones]) if self.zones else np.zeros((0, 2))
        pop_meta = snap.population or {}
        adm = pop_meta.get("admin") or {}
        self.routing = pop_meta.get("routing")
        if self.routing:  # snapshot zones with zero population were dropped: keep the matching route rows
            self.routing = {k: v for k, v in self.routing.items()}
            for prof in ("car", "foot"):
                if self.routing.get(prof) and len(self.routing[prof]["km"]) == len(snap.zones):
                    self.routing[prof] = {m: [self.routing[prof][m][i] for i in keep] for m in ("km", "min")}
        self.circuity, self.speed = circuity, speed_kmh
        self.income = self.behaviour = None
        self.arch = arch
        india = adm.get("country_code") in ("IN", "", None)
        if self.zones and india:
            ctx = ei.build_context(self.zone_ll[:, 0], self.zone_ll[:, 1], state=adm.get("state"), sector=adm.get("settlement"))
            if ctx.method.startswith("rwi") or adm.get("country_code") == "IN":
                self.income = ctx
                self.behaviour = eb.build(arch, category_key, ctx, len(self.zones), age_sex=pop_meta.get("age_sex"), seed=seed)
                self.arch = eb.apply(arch, self.behaviour)

    def route_fn(self, points: list[tuple[float, float]]):
        if not self.routing or not len(self.zone_ll):
            return None, None, 0.0
        pts = [(rt.point_key(a, b), a, b) for a, b in points]
        km, _, share = rt.matrix_for(self.routing, self.routing["dest_keys"], pts, self.zone_ll, self.circuity, self.speed, "car")
        _, walk, _ = rt.matrix_for(self.routing, self.routing["dest_keys"], pts, self.zone_ll, self.circuity, 4.5, "foot")
        return (km if share > 0 else None), walk, share

    @property
    def evidence_params(self) -> dict:
        return self.behaviour.params if self.behaviour else {}

    @property
    def seg_share_z(self):
        return self.behaviour.zone_shares if self.behaviour else None


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
    base_params = em.ResolvedParams.from_archetype(arch, inputs.get("param_overrides") or {})
    mi = MarketInputs(arch, (project.category or {}).get("key"), snap, seed, base_params.values.get("circuity", 1.3),
                      base_params.values.get("urban_speed_kmh", 20.0))
    zones = mi.zones
    ecomps = [em.Competitor(c.id, c.name, c.lat, c.lng, price=c.price, quality=c.quality, source="user" if c.source == "user" else "osm") for c in comps]
    snapshot_inputs = {
        "scenario": inputs, "category": project.category, "location": {"lat": loc.lat, "lng": loc.lng, "catchment": loc.catchment},
        "snapshot_id": snap.id, "competitors": [{"id": c.id, "name": c.name, "price": c.price, "quality": c.quality, "lat": c.lat, "lng": c.lng} for c in comps],
        "reference_price_filled": ref_fill, "model_version": em.MODEL_VERSION,
        "profile": {k: (project.profile or {}).get(k) for k in ("positioning", "operating_hours")}, "month0": gm.month_now(), "radius_km": radius,
        "n_agents": get_settings().abm_agents, "evidence_version": EVIDENCE_VERSION,
    }
    run.inputs_snapshot = snapshot_inputs
    run.input_hash = _hash(snapshot_inputs)
    db.add(run)
    db.commit()
    log.info("simulation start run=%s scenario=%s model=%s zones=%d comps=%d", run.id, scenario.id, em.MODEL_VERSION, len(zones), len(ecomps))
    try:
        if not zones:
            raise SimulationError("Population data is unavailable for this catchment. Enter an approximate catchment population on the market page and reload.")
        arch = mi.arch  # segments from the real income mix when the income layer ran
        travel_km, _, route_share = mi.route_fn([(biz.lat, biz.lng)] + [(c.lat, c.lng) for c in ecomps])
        res = simulate(arch, zones, ecomps, biz, inputs.get("param_overrides") or {}, mc_draws=get_settings().mc_draws, seed=seed,
                       travel_km=travel_km, evidence=mi.evidence_params, seg_share_z=mi.seg_share_z)
        if ref_fill is not None:
            res["summary"]["reference_price_status"] = "assumption_baseline_price"
        # Agent-based "live market": synthetic people at real density, simulated day by day.
        params = em.ResolvedParams.from_archetype(arch, inputs.get("param_overrides") or {}, mi.evidence_params)
        abm = run_abm(arch, zones, ecomps, biz, params, float(res["summary"]["reference_price"]), n_agents=snapshot_inputs["n_agents"],
                      days=84, seed=seed, age_sex=snap.population.get("age_sex"), spacing_km=float(snap.population.get("spacing_km") or 0.35),
                      overrides=inputs.get("param_overrides") or {}, profile=snapshot_inputs["profile"], offer=inputs.get("offer"),
                      radius_km=radius, month0=snapshot_inputs["month0"], cache_key=run.id,
                      income=mi.income, behaviour=mi.behaviour, route_fn=mi.route_fn)
        res["income"] = mi.behaviour.summary if mi.behaviour else None
        res["routing"] = {"share_routed": round(route_share, 3), "source": "osrm" if route_share > 0 else "haversine_circuity",
                          "note": "Road-network distance (OSRM, OpenStreetMap roads) from every zone to the site and nearest competitors"
                          if route_share > 0 else "Routing unavailable for this snapshot: straight-line distance x circuity factor"}
        res["parameter_status"] = {k: params.status.get(k) for k in params.values}
        res["parameter_sources"] = {k: v[4] for k, v in mi.evidence_params.items()}
        vcu, fixed = float(res["summary"]["variable_cost_per_unit"] or 0), float(res["finance"]["fixed_cost"] or 0)
        cap = float(res["summary"]["capacity_units"] or 0)
        abm["monthly_finance"] = [{"month": i + 1, "units": u, "capped_units": min(u, cap) if cap else u,
                                   "revenue": round(min(u, cap) * biz.price, 2), "profit": round(min(u, cap) * (biz.price - vcu) - fixed, 2)}
                                  for i, u in enumerate(abm["monthly_units"])]
        res["abm"] = abm
        res["evidence"] = {
            "snapshot_id": snap.id, "retrieved_at": snap.retrieved_at.isoformat(), "catchment_method": snap.catchment_method,
            "population_method": snap.population.get("method"), "population_source": snap.population.get("source"),
            "coverage": snap.coverage, "n_competitors": len(ecomps),
            "n_user_competitors": sum(1 for c in comps if c.source == "user"),
            "n_hypothetical": sum(1 for c in comps if c.is_hypothetical),
            "failed_layers": sorted({e.get("source") for e in (snap.errors or []) if e.get("source")}),
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


def population_for_run(db: Session, run: SimulationRun):
    """Rebuild (or fetch from cache) the exact synthetic population of a finished run: same inputs + seed => same 615-parameter genomes."""
    pop = cache_get(run.id)
    abm = (run.results or {}).get("abm") or {}
    if pop is None:
        snap = db.get(MarketSnapshot, run.snapshot_id) if run.snapshot_id else None
        if snap is None or not abm:
            raise SimulationError("This run cannot be re-inspected (market snapshot missing).")
        ins = run.inputs_snapshot or {}
        sc = ins.get("scenario") or {}
        project = db.get(Project, run.project_id)
        arch = get_archetype((ins.get("category") or project.category)["archetype"])
        loc = ins.get("location") or {}
        biz = em.BusinessInputs(lat=loc["lat"], lng=loc["lng"], price=float(sc["price"]), quality=float(sc.get("quality", 0.55)),
                                marketing_spend=float(sc.get("marketing_spend", 0)), capacity=sc.get("capacity") or {})
        comps = [em.Competitor(c["id"], c.get("name") or "Competitor", c["lat"], c["lng"], price=c.get("price"), quality=c.get("quality"))
                 for c in ins.get("competitors", [])]
        base_params = em.ResolvedParams.from_archetype(arch, sc.get("param_overrides") or {})
        mi = None
        if ins.get("evidence_version"):
            mi = MarketInputs(arch, (ins.get("category") or project.category or {}).get("key"), snap, int(run.seed),
                              base_params.values.get("circuity", 1.3), base_params.values.get("urban_speed_kmh", 20.0))
            zones, arch = mi.zones, mi.arch
        else:  # runs made before the real-data layer: rebuild exactly as they were made
            zones = [em.Zone(z["lat"], z["lng"], z["population"], z.get("activity", 0)) for z in snap.zones if z["population"] > 0]
        params = em.ResolvedParams.from_archetype(arch, sc.get("param_overrides") or {}, mi.evidence_params if mi else None)
        pop = build_population(arch, zones, comps, biz, params, float(run.results["summary"]["reference_price"]), n_agents=int(abm["n_agents"]),
                               seed=int(run.seed), age_sex=snap.population.get("age_sex"), spacing_km=float(snap.population.get("spacing_km") or 0.35),
                               profile=ins.get("profile") or project.profile, offer=sc.get("offer"), overrides=sc.get("param_overrides") or {},
                               month0=int(ins.get("month0", gm.month_now())), days=int(abm.get("days", 84)),
                               income=mi.income if mi else None, behaviour=mi.behaviour if mi else None, route_fn=mi.route_fn if mi else None)
        cols = abm["agents"]["columns"]
        im = cols.index("in_market")
        pop.gen.G[:, gm.KI["ev_in_market"]] = [r[im] for r in abm["agents"]["rows"]]
        cache_put(run.id, pop)
    return pop, abm
