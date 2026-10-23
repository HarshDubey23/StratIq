from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import ai
from ..categories.archetypes import ARCHETYPES
from ..categories.resolver import from_taxonomy_key, merge_llm_proposal, resolve_offline
from ..categories.taxonomy import TAXONOMY
from ..db import session_factory
from ..engine.model import MODEL_VERSION
from ..models import User
from ..providers import osm
from ..providers.http import Cache, ProviderError
from ..providers.registry import SOURCES
from ..schemas import CategoryIn
from ..security import current_user

router = APIRouter(tags=["catalog"])


@router.get("/categories/archetypes")
def archetypes():
    return [a.to_public() for a in ARCHETYPES.values()]


@router.get("/categories/catalog")
def catalog():
    return [{"key": e.key, "label": e.label, "archetype": e.archetype, "synonyms": list(e.synonyms)} for e in TAXONOMY]


@router.post("/categories/resolve")
async def resolve(body: CategoryIn, user: User = Depends(current_user)):
    try:
        res = resolve_offline(body.query)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if res.method == "keyword" and body.use_ai and ai.enabled():
        proposal = await ai.propose_category(body.query)
        if proposal:
            res = merge_llm_proposal(res, proposal)
    out = res.as_dict()
    out["archetype_detail"] = ARCHETYPES[res.archetype].to_public()
    out["ai_available"] = ai.enabled()
    return out


@router.get("/categories/by-key/{key}")
def by_key(key: str, user: User = Depends(current_user)):
    try:
        res = from_taxonomy_key(key)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    out = res.as_dict()
    out["archetype_detail"] = ARCHETYPES[res.archetype].to_public()
    return out


@router.get("/market/search")
async def search(q: str = Query(min_length=2, max_length=200), country: str | None = Query(default=None, max_length=20),
                 user: User = Depends(current_user)):
    try:
        results, prov = await osm.geocode(q, cache=Cache(session_factory()), country_codes=country)
    except ProviderError as e:
        raise HTTPException(502, f"Place search is unavailable right now ({e.message[:120]}). You can still drop a pin on the map.") from e
    return {"results": results, "source": prov}


@router.get("/market/reverse")
async def reverse(lat: float = Query(ge=-85, le=85), lng: float = Query(ge=-180, le=180), user: User = Depends(current_user)):
    name = await osm.reverse(lat, lng, cache=Cache(session_factory()))
    return {"display_name": name}


@router.get("/sources")
def sources():
    return SOURCES


@router.get("/system/capabilities")
def capabilities():
    from ..config import get_settings
    s = get_settings()
    return {"ai": ai.enabled(), "routing": bool(s.ors_api_key), "population": "worldpop", "places": "openstreetmap",
            "model_version": MODEL_VERSION}


# Public, cached preview for the landing page: real competitors around a famous street, no account needed.
PREVIEW_SPOTS = {
    "cp-delhi": {"label": "Connaught Place, New Delhi", "lat": 28.6315, "lng": 77.2167},
    "indiranagar": {"label": "Indiranagar, Bengaluru", "lat": 12.9719, "lng": 77.6412},
    "bandra": {"label": "Bandra West, Mumbai", "lat": 19.0596, "lng": 72.8295},
    "koramangala": {"label": "Koramangala, Bengaluru", "lat": 12.9352, "lng": 77.6245},
}
PREVIEW_CATS = {"gym", "cafe", "pizza", "restaurant", "pharmacy", "salon", "bakery_cafe", "grocery", "clothing"}


@router.get("/market/preview")
async def preview(spot: str = Query(default="cp-delhi"), category: str = Query(default="cafe"), radius_m: int = Query(default=1600, ge=300, le=3000)):
    if spot not in PREVIEW_SPOTS or category not in PREVIEW_CATS:
        raise HTTPException(404, "Unknown preview")
    sp = PREVIEW_SPOTS[spot]
    entry = next((e for e in TAXONOMY if e.key == category), None)
    if entry is None:
        raise HTTPException(404, "Unknown category")
    try:
        pois, prov = await osm.fetch_competitors(sp["lat"], sp["lng"], radius_m, list(entry.filters), Cache(session_factory()), limit=400,
                                                 timeout_s=30, terms=[entry.label.split("/")[0].strip(), *entry.synonyms[:2]])
    except ProviderError as e:
        raise HTTPException(502, f"OpenStreetMap is busy right now ({e.message[:100]})") from e
    return {"spot": {**sp, "key": spot}, "category": {"key": entry.key, "label": entry.label}, "radius_m": radius_m,
            "competitors": [{"name": p["name"] or "Unnamed", "lat": p["lat"], "lng": p["lng"], "ref": p["ref"]} for p in pois],
            "source": {"name": prov.get("name"), "retrieved_at": prov.get("retrieved_at"), "detail": prov.get("detail"),
                       "from_cache": prov.get("from_cache"), "attribution": prov.get("attribution")}}
