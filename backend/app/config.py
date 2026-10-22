from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _list(v: str | None, default: list[str]) -> list[str]:
    if not v:
        return default
    return [x.strip() for x in v.split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql+psycopg://strataiq:strataiq@localhost:5432/strataiq"))
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", "dev-insecure-change-me"))
    jwt_ttl_hours: int = field(default_factory=lambda: int(os.getenv("JWT_TTL_HOURS", "168")))
    cookie_secure: bool = field(default_factory=lambda: _bool(os.getenv("COOKIE_SECURE"), False))
    cors_origins: list[str] = field(default_factory=lambda: _list(os.getenv("CORS_ORIGINS"), ["http://localhost:3000"]))
    contact_email: str = field(default_factory=lambda: os.getenv("CONTACT_EMAIL", ""))
    nominatim_url: str = field(default_factory=lambda: os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org"))
    overpass_urls: list[str] = field(default_factory=lambda: _list(os.getenv("OVERPASS_URLS"), [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]))
    worldpop_url: str = field(default_factory=lambda: os.getenv("WORLDPOP_URL", "https://api.worldpop.org/v1"))
    worldpop_year: int = field(default_factory=lambda: int(os.getenv("WORLDPOP_YEAR", "2020")))
    ors_api_key: str = field(default_factory=lambda: os.getenv("ORS_API_KEY", ""))
    ors_url: str = field(default_factory=lambda: os.getenv("ORS_URL", "https://api.openrouteservice.org"))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5"))
    http_timeout_s: float = field(default_factory=lambda: float(os.getenv("HTTP_TIMEOUT_S", "40")))
    mc_draws: int = field(default_factory=lambda: int(os.getenv("MC_DRAWS", "800")))

    @property
    def user_agent(self) -> str:
        contact = f" ({self.contact_email})" if self.contact_email else ""
        return f"StrataIQ/1.0 market-simulation{contact}"

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        # Hosted providers hand out postgres:// or postgresql:// URLs; use the psycopg 3 driver.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.app_env == "production" and s.jwt_secret.startswith("dev-"):
        raise RuntimeError("JWT_SECRET must be set in production")
    return s
