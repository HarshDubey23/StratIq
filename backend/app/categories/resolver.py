"""Resolve free-text business descriptions to an OSM filter set + archetype.

Resolution order (each step records how the match was made, so the UI can be
honest about it):

1. ``taxonomy``  - fuzzy match against the seed catalogue.
2. ``llm``       - optional; an LLM proposes OSM tag filters + archetype. The
                   proposal is validated against an allow-list and a strict
                   selector grammar. The LLM never supplies prices, demand or
                   other market numbers.
3. ``keyword``   - fallback: search business *names* containing the user's
                   keyword, with a heuristic archetype the user must confirm.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher

from .archetypes import ARCHETYPES
from .taxonomy import ALLOWED_OSM_KEYS, TAXONOMY, TaxonomyEntry

TAXONOMY_THRESHOLD = 0.74

_SELECTOR_RE = re.compile(
    r'^(\[(?:"(?P<k>[a-z_:]+)"(?:(=|!=|~|!~)"(?P<v>[^"\\\[\]]{1,80})"(?:,i)?)?)\])+$'
)
_ONE_SEL = re.compile(r'\["([a-z_:]+)"(?:(=|!=|~|!~)"([^"\\\[\]]{1,80})"(?:,i)?)?\]')


@dataclass
class ResolvedCategory:
    query: str
    key: str
    label: str
    archetype: str
    filters: list[str]
    method: str  # taxonomy | llm | keyword | manual
    confidence: float
    needs_confirmation: bool
    alternatives: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = t.lower()
    t = re.sub(r"[^a-z0-9& ]+", " ", t)
    stop = {"a", "an", "the", "open", "opening", "start", "starting", "new", "my", "shop", "store", "business", "want", "to", "i", "near", "small", "ek", "kholna", "karna", "chahta", "hu", "hoon", "in", "of", "for", "and"}
    words = [w for w in t.split() if w not in stop]
    return " ".join(words).strip() or t.strip()


def _score_phrase(q: str, phrase: str) -> float:
    p = normalize(phrase)
    if not p or not q:
        return 0.0
    if q == p:
        return 1.0
    qt, pt = set(q.split()), set(p.split())
    if pt and pt <= qt:  # every word of the phrase appears in the query
        return 0.92 if len(pt) > 1 or len(p) > 3 else 0.85
    if qt and qt <= pt:
        return 0.86
    jacc = len(qt & pt) / max(1, len(qt | pt))
    ratio = SequenceMatcher(None, q, p).ratio()
    return max(ratio * 0.95, jacc * 0.9)


def score_entry(q: str, entry: TaxonomyEntry) -> float:
    phrases = (entry.label, entry.key.replace("_", " "), *entry.synonyms)
    return max(_score_phrase(q, ph) for ph in phrases)


def rank_taxonomy(query: str, limit: int = 5) -> list[tuple[TaxonomyEntry, float]]:
    q = normalize(query)
    scored = sorted(((e, score_entry(q, e)) for e in TAXONOMY), key=lambda x: -x[1])
    return scored[:limit]


def validate_filters(filters: list[str]) -> list[str]:
    """Keep only well-formed Overpass tag selectors on allow-listed keys."""
    ok: list[str] = []
    for f in filters:
        f = f.strip()
        if not f or len(f) > 200 or not _SELECTOR_RE.match(f):
            continue
        keys = [m.group(1) for m in _ONE_SEL.finditer(f)]
        if keys and all(k in ALLOWED_OSM_KEYS for k in keys):
            ok.append(f)
    return ok[:6]


_ARCH_HINTS = (
    ("lodging", ("hotel", "stay", "room", "lodge", "resort", "homestay")),
    ("membership", ("class", "classes", "academy", "coaching", "school", "studio", "training", "course", "club", "membership", "subscription")),
    ("appointment", ("repair", "service", "clinic", "care", "salon", "studio", "doctor", "consult", "therapy", "wash", "spa")),
    ("dine_in", ("cafe", "restaurant", "dining", "bar", "lounge", "dhaba", "eatery", "bistro")),
    ("takeaway", ("kitchen", "delivery", "takeaway", "pizza", "burger", "biryani", "momo", "roll", "food")),
)


def guess_archetype(query: str) -> str:
    q = normalize(query)
    for arch, words in _ARCH_HINTS:
        if any(w in q.split() or w in q for w in words):
            return arch
    return "retail"


def keyword_filters(query: str) -> list[str]:
    q = normalize(query)
    words = [w for w in q.split() if len(w) >= 3][:3]
    if not words:
        return []
    pattern = "|".join(re.escape(w) for w in words)
    return [f'["name"~"{pattern}",i]']


def resolve_offline(query: str) -> ResolvedCategory:
    query = (query or "").strip()
    if not query:
        raise ValueError("Category query is empty")
    ranked = rank_taxonomy(query)
    alts = [
        {"key": e.key, "label": e.label, "archetype": e.archetype, "score": round(s, 3)}
        for e, s in ranked
    ]
    best, score = ranked[0]
    if score >= TAXONOMY_THRESHOLD:
        return ResolvedCategory(
            query=query, key=best.key, label=best.label, archetype=best.archetype,
            filters=list(best.filters), method="taxonomy", confidence=round(score, 3),
            needs_confirmation=score < 0.85, alternatives=alts[1:],
        )
    arch = guess_archetype(query)
    filters = keyword_filters(query)
    return ResolvedCategory(
        query=query, key="custom:" + "-".join(normalize(query).split())[:40], label=query.strip().title(),
        archetype=arch, filters=filters, method="keyword", confidence=0.4,
        needs_confirmation=True, alternatives=alts,
        notes=[
            "No catalogue match. Competitors are searched by business name keyword, which misses businesses whose names do not contain it.",
            f"Business model type guessed as '{ARCHETYPES[arch].label}'. Please confirm or change it.",
        ],
    )


def from_taxonomy_key(key: str, query: str | None = None) -> ResolvedCategory:
    for e in TAXONOMY:
        if e.key == key:
            return ResolvedCategory(query=query or e.label, key=e.key, label=e.label, archetype=e.archetype,
                                    filters=list(e.filters), method="manual", confidence=1.0, needs_confirmation=False)
    raise ValueError(f"Unknown category key '{key}'")


def merge_llm_proposal(base: ResolvedCategory, proposal: dict) -> ResolvedCategory:
    """Apply a validated LLM proposal on top of an offline (keyword) result."""
    arch = proposal.get("archetype")
    filters = validate_filters(list(proposal.get("osm_filters") or []))
    if arch not in ARCHETYPES or not filters:
        base.notes.append("AI category mapping was rejected by validation; using keyword fallback.")
        return base
    label = str(proposal.get("label") or base.label)[:80]
    return ResolvedCategory(
        query=base.query, key="ai:" + "-".join(normalize(label).split())[:40], label=label,
        archetype=arch, filters=filters, method="llm", confidence=0.65, needs_confirmation=True,
        alternatives=base.alternatives,
        notes=["Category mapped to OpenStreetMap tags by an AI model and validated against an allow-list. Confirm it matches your business."],
    )
