import os

import pytest


def pytest_collection_modifyitems(config, items):
    has_db = bool(os.getenv("DATABASE_URL"))
    run_live = os.getenv("RUN_LIVE") == "1"
    for item in items:
        if "db" in item.keywords and not has_db:
            item.add_marker(pytest.mark.skip(reason="DATABASE_URL not set"))
        if "live" in item.keywords and not run_live:
            item.add_marker(pytest.mark.skip(reason="set RUN_LIVE=1 to hit real providers"))


@pytest.fixture(autouse=True)
def offline_admin_and_routing(request, monkeypatch):
    """Snapshots also reverse-geocode the state and route zones over the road network: keep offline tests offline."""
    if "live" in request.keywords:
        return
    from app.providers import osm, routing

    async def fake_admin(lat, lng, cache=None):
        return {"state": "Delhi", "country_code": "IN", "settlement": "urban"}, {"source": "osm_nominatim", "name": "Nominatim"}

    async def fake_routes(zones, dests, cache=None):
        km = [[1.0 + 0.1 * j for j in range(len(dests))] for _ in zones]
        return {"car": {"km": km, "min": km}, "foot": {"km": km, "min": [[12.0] * len(dests) for _ in zones]}}, {"source": "osrm", "name": "OSRM"}

    monkeypatch.setattr(osm, "reverse_admin", fake_admin)
    monkeypatch.setattr(routing, "route_matrix", fake_routes)


@pytest.fixture(scope="session")
def migrated_db():
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture()
def client(migrated_db):
    from fastapi.testclient import TestClient
    from sqlalchemy import text

    from app.db import get_engine
    from app.main import app

    with get_engine().begin() as c:
        c.execute(text("TRUNCATE users, projects, candidate_locations, market_snapshots, competitors, scenarios, "
                       "simulation_runs, actual_outcomes, reports, provider_cache CASCADE"))
    with TestClient(app) as tc:
        yield tc
