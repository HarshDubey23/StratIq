"""Demo scenario: a fully offline, clearly labelled illustrative market.

Used when judges need every feature to work even if live providers are slow.
All features in it are synthetic and flagged ``is_demo`` everywhere.
"""
from __future__ import annotations

import math

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..categories.resolver import from_taxonomy_key
from ..db import get_db
from ..engine.geo import circle_polygon, hex_grid
from ..models import CandidateLocation, Competitor, MarketSnapshot, Project, Scenario, User, utcnow
from ..security import current_user
from ..services.runs import point_wkt
from .serialize import project_out

router = APIRouter(tags=["demo"])

DEMO_LABEL = "DEMO SCENARIO — Illustrative market data; not verified live conditions."
CENTER = (12.9352, 77.6245)  # placeholder coordinates for the illustrative map only


@router.post("/demo", status_code=201)
def create_demo(user: User = Depends(current_user), db: Session = Depends(get_db)):
    cat = from_taxonomy_key("gym", "gym").as_dict()
    p = Project(owner_id=user.id, name="Demo — Neighbourhood gym", objective="start_new", decision_goal="profit", category=cat,
                profile={"description": "Illustrative demo project", "demo_label": DEMO_LABEL, "positioning": ["Premium experience", "Better service"], "operating_hours": "5:30am–10:30pm"}, status="created", is_demo=True)
    db.add(p)
    db.flush()
    lat, lng = CENTER
    loc = CandidateLocation(project_id=p.id, label="Location A", address="Demo area (illustrative)", lat=lat, lng=lng,
                            geog=point_wkt(lat, lng), catchment={"mode": "radius", "radius_km": 3.0, "minutes": None, "profile": "foot-walking"})
    db.add(loc)
    db.flush()
    rng = np.random.default_rng(2024)
    pts = hex_grid(lat, lng, 3.0, 0.35)
    # Illustrative density: two synthetic residential clusters.
    w = np.array([math.exp(-((a - lat - 0.008) ** 2 + (b - lng + 0.006) ** 2) / 0.00018) + 0.8 * math.exp(-((a - lat + 0.01) ** 2 + (b - lng - 0.01) ** 2) / 0.00025) + 0.15 for a, b in pts])
    total = 85000.0
    zones = [{"lat": round(a, 6), "lng": round(b, 6), "population": round(float(total * w[i] / w.sum()), 2), "buildings": 0, "activity": int(rng.random() < 0.08)} for i, (a, b) in enumerate(pts)]
    demo_comps = [("Demo Gym A (illustrative)", 0.011, 0.004, None), ("Demo Gym B (illustrative)", -0.006, 0.013, None),
                  ("Demo Fitness C (illustrative)", -0.014, -0.009, None), ("Demo Gym D (illustrative)", 0.019, -0.016, None)]
    for name, dla, dln, price in demo_comps:
        db.add(Competitor(project_id=p.id, source="demo", source_ref=f"demo/{name}", name=name, lat=lat + dla, lng=lng + dln,
                          geog=point_wkt(lat + dla, lng + dln), tags={"leisure": "fitness_centre"}, price=price, notes=DEMO_LABEL,
                          retrieved_at=utcnow()))
    src = {"source": "demo", "name": "Demo dataset", "kind": "demo", "license": "", "attribution": "", "url": "", "coverage_note": DEMO_LABEL,
           "retrieved_at": utcnow().isoformat(), "source_updated_at": None, "detail": "Synthetic population and competitors for demonstration.",
           "status": "ok", "from_cache": False, "layer": "demo"}
    db.add(MarketSnapshot(project_id=p.id, location_id=loc.id, status="complete", catchment_geojson={"type": "Polygon", "coordinates": [circle_polygon(lat, lng, 3.0)]},
                          catchment_method="radius", zones=zones, population={"method": "demo_synthetic", "source": "demo", "total": total, "radius_km": 3.0,
                                                                             "zones": len(zones), "spacing_km": 0.35},
                          sources=[src], coverage={"level": "unknown", "note": DEMO_LABEL, "signals": [], "method": "demo"}, activity_points=[], errors=[]))
    base = {"price": 1800, "quality": 0.6, "marketing_spend": 15000, "reference_price": 1600, "variable_cost_per_unit": None,
            "capacity": {"max_members": 350}, "rent": 65000, "payroll": 90000, "utilities": 18000, "other_fixed": 12000,
            "startup_cost": 1800000, "param_overrides": {}, "seed": 42}
    db.add(Scenario(project_id=p.id, location_id=loc.id, name="Baseline", is_baseline=True, inputs=base))
    db.add(Scenario(project_id=p.id, location_id=loc.id, name="Lower price ₹1,500", inputs=base | {"price": 1500}))
    db.commit()
    db.refresh(p)
    # Pre-run both scenarios so the live market plays immediately.
    from ..services.runs import execute_run
    for sc in list(p.scenarios):
        execute_run(db, p, sc)
    db.refresh(p)
    return project_out(p)


LIVE_SPOTS = {
    "cp-delhi": ("Connaught Place, New Delhi", 28.6315, 77.2167),
    "indiranagar": ("Indiranagar, Bengaluru", 12.9719, 77.6412),
    "bandra": ("Bandra West, Mumbai", 19.0596, 72.8295),
}


LIVE_KINDS = {
    "cafe": {
        "key": "cafe", "name": "Specialty café", "radius_km": 1.5, "alt": ("Lower price ₹280", 280),
        "positioning": ["Premium experience", "Better service"], "hours": "8am–11pm",
        "base": {"price": 350, "quality": 0.65, "marketing_spend": 30000, "reference_price": None, "variable_cost_per_unit": None,
                 "capacity": {"seats": 40, "turns_per_day": 4, "open_days_per_month": 30}, "rent": 250000, "payroll": 160000,
                 "utilities": 40000, "other_fixed": 20000, "startup_cost": 3000000, "param_overrides": {}, "seed": 42},
    },
    "gym": {
        "key": "gym", "name": "Gym", "radius_km": 2.5, "alt": ("Lower price ₹1,500", 1500),
        "positioning": ["Premium experience", "Extended operating hours"], "hours": "5:30am–10:30pm",
        "base": {"price": 2000, "quality": 0.65, "marketing_spend": 25000, "reference_price": None, "variable_cost_per_unit": None,
                 "capacity": {"max_members": 420}, "rent": 180000, "payroll": 150000, "utilities": 30000, "other_fixed": 15000,
                 "startup_cost": 3500000, "param_overrides": {}, "seed": 42},
    },
}


@router.post("/demo/live", status_code=201)
async def create_live_demo(spot: str = "cp-delhi", kind: str = "cafe", user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A real-data demo: live OpenStreetMap competitors + WorldPop population around a real street.
    Only the business inputs (price, rent, payroll…) are example assumptions, and they are labelled as such."""
    from ..config import get_settings
    from ..services.runs import execute_run, refresh_snapshot, start_refresh
    label, lat, lng = LIVE_SPOTS.get(spot, LIVE_SPOTS["cp-delhi"])
    k = LIVE_KINDS.get(kind, LIVE_KINDS["cafe"])
    cat = from_taxonomy_key(k["key"], k["key"]).as_dict()
    p = Project(owner_id=user.id, name=f"{k['name']} near {label.split(',')[0]}", objective="start_new", decision_goal="profit", category=cat,
                profile={"description": f"{k['name']}. Market data is live; business inputs are example assumptions you can edit.",
                         "positioning": k["positioning"], "operating_hours": k["hours"],
                         "inputs_note": "Example inputs entered for the demo"}, status="created", is_demo=False)
    db.add(p)
    db.flush()
    loc = CandidateLocation(project_id=p.id, label="Location A", address=label, lat=lat, lng=lng, geog=point_wkt(lat, lng),
                            catchment={"mode": "radius", "radius_km": k["radius_km"], "minutes": None, "profile": "foot-walking"})
    db.add(loc)
    db.flush()
    base = dict(k["base"])
    alt_name, alt_price = k["alt"]
    db.add(Scenario(project_id=p.id, location_id=loc.id, name="Baseline", is_baseline=True, inputs=base))
    db.add(Scenario(project_id=p.id, location_id=loc.id, name=alt_name, inputs=base | {"price": alt_price}))
    db.commit()
    db.refresh(p)
    if get_settings().serverless:
        try:
            await refresh_snapshot(db, p, loc)
            db.refresh(p)
            execute_run(db, p, next(s for s in p.scenarios if s.is_baseline))
        except Exception:  # the market page shows what failed and offers a retry
            db.rollback()
        db.refresh(p)
    else:
        start_refresh(db, p, loc)
    return project_out(p)
