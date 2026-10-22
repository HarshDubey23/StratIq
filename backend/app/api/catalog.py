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
