"""Shared HTTP client + database-backed response cache for external providers."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from ..config import get_settings

log = logging.getLogger("strataiq.providers")

_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None
_locks: dict[tuple[int, str], asyncio.Lock] = {}
_last_nominatim = 0.0


class ProviderError(RuntimeError):
    def __init__(self, provider: str, message: str):
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.message = message


def _lock(name: str) -> asyncio.Lock:
    """Per-event-loop lock (asyncio primitives cannot be shared across loops)."""
    key = (id(asyncio.get_running_loop()), name)
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


def overpass_slot() -> asyncio.Lock:
    """Public Overpass servers allow ~2 concurrent requests per IP; we use one at a time."""
    return _lock("overpass")


def client() -> httpx.AsyncClient:
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is not None and _client_loop is not loop:
        _client = None  # created under a different event loop (e.g. tests); make a fresh one
    if _client is None:
        _client_loop = loop
        s = get_settings()
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(s.http_timeout_s, connect=10.0),
            headers={"User-Agent": s.user_agent, "Accept": "application/json"},
            follow_redirects=True,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def nominatim_throttle() -> None:
    """Nominatim usage policy: at most one request per second per application."""
    global _last_nominatim
    async with _lock("nominatim"):
        wait = 1.05 - (time.monotonic() - _last_nominatim)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_nominatim = time.monotonic()


def cache_key(provider: str, payload: dict) -> str:
    raw = provider + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class Cache:
    """Thin cache over the provider_cache table. Works without a DB session (no-op)."""

    def __init__(self, session_factory=None):
        self.session_factory = session_factory

    def get(self, key: str) -> tuple[dict, datetime] | None:
        if not self.session_factory:
            return None
        from ..models import ProviderCache
        try:
            with self.session_factory() as db:
                row = db.get(ProviderCache, key)
                if row and row.expires_at > datetime.now(timezone.utc):
                    return row.payload, row.fetched_at
        except Exception as e:  # cache must never break a request
            log.warning("cache read failed: %s", e)
        return None

    def put(self, key: str, provider: str, payload: dict, ttl: timedelta) -> None:
        if not self.session_factory:
            return
        from ..models import ProviderCache
        try:
            with self.session_factory() as db:
                now = datetime.now(timezone.utc)
                row = db.get(ProviderCache, key)
                if row is None:
                    row = ProviderCache(key=key, provider=provider, payload=payload, fetched_at=now, expires_at=now + ttl)
                    db.add(row)
                else:
                    row.payload, row.fetched_at, row.expires_at = payload, now, now + ttl
                db.commit()
        except Exception as e:
            log.warning("cache write failed: %s", e)
