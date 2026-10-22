"""Source registry: every external source is described once, here, and the UI
renders provenance from these records rather than from hard-coded strings."""
from __future__ import annotations

from datetime import datetime, timezone

SOURCES: dict[str, dict] = {
    "osm_overpass": {
        "name": "OpenStreetMap (via Overpass API)",
        "kind": "observed",
        "license": "ODbL 1.0",
        "attribution": "© OpenStreetMap contributors",
        "url": "https://www.openstreetmap.org/copyright",
        "coverage_note": "Volunteer-mapped. Coverage of small and informal businesses varies a lot by area; prices are almost never recorded.",
    },
    "osm_nominatim": {
        "name": "Nominatim geocoder (OpenStreetMap)",
        "kind": "observed",
        "license": "ODbL 1.0",
        "attribution": "© OpenStreetMap contributors",
        "url": "https://operations.osmfoundation.org/policies/nominatim/",
        "coverage_note": "Place search. Usage limited to light, interactive use (max 1 request/second).",
    },
    "worldpop": {
        "name": "WorldPop Global population (100 m, unconstrained)",
        "kind": "official_aggregate_estimate",
        "license": "CC BY 4.0",
        "attribution": "WorldPop (www.worldpop.org), University of Southampton",
        "url": "https://www.worldpop.org/",
        "coverage_note": "Modelled gridded population estimate for a fixed reference year, not a live count.",
    },
    "openrouteservice": {
        "name": "openrouteservice isochrones",
        "kind": "derived",
        "license": "Service terms; OSM data ODbL",
        "attribution": "© openrouteservice.org by HeiGIT | Map data © OpenStreetMap contributors",
        "url": "https://openrouteservice.org/terms-of-service/",
        "coverage_note": "Travel-time areas from the road network; real traffic is not included.",
    },
    "user": {
        "name": "User-entered",
        "kind": "user",
        "license": "Owned by the user",
        "attribution": "",
        "url": "",
        "coverage_note": "Not independently verified.",
    },
    "model": {
        "name": "StrataIQ model",
        "kind": "model",
        "license": "",
        "attribution": "",
        "url": "/methodology",
        "coverage_note": "Estimated by the simulation; see methodology.",
    },
}


def provenance(source_key: str, *, retrieved_at: datetime | None = None, source_updated_at: str | None = None,
               detail: str = "", status: str = "ok", cached: bool = False) -> dict:
    meta = SOURCES[source_key]
    return {
        "source": source_key,
        "name": meta["name"],
        "kind": meta["kind"],
        "license": meta["license"],
        "attribution": meta["attribution"],
        "url": meta["url"],
        "coverage_note": meta["coverage_note"],
        "retrieved_at": (retrieved_at or datetime.now(timezone.utc)).isoformat(),
        "source_updated_at": source_updated_at,
        "detail": detail,
        "status": status,
        "from_cache": cached,
    }
