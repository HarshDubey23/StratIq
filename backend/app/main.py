from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .api import assistant, auth, catalog, decisions, demo, genome, insights, projects, scenarios
from .config import get_settings
from .db import get_engine
from .engine.model import MODEL_VERSION
from .providers.http import close_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("strataiq")


_migrated = False


def migrate_once() -> None:
    """Apply Alembic migrations once per process when AUTO_MIGRATE is on (serverless hosts have no release step)."""
    global _migrated
    if _migrated or not get_settings().auto_migrate:
        return
    _migrated = True
    try:
        from pathlib import Path

        from alembic import command
        from alembic.config import Config
        root = Path(__file__).resolve().parent.parent
        cfg = Config(str(root / "alembic.ini"))
        cfg.set_main_option("script_location", str(root / "alembic"))
        command.upgrade(cfg, "head")
        log.info("migrations applied")
    except Exception as e:  # pragma: no cover
        log.error("auto-migrate failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()
    migrate_once()
    yield
    await close_client()


app = FastAPI(title="StrataIQ API", version="1.0.0", lifespan=lifespan,
              description="Market simulation and decision-support API. All numeric outputs come from the documented model in docs/MODEL.md.")

app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def ensure_migrated(request: Request, call_next):
    if not _migrated and get_settings().auto_migrate:
        from fastapi.concurrency import run_in_threadpool
        await run_in_threadpool(migrate_once)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(x) for x in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Validation failed", "errors": errors})


API = "/api/v1"
for r in (auth.router, catalog.router, projects.router, scenarios.router, decisions.router, demo.router, genome.router, assistant.router, insights.router):
    app.include_router(r, prefix=API)


@app.get("/api/health")
def health():
    db_ok, err = True, None
    try:
        with get_engine().connect() as c:
            c.execute(text("select 1"))
    except Exception as e:  # pragma: no cover
        log.error("health db error: %s", e)
        db_ok = False
        import re
        err = re.sub(r"://[^@\s]+@", "://***@", f"{type(e).__name__}: {e}")[:300]
    body = {"status": "ok" if db_ok else "degraded", "db": db_ok, "model_version": MODEL_VERSION}
    if err:
        body["db_error"] = err
    return JSONResponse(status_code=200 if db_ok else 503, content=body)
