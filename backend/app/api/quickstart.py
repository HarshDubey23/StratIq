"""Quick start: "I want to open a café in Indiranagar for ₹250" -> a ready-to-run project plan.

For people who don't know what a catchment, variable cost or capacity is. We read the sentence (business type, place,
price, budget), fill everything else with labelled starter assumptions typical for small Indian businesses of that
kind, show the plan for a quick edit, and create the project. Nothing here is presented as data: every filled value is
listed under "assumptions" so the person knows what to replace with real quotes.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..categories.archetypes import ARCHETYPES
from ..categories.resolver import from_taxonomy_key, rank_taxonomy, resolve_offline
from ..db import get_db, session_factory
from ..models import CandidateLocation, Project, Scenario, User
from ..providers import osm
from ..providers.http import Cache, ProviderError
from ..security import current_user
from ..services.runs import point_wkt
from .serialize import project_out

router = APIRouter(tags=["quickstart"])

# Typical price per unit (₹) for common categories — starter assumptions, shown as such.
TYPICAL_PRICE = {
    "gym": 1500, "yoga_studio": 1800, "dance_school": 1500, "martial_arts": 1500, "swimming": 2000, "coaching_centre": 2500,
    "language_school": 3000, "music_school": 2000, "driving_school": 4500, "coworking": 6000, "library": 1200, "kindergarten": 5000,
    "sports_club": 1500, "pg_hostel": 9000,
    "cafe": 250, "restaurant": 550, "bar": 1200, "ice_cream": 150, "juice_bar": 120, "food_court": 180, "tea_stall": 30, "bakery_cafe": 220,
    "pizza": 400, "fast_food": 220, "cloud_kitchen": 180, "bakery": 300, "biryani": 280, "chinese_takeaway": 180, "street_food": 80,
    "pharmacy": 450, "grocery": 600, "fruit_veg": 250, "butcher": 500, "dairy": 120, "clothing": 1500, "shoes": 1800, "electronics": 3000,
    "hardware": 900, "stationery": 250, "jewelry": 15000, "optician": 2500, "cosmetics": 700, "pet_shop": 900, "florist": 500,
    "furniture": 12000, "liquor": 900, "sports_shop": 1500, "toy_shop": 800, "fuel": 1000, "ev_charging": 300,
    "salon": 350, "beauty_salon": 900, "clinic": 500, "dentist": 1200, "physio": 700, "diagnostics": 900, "veterinary": 600,
    "pet_grooming": 900, "car_repair": 2500, "car_wash": 500, "laundry": 300, "tailor": 600, "phone_repair": 900, "photo_studio": 1500,
    "tattoo": 3000, "print_shop": 100, "hotel": 2800, "guest_house": 1800, "hostel": 700, "banquet": 60000,
}
ARCH_PRICE = {"membership": 1500, "dine_in": 300, "takeaway": 250, "retail": 600, "appointment": 500, "lodging": 2500}

# Monthly fixed costs and startup for a small outlet, by model type (₹). Starter assumptions.
ARCH_COSTS = {
    "membership": {"rent": 120000, "payroll": 120000, "utilities": 25000, "other_fixed": 10000, "marketing_spend": 20000, "startup_cost": 2500000},
    "dine_in": {"rent": 90000, "payroll": 120000, "utilities": 30000, "other_fixed": 15000, "marketing_spend": 15000, "startup_cost": 1500000},
    "takeaway": {"rent": 60000, "payroll": 100000, "utilities": 25000, "other_fixed": 15000, "marketing_spend": 20000, "startup_cost": 1000000},
    "retail": {"rent": 60000, "payroll": 50000, "utilities": 10000, "other_fixed": 8000, "marketing_spend": 8000, "startup_cost": 1200000},
    "appointment": {"rent": 50000, "payroll": 90000, "utilities": 12000, "other_fixed": 8000, "marketing_spend": 10000, "startup_cost": 800000},
    "lodging": {"rent": 300000, "payroll": 200000, "utilities": 60000, "other_fixed": 30000, "marketing_spend": 30000, "startup_cost": 5000000},
}

_MONEY = r"(?:₹|rs\.?|inr|rupees?)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|hazaar|hazar|lakh|lac|l|crore|cr)?\b"


def _amount(num: str, unit: str | None) -> float:
    v = float(num.replace(",", ""))
    u = (unit or "").lower()
    return v * (1e7 if u in ("crore", "cr") else 1e5 if u in ("lakh", "lac", "l") else 1e3 if u in ("k", "thousand", "hazaar", "hazar") else 1)


def parse_idea(text: str) -> dict:
    """Pull business type, place, price and budget out of a sentence (English or Hinglish)."""
    t = " ".join((text or "").split())
    tl = t.lower()
    budget = None
    m = re.search(r"(?:budget|invest\w*|capital|paisa|paise|lagana|lagaun\w*|have|hai)\D{0,20}" + _MONEY, tl) or re.search(_MONEY + r"\s*(?:budget|investment|capital)", tl)
    if m:
        budget = _amount(m.group(1), m.group(2))
    price = None
    m = re.search(r"(?:price|charge|fee|fees|rate|sell\w*|at|for|@)\s*(?:of\s*)?(?:₹|rs\.?|inr)\s*(\d[\d,]*)", tl) or \
        re.search(r"(?:price|charge|fee|fees|rate)\D{0,12}(\d[\d,]*)", tl) or re.search(r"(?:₹|rs\.?)\s*(\d[\d,]*)\s*(?:per|a|each|/)", tl)
    if m:
        price = float(m.group(1).replace(",", ""))
        if budget and abs(price - budget) < 1:
            price = None
    place = None
    stop_after = r"(?=\s*,?\s+(?:with|for|at|price|budget|and|under|charging|selling|fees?|rate|per|₹|rs|mein|me|pe|par)\b|\s*,\s*(?:fees?|price|budget|rate)\b|[.!?]|$)"
    hm = re.search(r"([A-Za-z][A-Za-z .,'-]{2,60}?)\s+(?:mein|me|pe|par)\s", t, re.I)  # Hinglish: "Koramangala mein ..."
    m = re.search(r"\b(?:in|at|near|around)\s+([A-Za-z][A-Za-z0-9 .,'-]{2,80}?)" + stop_after, t, re.I)
    if m:
        place = m.group(1).strip(" ,.")
    elif hm:
        words = [w for w in hm.group(1).split() if w.lower() not in {"mujhe", "main", "hum", "mera", "meri", "humein", "i", "want", "to", "ek"}]
        place = " ".join(words).strip(" ,.") or None
    business = t
    if place:
        business = re.sub(r"\b(?:in|at|near|around)\s+" + re.escape(place) + r"|" + re.escape(place) + r"\s+(?:mein|me|pe|par)\b", " ", t, flags=re.I)
        business = re.split(r",\s*(?:fees?|price|budget|rate)\b", business, flags=re.I)[0]
        business = re.sub(r"\b(mujhe|ek|kholna|kholni|hai|chahta|chahti|hoon|hu|i want to open|i want to start|want to open)\b", " ", business, flags=re.I)
    business = re.sub(r"(?:₹|rs\.?)\s*\d[\d,]*|\d[\d,]*\s*(?:k|lakh|lac|crore)?", " ", business, flags=re.I)
    return {"text": t, "business": business.strip(), "place": place, "price": price, "budget": budget}


class PlanIn(BaseModel):
    text: str = Field(min_length=3, max_length=400)
    lat: float | None = Field(default=None, ge=-85, le=85)
    lng: float | None = Field(default=None, ge=-180, le=180)
    place_label: str | None = Field(default=None, max_length=200)


async def build_plan(body: dict) -> dict:
    p = parse_idea(body["text"])
    ranked = rank_taxonomy(p["business"] or p["text"])
    try:
        cat = resolve_offline(p["business"] or p["text"]).as_dict()
    except ValueError:
        cat = None
    if cat and cat.get("method") != "taxonomy" and ranked and ranked[0][1] >= 0.5:
        cat = from_taxonomy_key(ranked[0][0].key).as_dict()
    questions: list[str] = []
    if not cat:
        raise HTTPException(422, "Tell me what kind of business, for example 'a café' or 'a gym'.")
    place = None
    if body.get("lat") is not None and body.get("lng") is not None:
        place = {"name": body.get("place_label") or "Selected place", "display_name": body.get("place_label") or "", "lat": body["lat"], "lng": body["lng"]}
    elif p["place"]:
        try:
            res, _ = await osm.geocode(p["place"], limit=3, cache=Cache(session_factory()), country_codes=None)
        except ProviderError:
            res = []
        if res:
            place = res[0]
        else:
            questions.append(f"I couldn't find \"{p['place']}\" on the map — pick the place below.")
    else:
        questions.append("Where do you want to open it? Pick a place below.")
    arch_key = cat["archetype"]
    arch = ARCHETYPES[arch_key]
    costs = dict(ARCH_COSTS[arch_key])
    assumptions = []
    price = p["price"]
    if not price:
        price = float(TYPICAL_PRICE.get(cat["key"], ARCH_PRICE[arch_key]))
        assumptions.append(f"{arch.price_label}: ₹{int(price):,} (a typical price for this kind of business — change it to yours)")
    if p["budget"]:
        costs["startup_cost"] = float(p["budget"])
    else:
        assumptions.append(f"Startup cost: ₹{int(costs['startup_cost']):,} (typical for a small outlet)")
    assumptions += [
        f"Rent ₹{int(costs['rent']):,}, staff ₹{int(costs['payroll']):,}, utilities ₹{int(costs['utilities']):,} and other ₹{int(costs['other_fixed']):,} a month",
        f"Marketing ₹{int(costs['marketing_spend']):,} a month",
        "Food / material cost per sale: a typical share of price for this category",
        "Capacity: " + ", ".join(f"{f.label.lower()} {int(f.default) if f.default is not None else '—'}" for f in arch.capacity_fields),
    ]
    capacity = {f.key: float(f.default) for f in arch.capacity_fields if f.default is not None}
    name = f"{cat['label']}" + (f" near {place['name']}" if place else "")
    return {
        "parsed": p, "category": cat, "archetype": {"key": arch_key, "label": arch.label, "unit": arch.unit_label, "price_label": arch.price_label},
        "place": place, "price": price, "costs": costs, "capacity": capacity, "radius_km": arch.default_catchment_km,
        "assumptions": assumptions, "questions": questions, "name": name[:160],
        "ready": place is not None,
    }


@router.post("/quickstart/plan")
async def plan(body: PlanIn, user: User = Depends(current_user)):
    return await build_plan(body.model_dump())


class CreateIn(BaseModel):
    plan: dict
    price: float | None = Field(default=None, gt=0, le=10_000_000)
    startup_cost: float | None = Field(default=None, ge=0, le=1e10)
    rent: float | None = Field(default=None, ge=0, le=1e9)


def create_from_plan(db: Session, user: User, pl: dict, price: float | None = None, startup: float | None = None, rent: float | None = None) -> Project:
    place, cat = pl.get("place"), pl.get("category")
    if not place or not cat:
        raise HTTPException(422, "The plan needs a business type and a place")
    arch_key = cat["archetype"]
    if arch_key not in ARCHETYPES:
        raise HTTPException(422, "Unknown business model type")
    costs = dict(pl.get("costs") or ARCH_COSTS[arch_key])
    p = Project(owner_id=user.id, name=str(pl.get("name") or cat["label"])[:160], objective="start_new", decision_goal="profit",
                category={k: cat.get(k) for k in ("query", "key", "label", "archetype", "filters", "method", "confidence", "needs_confirmation", "alternatives", "notes")},
                profile={"description": (pl.get("parsed") or {}).get("text", ""), "quick_start": True, "assumptions": pl.get("assumptions") or []},
                status="created")
    db.add(p)
    db.flush()
    lat, lng = float(place["lat"]), float(place["lng"])
    loc = CandidateLocation(project_id=p.id, label="Location A", address=str(place.get("display_name") or place.get("name") or "")[:400],
                            lat=lat, lng=lng, geog=point_wkt(lat, lng),
                            catchment={"mode": "radius", "radius_km": float(pl.get("radius_km") or ARCHETYPES[arch_key].default_catchment_km),
                                       "minutes": None, "profile": "foot-walking"}, manual_population=None)
    db.add(loc)
    db.flush()
    inputs = {"price": float(price or pl.get("price") or ARCH_PRICE[arch_key]), "quality": 0.55, "marketing_spend": float(costs.get("marketing_spend", 0)),
              "reference_price": None, "variable_cost_per_unit": None, "capacity": pl.get("capacity") or {},
              "rent": float(rent if rent is not None else costs.get("rent", 0)), "payroll": float(costs.get("payroll", 0)),
              "utilities": float(costs.get("utilities", 0)), "other_fixed": float(costs.get("other_fixed", 0)),
              "startup_cost": float(startup if startup is not None else costs.get("startup_cost", 0)), "param_overrides": {}, "offer": None, "seed": 42}
    db.add(Scenario(project_id=p.id, location_id=loc.id, name="Baseline", is_baseline=True, inputs=inputs))
    db.commit()
    db.refresh(p)
    return p


@router.post("/quickstart/create", status_code=201)
def create(body: CreateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = create_from_plan(db, user, body.plan, body.price, body.startup_cost, body.rent)
    return project_out(p)
