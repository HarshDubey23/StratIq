from __future__ import annotations

import copy

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db, session_factory
from ..models import CandidateLocation, Project, Scenario, SimulationRun, User, utcnow
from ..schemas import ScenarioCreate, ScenarioPatch
from ..security import current_user, owned_project
from ..services.runs import execute_run, latest_runs
from .serialize import run_out, scenario_out

router = APIRouter(tags=["scenarios"])


def _owned_scenario(scenario_id: str, user: User, db: Session) -> tuple[Project, Scenario]:
    s = db.get(Scenario, scenario_id)
    if s is None:
        raise HTTPException(404, "Scenario not found")
    p = owned_project(s.project_id, user, db)
    return p, s


@router.get("/projects/{project_id}/scenarios")
def list_scenarios(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    runs = latest_runs(db, p)
    return [scenario_out(s, runs.get(s.id)) for s in p.scenarios]


@router.post("/projects/{project_id}/scenarios", status_code=201)
def create_scenario(project_id: str, body: ScenarioCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    if len(p.scenarios) >= 12:
        raise HTTPException(422, "Up to 12 scenarios per project")
    base = next((s for s in p.scenarios if s.is_baseline), None)
    src = base
    if body.clone_from:
        src = next((s for s in p.scenarios if s.id == body.clone_from), None)
        if src is None:
            raise HTTPException(404, "Scenario to duplicate not found")
    inputs = body.inputs.model_dump() if body.inputs else copy.deepcopy(src.inputs if src else None)
    if inputs is None:
        raise HTTPException(422, "Inputs are required")
    loc_id = body.location_id or (src.location_id if src else p.locations[0].id)
    loc = db.get(CandidateLocation, loc_id)
    if not loc or loc.project_id != p.id:
        raise HTTPException(422, "Location does not belong to this project")
    s = Scenario(project_id=p.id, location_id=loc_id, name=body.name.strip(), is_baseline=False, inputs=inputs)
    db.add(s)
    p.updated_at = utcnow()
    db.commit()
    return scenario_out(s)


@router.patch("/scenarios/{scenario_id}")
def patch_scenario(scenario_id: str, body: ScenarioPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p, s = _owned_scenario(scenario_id, user, db)
    if body.name:
        s.name = body.name.strip()
    if body.location_id:
        loc = db.get(CandidateLocation, body.location_id)
        if not loc or loc.project_id != p.id:
            raise HTTPException(422, "Location does not belong to this project")
        s.location_id = loc.id
    if body.inputs is not None:
        s.inputs = body.inputs.model_dump()
    s.updated_at = utcnow()
    p.updated_at = utcnow()
    db.commit()
    runs = latest_runs(db, p)
    return scenario_out(s, runs.get(s.id))


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p, s = _owned_scenario(scenario_id, user, db)
    if s.is_baseline:
        raise HTTPException(422, "The baseline scenario cannot be deleted")
    db.delete(s)
    db.commit()
    return Response(status_code=204)


@router.post("/scenarios/{scenario_id}/reset")
def reset_to_baseline(scenario_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p, s = _owned_scenario(scenario_id, user, db)
    base = next((x for x in p.scenarios if x.is_baseline), None)
    if base is None or base.id == s.id:
        raise HTTPException(422, "Nothing to reset to")
    s.inputs = copy.deepcopy(base.inputs)
    s.location_id = base.location_id
    db.commit()
    return scenario_out(s)


def _run_sync(project_id: str, scenario_id: str) -> str:
    with session_factory()() as db:
        p = db.get(Project, project_id)
        s = db.get(Scenario, scenario_id)
        return execute_run(db, p, s).id


@router.post("/scenarios/{scenario_id}/runs", status_code=201)
async def run_scenario(scenario_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p, s = _owned_scenario(scenario_id, user, db)
    run_id = await run_in_threadpool(_run_sync, p.id, s.id)
    db.expire_all()
    run = db.get(SimulationRun, run_id)
    if run.status != "succeeded":
        raise HTTPException(422, {"message": run.error or "Simulation failed", "run_id": run.id})
    return run_out(run)


@router.get("/simulation-runs/{run_id}")
def get_run(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = db.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    owned_project(run.project_id, user, db)
    return run_out(run, include_results=False)


@router.get("/simulation-runs/{run_id}/results")
def get_run_results(run_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = db.get(SimulationRun, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    owned_project(run.project_id, user, db)
    if run.status != "succeeded":
        raise HTTPException(409, run.error or f"Run is {run.status}")
    return run_out(run)


@router.get("/scenarios/{scenario_id}/runs")
def list_runs(scenario_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, s = _owned_scenario(scenario_id, user, db)
    rows = db.scalars(select(SimulationRun).where(SimulationRun.scenario_id == s.id).order_by(SimulationRun.started_at.desc()).limit(20))
    return [run_out(r, include_results=False) for r in rows]


@router.get("/projects/{project_id}/compare")
def compare(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    runs = latest_runs(db, p)
    rows = []
    for s in p.scenarios:
        r = runs.get(s.id)
        if not r:
            rows.append({"scenario": scenario_out(s), "result": None})
            continue
        res = r.results
        mc = res.get("monte_carlo") or {}
        rows.append({
            "scenario": scenario_out(s, r), "run_id": r.id,
            "metrics": {
                "in_market_units": res["summary"]["in_market_units"], "modeled_demand_units": res["summary"]["modeled_demand_units"],
                "units_sold": res["summary"]["units_sold"], "capacity_units": res["summary"]["capacity_units"],
                "price": res["summary"]["price"], "revenue": res["finance"]["revenue"],
                "operating_cost": (res["finance"]["fixed_cost"] or 0) + (res["finance"]["variable_cost"] or 0),
                "operating_profit": res["finance"]["operating_profit"], "break_even_units": res["finance"]["break_even_units"],
                "utilization": res["finance"]["utilization"], "payback_months": res["finance"]["payback_months"],
                "profit_p10": (mc.get("profit") or {}).get("p10"), "profit_p50": (mc.get("profit") or {}).get("p50"),
                "profit_p90": (mc.get("profit") or {}).get("p90"), "prob_loss": mc.get("prob_loss"),
            },
            "unit_label": res["unit_label"],
        })
    return {"rows": rows}
