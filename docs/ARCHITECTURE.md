# Architecture

```
frontend/  Next.js 15 (App Router), TypeScript, Tailwind v4, MapLibre GL, Recharts, zod
  app/                      routes: / , /methodology, /sign-in, /sign-up, /onboarding, /r/[token]
  app/app/                  authenticated workspace (middleware redirects without session)
    projects/new            7-step wizard (objective → category → profile → finances → positioning → location → review)
    projects/[id]/          overview, market, simulation, decisions, report, monitor
  components/               AppShell, ProjectContext, MapView (MapLibre), charts, ReportView, ui primitives
  next.config.ts            /api/* → FastAPI (first-party cookie)

backend/   FastAPI, SQLAlchemy 2, Alembic, GeoAlchemy2, PostGIS, httpx, numpy/scipy
  app/categories/           archetypes (economic structure + documented parameters), taxonomy, resolver
  app/providers/            registry (provenance), http (client, cache, throttles), osm, population
  app/services/market.py    Market Reality Engine: catchment → parallel fetch → zones → coverage → snapshot
  app/services/runs.py      persist snapshots/competitors, build engine inputs, execute + record runs
  app/engine/               model (choice), finance, simulate (MC, sensitivity, agents), recommend (rules), geo
  app/api/                  routers (auth, catalog, projects, scenarios, decisions, demo)
  alembic/                  migrations (PostGIS extension, GIST indexes)
```

## Why categories are open

Category ≠ model. A *category* is how competitors are found (OSM tag filters). An *archetype* is how the economics work
(what a unit is, how capacity works, which parameters apply). Any category maps to one of six archetypes, so a new business
type needs no code, and adding a new archetype is a single entry in `archetypes.py`.

## Why data is "real-time" without being fragile

Evidence is fetched live per location on demand and frozen into a **market snapshot** (zones, sources, coverage, errors).
Runs reference the snapshot id + input hash + model version + seed, so results are reproducible while the underlying public
data keeps changing. Refreshing creates a new snapshot. Provider responses are cached within licence terms to respect rate
limits; failures degrade to clearly flagged partial snapshots, never fabricated data.

## Run lifecycle

1. validate inputs → 2. load snapshot + competitors within catchment (PostGIS `ST_DWithin`) → 3. build zones/alternatives →
4. choice model → 5. capacity → 6. economics → 7. Monte Carlo → 8. sensitivity/agents → 9. store JSON results with hash,
seed, version, duration → 10. decision layer on request.
