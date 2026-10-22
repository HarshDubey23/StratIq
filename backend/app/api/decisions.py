from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import ai
from ..categories.archetypes import ARCHETYPES
from ..db import get_db
from ..engine.recommend import decide
from ..models import ActualOutcome, CandidateLocation, Competitor, Project, Report, User, utcnow
from ..schemas import OutcomeIn
from ..security import current_user, owned_project
from ..services.runs import latest_runs, latest_snapshot
from .serialize import competitor_out, iso, location_out, scenario_out

router = APIRouter(tags=["decisions"])


def _decision(db: Session, p: Project, goal: str | None) -> dict:
    goal = goal or p.decision_goal
    if goal not in ("profit", "low_risk", "break_even", "growth"):
        raise HTTPException(422, "Unknown goal")
    runs = latest_runs(db, p)
    scen = []
    for s in p.scenarios:
        r = runs.get(s.id)
        if r:
            scen.append({"id": s.id, "name": s.name, "is_baseline": s.is_baseline, "result": r.results,
                         "stale": r.inputs_snapshot.get("scenario") != s.inputs, "run_id": r.id})
    evidence = {}
    if scen:
        best_ev = scen[0]["result"].get("evidence") or {}
        evidence = {"population_method": best_ev.get("population_method"), "population_source": best_ev.get("population_source"),
                    "catchment_method": best_ev.get("catchment_method"), "coverage": best_ev.get("coverage")}
    d = decide(scen, goal, evidence, ARCHETYPES[p.category["archetype"]].label)
    d["stale_scenarios"] = [s["name"] for s in scen if s["stale"]]
    d["not_run"] = [s.name for s in p.scenarios if s.id not in runs]
    d["model_version"] = scen[0]["result"]["model_version"] if scen else None
    return d


@router.get("/projects/{project_id}/decisions")
def decisions(project_id: str, goal: str | None = Query(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    return _decision(db, p, goal)


@router.post("/projects/{project_id}/explain")
async def explain(project_id: str, goal: str | None = Query(default=None), user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    d = _decision(db, p, goal)
    if d.get("verdict") == "no_conclusion":
        raise HTTPException(409, "Run a simulation first")
    return await ai.explain(d)


def _report_content(db: Session, p: Project) -> dict:
    d = _decision(db, p, None)
    runs = latest_runs(db, p)
    locs = []
    for l in p.locations:
        snap = latest_snapshot(db, l.id)
        locs.append({"location": location_out(l), "snapshot": None if not snap else {
            "retrieved_at": iso(snap.retrieved_at), "status": snap.status, "catchment_method": snap.catchment_method,
            "population": snap.population, "coverage": snap.coverage, "sources": snap.sources, "errors": snap.errors,
            "catchment_geojson": snap.catchment_geojson}})
    comps = [competitor_out(c) for c in db.scalars(select(Competitor).where(Competitor.project_id == p.id))]
    scen = []
    for s in p.scenarios:
        r = runs.get(s.id)
        scen.append({"scenario": scenario_out(s, r), "result": None if not r else {
            k: r.results.get(k) for k in ("summary", "finance", "monte_carlo", "segments", "parameters", "limitations", "drivers", "model_version")
        } | {"sensitivity": {k: (r.results.get("sensitivity") or {}).get(k) for k in ("tornado", "stress_tests", "thresholds", "price_curve")}}})
    return {"generated_at": utcnow().isoformat(), "project": {"name": p.name, "objective": p.objective, "decision_goal": p.decision_goal,
            "category": p.category, "profile": p.profile, "is_demo": p.is_demo},
            "archetype": ARCHETYPES[p.category["archetype"]].to_public(), "locations": locs, "competitors": comps,
            "scenarios": scen, "decision": d,
            "disclaimer": "This report contains model estimates under stated assumptions. It is not a guarantee of business success, and it is not financial advice."}


@router.post("/projects/{project_id}/reports", status_code=201)
def create_report(project_id: str, share: bool = Query(default=False), user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    rep = Report(project_id=p.id, content=_report_content(db, p), share_token=secrets.token_urlsafe(24) if share else None)
    db.add(rep)
    db.commit()
    return {"id": rep.id, "created_at": iso(rep.created_at), "share_token": rep.share_token}


@router.get("/projects/{project_id}/reports")
def list_reports(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    rows = db.scalars(select(Report).where(Report.project_id == p.id).order_by(Report.created_at.desc()).limit(20))
    return [{"id": r.id, "created_at": iso(r.created_at), "share_token": r.share_token} for r in rows]


@router.get("/reports/{report_id}")
def get_report(report_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    owned_project(r.project_id, user, db)
    return {"id": r.id, "created_at": iso(r.created_at), "share_token": r.share_token, "content": r.content}


@router.get("/shared/reports/{token}")
def shared_report(token: str, db: Session = Depends(get_db)):
    r = db.scalar(select(Report).where(Report.share_token == token)) if len(token) >= 20 else None
    if r is None:
        raise HTTPException(404, "Report not found")
    return {"id": r.id, "created_at": iso(r.created_at), "content": r.content}


@router.post("/reports/{report_id}/unshare", status_code=204)
def unshare(report_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    owned_project(r.project_id, user, db)
    r.share_token = None
    db.commit()
    return Response(status_code=204)


# ---------------- monitoring ----------------
@router.post("/projects/{project_id}/actual-outcomes", status_code=201)
def add_outcome(project_id: str, body: OutcomeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    row = db.scalar(select(ActualOutcome).where(ActualOutcome.project_id == p.id, ActualOutcome.period == body.period))
    if row is None:
        row = ActualOutcome(project_id=p.id, period=body.period)
        db.add(row)
    row.units, row.revenue, row.costs, row.note = body.units, body.revenue, body.costs, body.note
    db.commit()
    return {"id": row.id, "period": row.period}


@router.delete("/projects/{project_id}/actual-outcomes/{period}", status_code=204)
def delete_outcome(project_id: str, period: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    row = db.scalar(select(ActualOutcome).where(ActualOutcome.project_id == p.id, ActualOutcome.period == period))
    if row:
        db.delete(row)
        db.commit()
    return Response(status_code=204)


@router.get("/projects/{project_id}/monitor")
def monitor(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    runs = latest_runs(db, p)
    base = next((s for s in p.scenarios if s.is_baseline), None)
    forecast = None
    if base and base.id in runs:
        r = runs[base.id].results
        forecast = {"run_id": runs[base.id].id, "run_at": iso(runs[base.id].finished_at), "units": r["summary"]["units_sold"],
                    "revenue": r["finance"]["revenue"], "costs": (r["finance"]["fixed_cost"] or 0) + (r["finance"]["variable_cost"] or 0),
                    "units_p10": ((r.get("monte_carlo") or {}).get("units") or {}).get("p10"),
                    "units_p90": ((r.get("monte_carlo") or {}).get("units") or {}).get("p90"), "unit_label": r["unit_label"]}
    rows = []
    for o in db.scalars(select(ActualOutcome).where(ActualOutcome.project_id == p.id).order_by(ActualOutcome.period)):
        err = None
        if forecast and o.units is not None and forecast["units"]:
            err = {"units_abs": round(o.units - forecast["units"], 1), "units_pct": round((o.units - forecast["units"]) / forecast["units"], 4)}
        rows.append({"period": o.period, "units": o.units, "revenue": o.revenue, "costs": o.costs, "note": o.note,
                     "source": "user-entered (not independently verified)", "error": err,
                     "within_p10_p90": None if not forecast or o.units is None or forecast["units_p10"] is None else forecast["units_p10"] <= o.units <= forecast["units_p90"]})
    wape = None
    pairs = [(r["units"], forecast["units"]) for r in rows if forecast and r["units"] is not None]
    if pairs and sum(a for a, _ in pairs) > 0:
        wape = round(sum(abs(a - f) for a, f in pairs) / sum(a for a, _ in pairs), 4)
    return {"forecast": forecast, "actuals": rows, "wape_units": wape,
            "note": "Forecast error is computed only from figures you enter. The model is not automatically recalibrated."}
