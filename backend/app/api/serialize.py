from __future__ import annotations

from ..engine.model import MODEL_VERSION
from ..models import CandidateLocation, Competitor, MarketSnapshot, Project, Scenario, SimulationRun


def iso(dt):
    return dt.isoformat() if dt else None


def location_out(l: CandidateLocation) -> dict:
    return {"id": l.id, "label": l.label, "address": l.address, "lat": l.lat, "lng": l.lng, "catchment": l.catchment,
            "manual_population": l.manual_population, "created_at": iso(l.created_at)}


def scenario_out(s: Scenario, run: SimulationRun | None = None) -> dict:
    d = {"id": s.id, "name": s.name, "is_baseline": s.is_baseline, "location_id": s.location_id, "inputs": s.inputs,
         "created_at": iso(s.created_at), "updated_at": iso(s.updated_at), "latest_run": None}
    if run is not None:
        stale = run.inputs_snapshot.get("scenario") != s.inputs or run.model_version != MODEL_VERSION
        d["latest_run"] = {"id": run.id, "status": run.status, "finished_at": iso(run.finished_at), "stale": stale,
                           "model_version": run.model_version}
    return d


def project_out(p: Project, summary: dict | None = None) -> dict:
    return {"id": p.id, "name": p.name, "objective": p.objective, "decision_goal": p.decision_goal, "category": p.category,
            "profile": p.profile, "status": p.status, "is_demo": p.is_demo, "created_at": iso(p.created_at),
            "updated_at": iso(p.updated_at), "locations": [location_out(l) for l in p.locations],
            "summary": summary}


def competitor_out(c: Competitor, target_category_key: str | None = None) -> dict:
    tags = c.tags or {}
    public_attrs = {k: tags[k] for k in ("opening_hours", "website", "phone", "brand", "cuisine", "sport", "addr:street",
                                         "addr:city", "addr:postcode", "level", "operator", "check_date", "wheelchair") if k in tags}
    category_tag = next((f"{k}={tags[k]}" for k in ("amenity", "shop", "leisure", "tourism", "healthcare", "craft", "office") if k in tags), None)
    from ..categories.competitors import classify_competitor
    cl = classify_competitor(target_category_key, tags, c.name) if target_category_key else None
    return {
        "id": c.id, "source": c.source, "source_ref": c.source_ref, "name": c.name, "lat": c.lat, "lng": c.lng,
        "category_tag": category_tag, "public_attributes": public_attrs,
        "relationship_tier": cl.tier if cl else "direct",
        "relationship_reason": cl.reason if cl else "Active competitor",
        "is_direct_competitor": cl.is_direct_or_partial if cl else True,
        "price": c.price, "price_status": c.price_status if c.price else "unknown",
        "quality": c.quality, "quality_status": c.quality_status if c.quality is not None else "unknown",
        "is_hypothetical": c.is_hypothetical, "active": c.active, "notes": c.notes,
        "source_updated_at": iso(c.source_updated_at), "retrieved_at": iso(c.retrieved_at), "created_at": iso(c.created_at),
        "osm_url": f"https://www.openstreetmap.org/{c.source_ref}" if c.source == "osm" and c.source_ref else None,
    }


def snapshot_out(s: MarketSnapshot) -> dict:
    return {"id": s.id, "location_id": s.location_id, "retrieved_at": iso(s.retrieved_at), "status": s.status,
            "catchment_geojson": s.catchment_geojson, "catchment_method": s.catchment_method, "zones": s.zones,
            "population": s.population, "sources": s.sources, "coverage": s.coverage, "activity_points": s.activity_points,
            "errors": s.errors}


def run_out(r: SimulationRun, include_results: bool = True) -> dict:
    d = {"id": r.id, "scenario_id": r.scenario_id, "snapshot_id": r.snapshot_id, "status": r.status, "model_version": r.model_version,
         "input_hash": r.input_hash, "seed": r.seed, "started_at": iso(r.started_at), "finished_at": iso(r.finished_at),
         "duration_ms": r.duration_ms, "error": r.error}
    if include_results:
        d["results"] = r.results
    return d
