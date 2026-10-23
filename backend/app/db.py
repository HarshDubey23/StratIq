from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

_engine = None
_SessionLocal = None


class Base(DeclarativeBase):
    pass


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        s = get_settings()
        if s.serverless:
            # short-lived instances behind a connection pooler: no client-side pool, no server-side prepared statements
            _engine = create_engine(s.sqlalchemy_url, poolclass=NullPool, connect_args={"prepare_threshold": None})
        else:
            _engine = create_engine(s.sqlalchemy_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_db() -> Iterator[Session]:
    get_engine()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def session_factory():
    get_engine()
    return _SessionLocal
