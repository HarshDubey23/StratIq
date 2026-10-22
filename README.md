# StrataIQ

**Simulate the market. Validate the move.**

StrataIQ lets an entrepreneur describe *any* local business, pick *any* searchable place, and test the decision before investing:
it loads live market evidence (competitors, buildings, population), simulates how synthetic customer segments choose
between the business, nearby competitors and not buying at all, and turns that into monthly economics, downside risk,
scenario comparisons and a list of what to verify next.

> Model outputs are estimates under stated assumptions. They are not predictions, guarantees or financial advice.

## What works

| Capability | How |
|---|---|
| Any business category | Free text → catalogue match (70+ seed categories) → optional AI tag mapping validated against an allow-list → keyword fallback. Mapped to one of 6 economic model types. |
| Any place | Nominatim search or drop a pin; radius or travel-time (openrouteservice) catchment |
| Live evidence with provenance | OpenStreetMap competitors and buildings (Overpass), WorldPop population; retrieval time and source-update time kept separately; coverage indicator from observable signals |
| Customer-choice simulation | Vectorised multinomial logit with outside option, lognormal affordability by segment, distance decay, awareness from marketing, capacity limits ([docs/MODEL.md](docs/MODEL.md)) |
| Uncertainty | Monte Carlo (seeded, reproducible) → P10/P50/P90 profit, modeled P(loss); tornado, price and marketing sweeps, stress tests, break-even thresholds |
| Agent Genome | 10,000 synthetic agents per run at real population density, **each with a 615-parameter genome** (16 correlated latent traits conditioned on age and income, 46 real-geometry measurements, 553 generated parameters). Every parameter is consumed by the model — audited in tests. [docs/GENOME.md](docs/GENOME.md) |
| Agent X-ray | Click any agent: its full genome, utility of each option split into 8 channels, and the parameters that pushed it away from you |
| Market DNA | Agents × 615 parameters heatmap grouped by outcome; what separates your customers from competitors'; where you win and lose |
| Calibration | Revealed-demand floor from incumbents (bounded, reported, can be disabled) |
| Real feedback | Field survey kit targeting the assumptions the result is most sensitive to (Van Westendorp pricing, hours, travel, attributes, channels) |
| Decisions | Rule-based verdict, ranking by goal (profit / low risk / payback / growth), recommendations with reason, uncertainty, what to verify and what would change them |
| Missing evidence | Add observed or hypothetical competitors, record their prices, exclude records, override population; re-run and see the delta |
| Reports | Snapshot report with sources, assumptions, scenarios, risks; print to PDF; revocable share links |
| Monitoring | Record actual monthly outcomes; forecast error and WAPE |
| Demo mode | One click, fully offline, permanently labelled "DEMO SCENARIO" |

## Architecture

```
Browser ── Next.js 15 (frontend/, Vercel) ── /api/* rewrite ──► FastAPI (backend/, Render/Docker)
                                                                  ├─ engine/      numpy choice model, finance, Monte Carlo, sensitivity, decisions
                                                                  ├─ categories/  archetypes, open taxonomy, resolver
                                                                  ├─ providers/   Nominatim, Overpass, WorldPop, openrouteservice, Anthropic (optional)
                                                                  ├─ services/    market snapshots, simulation runs
                                                                  └─ PostgreSQL + PostGIS (geography columns, GIST indexes, ST_DWithin)
```

The browser only talks to its own origin; the session is an httpOnly cookie (JWT, bcrypt passwords). All money and demand
numbers are produced by the tested Python engine. The optional LLM never produces numbers: its category mapping is validated,
and its explanations are discarded if they contain any number not present in the model output.

More: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/API.md](docs/API.md) · [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) · [docs/DEMO.md](docs/DEMO.md)

## Run locally

### Option A — Docker (everything)

```bash
cp .env.example .env      # optional keys: CONTACT_EMAIL, ORS_API_KEY, ANTHROPIC_API_KEY
docker compose up --build
open http://localhost:3000
```

### Option B — dev servers

```bash
# database
docker compose up -d db

# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql://strataiq:strataiq@localhost:5432/strataiq
alembic upgrade head
uvicorn app.main:app --reload            # http://localhost:8000/docs

# frontend (new terminal)
cd frontend
npm install
API_URL=http://localhost:8000 npm run dev  # http://localhost:3000
```

## Tests

```bash
cd backend
pytest                       # engine + provider parsing; API flow too when DATABASE_URL points to PostGIS
RUN_LIVE=1 pytest -m live -s # real calls to OpenStreetMap / WorldPop
```

CI (`.github/workflows/ci.yml`) runs lint, migrations up/down/up, the full test suite against a PostGIS service, a live-data
job, and a typecheck + production build of the frontend.

## Deploy (public URL)

1. **Database — Neon**: create a project, run `CREATE EXTENSION postgis;` in the SQL editor, copy the connection string.
2. **Backend — Render**: New → Blueprint → this repo (uses `render.yaml`). Set `DATABASE_URL`, `CONTACT_EMAIL`,
   and optionally `ORS_API_KEY`, `ANTHROPIC_API_KEY`. Migrations run on start. Check `https://<api>/api/health`.
3. **Frontend — Vercel**: import the repo, root directory `frontend`, env `API_URL=https://<your-render-api>`.

Free Render instances sleep when idle; open `/api/health` a minute before a live demo.

## Data and licences

Map data © OpenStreetMap contributors (ODbL) · Population © WorldPop, University of Southampton (CC BY 4.0) ·
Tiles © OpenFreeMap / OpenMapTiles · Routing © openrouteservice by HeiGIT. Contributor usernames from OSM are discarded.
