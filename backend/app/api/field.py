"""Field research: when open data is missing, a StrataIQ field researcher from the project's own industry goes to the
street, collects ground data and saves it here. The simulation then runs its agents on that data
(engine/field.py turns interviews into agent parameters; visited competitors become competitor rows).

Owner endpoints need the session. The researcher uses a no-login link (``/field/{token}``) that can only read the brief
and add records to that one project.
"""
from __future__ import annotations

import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..categories.archetypes import ARCHETYPES
from ..db import get_db
from ..engine.field import MIN_N, field_evidence
from ..models import Competitor, FieldRecord, FieldRequest, Project, User, utcnow
from ..security import current_user, owned_project
from ..services.runs import point_wkt
from .serialize import iso

router = APIRouter(tags=["field"])

MAX_RECORDS = 3000
Kind = Literal["interview", "competitor", "footfall", "rent"]


class InterviewData(BaseModel):
    uses_category: bool
    visits_per_month: float | None = Field(default=None, ge=0, le=60)
    max_price: float | None = Field(default=None, gt=0, le=10_000_000)
    travel_km: float | None = Field(default=None, ge=0, le=50)
    travel_mode: Literal["walk", "two_wheeler", "car", "bus_metro", "auto", "other"] | None = None
    age_band: Literal["under_18", "18_24", "25_34", "35_49", "50_plus"] | None = None
    notes: str = Field(default="", max_length=500)


class CompetitorData(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    price: float | None = Field(default=None, gt=0, le=10_000_000)
    quality: int | None = Field(default=None, ge=1, le=5)  # researcher's 1-5 rating
    visitors_per_hour: float | None = Field(default=None, ge=0, le=100_000)
    open_hours: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=500)


class FootfallData(BaseModel):
    count: int = Field(ge=0, le=100_000)
    minutes: int = Field(ge=1, le=480)
    time_of_day: Literal["morning", "afternoon", "evening", "night"]
    weekend: bool = False
    notes: str = Field(default="", max_length=500)


class RentData(BaseModel):
    monthly_rent: float = Field(gt=0, le=100_000_000)
    deposit: float | None = Field(default=None, ge=0, le=1_000_000_000)
    area_sqft: float | None = Field(default=None, gt=0, le=1_000_000)
    notes: str = Field(default="", max_length=500)


DATA_MODELS = {"interview": InterviewData, "competitor": CompetitorData, "footfall": FootfallData, "rent": RentData}


class RecordIn(BaseModel):
    kind: Kind
    data: dict
    lat: float | None = Field(default=None, ge=-85, le=85)
    lng: float | None = Field(default=None, ge=-180, le=180)
    collected_by: str = Field(default="", max_length=120)


class RequestIn(BaseModel):
    researcher_name: str = Field(default="", max_length=120)
    brief: str = Field(default="", max_length=2000)
    due_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class RequestPatch(RequestIn):
    status: Literal["requested", "in_field", "submitted", "closed"] | None = None
    researcher_name: str | None = Field(default=None, max_length=120)
    brief: str | None = Field(default=None, max_length=2000)


def specialty_for(p: Project) -> str:
    return f"{p.category.get('label') or 'Local business'} specialist"


def checklist(p: Project) -> list[dict]:
    arch = ARCHETYPES[p.category["archetype"]]
    label = (p.category.get("label") or "this business").lower()
    return [
        {"kind": "interview", "target": 25, "min": MIN_N["participation"], "title": "Street interviews",
         "how": f"Stop people near the site. Ask if they use {label}, how often, how far they travel, and the most they would pay "
                f"({arch.price_label.lower()})."},
        {"kind": "competitor", "target": 8, "min": 1, "title": "Visit every competitor",
         "how": "Walk the catchment. Pin each competitor, note its real price, rate it 1-5, and count visitors for a few minutes. "
                "Unmapped and informal shops matter most."},
        {"kind": "footfall", "target": 4, "min": 1, "title": "Footfall counts at the site",
         "how": "Count people passing the site for 15 minutes: morning, evening, and once on a weekend."},
        {"kind": "rent", "target": 2, "min": 1, "title": "Rent quotes",
         "how": "Ask the owner or a broker for monthly rent and deposit for the site or a similar unit nearby."},
    ]


def _record_out(r: FieldRecord) -> dict:
    return {"id": r.id, "kind": r.kind, "lat": r.lat, "lng": r.lng, "data": r.data, "collected_by": r.collected_by,
            "competitor_id": r.competitor_id, "created_at": iso(r.created_at)}


def _request_out(q: FieldRequest | None) -> dict | None:
    if not q:
        return None
    return {"id": q.id, "token": q.token, "specialty": q.specialty, "researcher_name": q.researcher_name, "status": q.status,
            "brief": q.brief, "due_date": q.due_date, "created_at": iso(q.created_at), "updated_at": iso(q.updated_at)}


def current_request(db: Session, project_id: str) -> FieldRequest | None:
    return db.scalar(select(FieldRequest).where(FieldRequest.project_id == project_id).order_by(FieldRequest.created_at.desc()).limit(1))


def project_records(db: Session, project_id: str) -> list[FieldRecord]:
    return list(db.scalars(select(FieldRecord).where(FieldRecord.project_id == project_id).order_by(FieldRecord.created_at)))


def summary_for(p: Project, records: list[FieldRecord]):
    arch = ARCHETYPES[p.category["archetype"]]
    fq = arch.params.get("frequency")
    fixed = bool(fq and fq.low == fq.high)
    return field_evidence([{"kind": r.kind, "data": r.data} for r in records], frequency_fixed=fixed)


def field_status(db: Session, p: Project) -> dict:
    """Small summary used by the project page header."""
    n = db.scalar(select(func.count()).select_from(FieldRecord).where(FieldRecord.project_id == p.id)) or 0
    q = current_request(db, p.id)
    return {"records": int(n), "status": q.status if q else None}


def _add(db: Session, p: Project, q: FieldRequest | None, body: RecordIn) -> FieldRecord:
    n = db.scalar(select(func.count()).select_from(FieldRecord).where(FieldRecord.project_id == p.id)) or 0
    if n >= MAX_RECORDS:
        raise HTTPException(409, "This project already holds the maximum number of field records")
    try:
        data = DATA_MODELS[body.kind].model_validate(body.data).model_dump()
    except Exception as e:  # pydantic ValidationError -> 422 with a readable message
        raise HTTPException(422, f"Invalid {body.kind} record: {e}") from e
    loc = p.locations[0] if p.locations else None
    lat, lng = body.lat, body.lng
    if body.kind == "competitor" and (lat is None or lng is None):
        raise HTTPException(422, "Pin the competitor's location")
    if (lat is None or lng is None) and loc:
        lat, lng = loc.lat, loc.lng
    who = body.collected_by.strip() or (q.researcher_name if q else "") or "Field researcher"
    rec = FieldRecord(project_id=p.id, request_id=q.id if q else None, kind=body.kind, lat=lat, lng=lng, data=data, collected_by=who)
    if body.kind == "competitor":
        c = Competitor(project_id=p.id, source="field", source_ref=None, name=data["name"].strip(), lat=lat, lng=lng,
                       geog=point_wkt(lat, lng), tags={"opening_hours": data["open_hours"]} if data.get("open_hours") else {},
                       price=data.get("price"), price_status="field" if data.get("price") else "unknown",
                       quality=(data["quality"] - 1) / 4 if data.get("quality") else None,
                       quality_status="field" if data.get("quality") else "unknown",
                       notes=f"Visited by {who}. {data.get('notes') or ''}".strip(), retrieved_at=utcnow())
        db.add(c)
        db.flush()
        rec.competitor_id = c.id
    db.add(rec)
    if q and q.status == "requested":
        q.status = "in_field"
    p.updated_at = utcnow()
    db.commit()
    return rec


def _payload(db: Session, p: Project) -> dict:
    recs = project_records(db, p.id)
    q = current_request(db, p.id)
    return {"specialty": specialty_for(p), "request": _request_out(q), "records": [_record_out(r) for r in recs],
            "summary": summary_for(p, recs).public(), "checklist": checklist(p)}


# ---------------------------------------------------------------- owner

@router.get("/projects/{project_id}/field")
def get_field(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _payload(db, owned_project(project_id, user, db))


@router.post("/projects/{project_id}/field/request", status_code=201)
def request_researcher(project_id: str, body: RequestIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    q = current_request(db, p.id)
    if q is None or q.status == "closed":
        q = FieldRequest(project_id=p.id, token=secrets.token_urlsafe(24), specialty=specialty_for(p))
        db.add(q)
    q.researcher_name, q.brief, q.due_date = body.researcher_name.strip(), body.brief.strip(), body.due_date
    db.commit()
    return _payload(db, p)


@router.patch("/projects/{project_id}/field/request")
def patch_request(project_id: str, body: RequestPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    q = current_request(db, p.id)
    if q is None:
        raise HTTPException(404, "No field request yet")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(q, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    return _payload(db, p)


@router.post("/projects/{project_id}/field/records", status_code=201)
def add_record(project_id: str, body: RecordIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    rec = _add(db, p, current_request(db, p.id), body)
    return _record_out(rec)


@router.delete("/projects/{project_id}/field/records/{record_id}", status_code=204)
def delete_record(project_id: str, record_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = owned_project(project_id, user, db)
    r = db.get(FieldRecord, record_id)
    if not r or r.project_id != p.id:
        raise HTTPException(404, "Record not found")
    if r.competitor_id:
        c = db.get(Competitor, r.competitor_id)
        if c and c.source == "field":
            db.delete(c)
    db.delete(r)
    db.commit()


# ---------------------------------------------------------------- researcher (no-login link)

def _by_token(db: Session, token: str) -> tuple[FieldRequest, Project]:
    q = db.scalar(select(FieldRequest).where(FieldRequest.token == token)) if 20 <= len(token) <= 64 else None
    if q is None or q.status == "closed":
        raise HTTPException(404, "This field link is not valid")
    return q, db.get(Project, q.project_id)


@router.get("/field/{token}")
def field_brief(token: str, db: Session = Depends(get_db)):
    q, p = _by_token(db, token)
    loc = p.locations[0] if p.locations else None
    arch = ARCHETYPES[p.category["archetype"]]
    recs = project_records(db, p.id)
    counts: dict[str, int] = {}
    for r in recs:
        counts[r.kind] = counts.get(r.kind, 0) + 1
    return {
        "project": {"name": p.name, "category": p.category.get("label"), "price_label": arch.price_label, "unit_label": arch.unit_label},
        "location": {"lat": loc.lat, "lng": loc.lng, "address": loc.address, "radius_km": (loc.catchment or {}).get("radius_km")} if loc else None,
        "request": {k: v for k, v in (_request_out(q) or {}).items() if k != "token"},
        "checklist": checklist(p), "counts": counts,
        "recent": [_record_out(r) for r in recs[-12:]][::-1],
    }


@router.post("/field/{token}/records", status_code=201)
def field_add(token: str, body: RecordIn, db: Session = Depends(get_db)):
    q, p = _by_token(db, token)
    return _record_out(_add(db, p, q, body))


@router.post("/field/{token}/submit")
def field_submit(token: str, db: Session = Depends(get_db)):
    q, _ = _by_token(db, token)
    q.status = "submitted"
    db.commit()
    return {"status": q.status}
