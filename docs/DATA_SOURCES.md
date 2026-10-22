# Data sources and governance

All sources are described once in `backend/app/providers/registry.py`; the UI renders provenance from those records.

| Source | Used for | Access | Licence / attribution | Notes |
|---|---|---|---|---|
| OpenStreetMap via Overpass API | competitors, buildings, activity points | live, cached 12 h (buildings 3 d) | ODbL, “© OpenStreetMap contributors” | one request at a time, retries across public endpoints; contributor usernames/uids discarded; record last-edit time kept |
| Nominatim | place search, reverse geocode | live, throttled to 1 req/s, cached 14–30 d | ODbL | `User-Agent` includes `CONTACT_EMAIL` as the usage policy asks |
| WorldPop Global (wpgppop, 100 m) | total catchment population | live async task API, cached 60 d | CC BY 4.0 | fixed reference year (default 2020); not a live count |
| openrouteservice | travel-time catchments | optional (`ORS_API_KEY`) | ORS terms; OSM ODbL | falls back to radius, recorded as a snapshot error |
| OpenFreeMap tiles | base map, 3D buildings where heights exist | browser | © OpenMapTiles, OSM | falls back to the positron style |
| User input | prices, costs, competitors, actual outcomes | — | owned by the user | labelled user-entered, never “verified” |
| Anthropic API | optional category mapping and explanation text | optional (`ANTHROPIC_API_KEY`) | — | never produces numbers |

**Timestamps.** Each provenance record stores `retrieved_at` (when StrataIQ fetched it) and `source_updated_at` (OSM database
timestamp / record edit time / WorldPop reference year). The UI always shows both.

**Failures.** If a provider fails, the snapshot is saved with status `partial`/`failed` and an `errors` list; nothing is
fabricated. Without population, simulation is blocked until data loads or the user enters a population (labelled user).

**Coverage indicator.** Computed from mapped buildings per 1,000 residents, competitor-record completeness and edit recency.
It is a heuristic, not a measured recall rate.

**Privacy.** No personal data about individuals is collected. Synthetic agents are generated from aggregate zone weights.
