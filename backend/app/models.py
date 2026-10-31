from __future__ import annotations

import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geography
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    objective: Mapped[str] = mapped_column(String(40), nullable=False)  # start_new | improve_existing | compare_locations | test_strategy | diagnose
    decision_goal: Mapped[str] = mapped_column(String(20), default="profit", nullable=False)  # profit | low_risk | break_even | growth
    category: Mapped[dict] = mapped_column(JSONB, nullable=False)  # ResolvedCategory
    profile: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # business description, positioning, existing-business metrics
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    locations: Mapped[list["CandidateLocation"]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="CandidateLocation.created_at")
    scenarios: Mapped[list["Scenario"]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="Scenario.created_at")


class CandidateLocation(TimestampMixin, Base):
    __tablename__ = "candidate_locations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    address: Mapped[str] = mapped_column(Text, default="", nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    geog = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False)
    catchment: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {mode: radius|isochrone, radius_km, minutes, profile}
    manual_population: Mapped[float | None] = mapped_column(Float, nullable=True)

    project: Mapped[Project] = relationship(back_populates="locations")
    __table_args__ = (Index("ix_candidate_locations_geog", "geog", postgresql_using="gist"),)


class MarketSnapshot(Base):
    """A reproducible, timestamped capture of live market evidence around a location."""

    __tablename__ = "market_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    location_id: Mapped[str] = mapped_column(ForeignKey("candidate_locations.id", ondelete="CASCADE"), index=True, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # complete | partial | failed
    catchment_geojson: Mapped[dict] = mapped_column(JSONB, nullable=False)
    catchment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    zones: Mapped[list] = mapped_column(JSONB, nullable=False)
    population: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sources: Mapped[list] = mapped_column(JSONB, nullable=False)
    coverage: Mapped[dict] = mapped_column(JSONB, nullable=False)
    activity_points: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    errors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class Competitor(TimestampMixin, Base):
    __tablename__ = "competitors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # osm | user
    source_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)  # e.g. node/123
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    geog = mapped_column(Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False)
    tags: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)  # unknown | user | observed
    quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    is_hypothetical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "source", "source_ref", name="uq_competitor_source_ref"),
        Index("ix_competitors_geog", "geog", postgresql_using="gist"),
    )


class Scenario(TimestampMixin, Base):
    __tablename__ = "scenarios"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    location_id: Mapped[str] = mapped_column(ForeignKey("candidate_locations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)

    project: Mapped[Project] = relationship(back_populates="scenarios")


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    scenario_id: Mapped[str] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True, nullable=False)
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("market_snapshots.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # running | succeeded | failed
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    inputs_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class ActualOutcome(TimestampMixin, Base):
    __tablename__ = "actual_outcomes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    units: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue: Mapped[float | None] = mapped_column(Float, nullable=True)
    costs: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    __table_args__ = (UniqueConstraint("project_id", "period", name="uq_outcome_period"),)


class FieldRequest(TimestampMixin, Base):
    """A request for a StrataIQ field researcher from the project's industry to collect ground data in the catchment."""
    __tablename__ = "field_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # researcher's no-login field link
    specialty: Mapped[str] = mapped_column(String(160), nullable=False)  # industry the researcher must come from
    researcher_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="requested", nullable=False)  # requested | in_field | submitted | closed
    brief: Mapped[str] = mapped_column(Text, default="", nullable=False)
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD


class FieldRecord(Base):
    """One observation collected on the ground (interview, competitor visit, footfall count, rent quote)."""
    __tablename__ = "field_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    request_id: Mapped[str | None] = mapped_column(ForeignKey("field_requests.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # interview | competitor | footfall | rent
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    collected_by: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    competitor_id: Mapped[str | None] = mapped_column(ForeignKey("competitors.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)


class ProviderCache(Base):
    __tablename__ = "provider_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
