"""Optional LLM features (Anthropic Messages API).

The LLM is used for two narrow jobs and is never in the numerical path:
1. Map a free-text business description to OSM tag filters + archetype
   (output validated against an allow-list; no market numbers accepted).
2. Paraphrase the rule-based decision into plain language. Every number in the
   paraphrase must already exist in the decision payload, otherwise the
   paraphrase is discarded.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from .categories.archetypes import ARCHETYPES
from .config import get_settings

log = logging.getLogger("strataiq.ai")
API = "https://api.anthropic.com/v1/messages"


def enabled() -> bool:
    return bool(get_settings().anthropic_api_key)


async def _call(system: str, user: str, tool: dict | None = None, max_tokens: int = 700) -> dict | None:
    s = get_settings()
    body = {"model": s.anthropic_model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user}]}
    if tool:
        body["tools"] = [tool]
        body["tool_choice"] = {"type": "tool", "name": tool["name"]}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(API, json=body, headers={"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01",
                                                       "content-type": "application/json"})
            r.raise_for_status()
            return r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("anthropic call failed: %s", e)
        return None


CATEGORY_TOOL = {
    "name": "map_category",
    "description": "Map a business idea to OpenStreetMap tag filters for finding competing businesses, and to an economic model type.",
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Short human label for the business category."},
            "archetype": {"type": "string", "enum": sorted(ARCHETYPES)},
            "osm_filters": {"type": "array", "maxItems": 5, "items": {"type": "string"},
                            "description": 'Overpass QL tag selectors such as ["shop"="bicycle"] or ["cuisine"~"pizza",i]. Allowed keys: amenity, shop, leisure, tourism, healthcare, office, craft, sport, cuisine, club, name, brand.'},
        },
        "required": ["label", "archetype", "osm_filters"],
    },
}


async def propose_category(query: str) -> dict | None:
    if not enabled():
        return None
    arch_desc = "\n".join(f"- {k}: {a.description}" for k, a in ARCHETYPES.items())
    sys = ("You map small-business ideas to OpenStreetMap tags so a system can find competing businesses on a map. "
           "Use real, documented OSM tag values (wiki.openstreetmap.org). Prefer specific tags; add a name-regex selector only as a supplement. "
           "Do not output prices, demand or any statistics.\nEconomic model types:\n" + arch_desc)
    resp = await _call(sys, f"Business idea: {query[:200]}", CATEGORY_TOOL, 400)
    if not resp:
        return None
    for block in resp.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "map_category":
            return block.get("input")
    return None


_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def _numbers(obj) -> set[float]:
    out: set[float] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            out |= _numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _numbers(v)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.add(float(obj))
    elif isinstance(obj, str):
        for m in _NUM.findall(obj):
            try:
                out.add(float(m.replace(",", "")))
            except ValueError:
                pass
    return out


def grounded(text: str, source: dict) -> bool:
    """True if every number in ``text`` matches (within 1%) a number present in ``source``."""
    allowed = _numbers(source)
    for m in _NUM.findall(text):
        try:
            x = float(m.replace(",", ""))
        except ValueError:
            continue
        if abs(x) < 10 and x == int(x):  # small integers (list numbering, "3 competitors") are tolerated
            continue
        if not any(abs(x - a) <= max(0.01 * abs(a), 0.5) or abs(x - a * 100) <= 0.6 for a in allowed):
            return False
    return True


async def explain(decision: dict) -> dict:
    if not enabled():
        return {"status": "disabled", "text": None}
    payload = {k: decision.get(k) for k in ("headline", "verdict", "objective_label", "financial_summary", "recommendations", "risks", "next_actions")}
    sys = ("You explain a business feasibility model's output to a first-time entrepreneur in plain, calm language (120-180 words). "
           "Use ONLY facts and numbers present in the JSON. Do not add new numbers, percentages, prices or forecasts. "
           "Say clearly that results are model estimates under stated assumptions. No markdown headers.")
    resp = await _call(sys, json.dumps(payload, default=str)[:12000], None, 500)
    if not resp:
        return {"status": "error", "text": None}
    text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text").strip()
    if not text:
        return {"status": "error", "text": None}
    if not grounded(text, payload):
        log.info("discarded ungrounded explanation")
        return {"status": "rejected_ungrounded", "text": None}
    return {"status": "ok", "text": text, "model": get_settings().anthropic_model}
