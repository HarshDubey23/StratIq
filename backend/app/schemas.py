from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .categories.archetypes import ARCHETYPES
from .categories.resolver import validate_filters

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")

Objective = Literal["start_new", "improve_existing", "compare_locations", "test_strategy", "diagnose"]
DecisionGoal = Literal["profit", "low_risk", "break_even", "growth"]


class SignupIn(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=120)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v


class LoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return v.strip().lower()


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    preferences: dict


class PreferencesIn(BaseModel):
    preferences: dict


class CategoryIn(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    use_ai: bool = True


class CategoryModel(BaseModel):
    query: str = ""
    key: str
    label: str = Field(max_length=120)
    archetype: str
    filters: list[str] = Field(default_factory=list, max_length=6)
    method: str = "manual"
    confidence: float = 1.0
    needs_confirmation: bool = False
    alternatives: list[dict] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("archetype")
    @classmethod
    def _arch(cls, v: str) -> str:
        if v not in ARCHETYPES:
            raise ValueError(f"archetype must be one of {sorted(ARCHETYPES)}")
        return v

    @field_validator("filters")
    @classmethod
    def _filters(cls, v: list[str]) -> list[str]:
        # Catalogue filters are trusted; anything else must pass the strict validator.
        from .categories.taxonomy import TAXONOMY
        trusted = {f for e in TAXONOMY for f in e.filters}
        return [f for f in v if f in trusted] + validate_filters([f for f in v if f not in trusted])


class Catchment(BaseModel):
    mode: Literal["radius", "isochrone"] = "radius"
    radius_km: float | None = Field(default=None, gt=0.2, le=6)
    minutes: int | None = Field(default=None, ge=3, le=45)
    profile: Literal["foot-walking", "driving-car", "cycling-regular"] = "foot-walking"


class LocationIn(BaseModel):
    label: str = Field(default="Location A", max_length=80)
    address: str = Field(default="", max_length=400)
    lat: float = Field(ge=-85, le=85)
    lng: float = Field(ge=-180, le=180)
    catchment: Catchment = Field(default_factory=Catchment)
    manual_population: float | None = Field(default=None, gt=0, le=5_000_000)


class LocationPatch(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    catchment: Catchment | None = None
    manual_population: float | None = Field(default=None, ge=0, le=5_000_000)


class ScenarioInputs(BaseModel):
    price: float = Field(gt=0, le=10_000_000)
    quality: float = Field(default=0.55, ge=0, le=1)
    marketing_spend: float = Field(default=0, ge=0, le=100_000_000)
    reference_price: float | None = Field(default=None, gt=0)
    variable_cost_per_unit: float | None = Field(default=None, ge=0)
    capacity: dict[str, float] = Field(default_factory=dict)
    rent: float = Field(default=0, ge=0)
    payroll: float = Field(default=0, ge=0)
    utilities: float = Field(default=0, ge=0)
    other_fixed: float = Field(default=0, ge=0)
    startup_cost: float = Field(default=0, ge=0)
    param_overrides: dict[str, float] = Field(default_factory=dict)
    seed: int = Field(default=42, ge=0, le=2**31)

    @field_validator("capacity", "param_overrides")
    @classmethod
    def _nonneg(cls, v: dict[str, float]) -> dict[str, float]:
        for k, x in v.items():
            if x is None or x < 0 or len(k) > 60:
                raise ValueError(f"invalid value for {k}")
        return v


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    objective: Objective = "start_new"
    decision_goal: DecisionGoal = "profit"
    category: CategoryModel
    profile: dict = Field(default_factory=dict)
    location: LocationIn
    baseline: ScenarioInputs


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    decision_goal: DecisionGoal | None = None
    profile: dict | None = None
    category: CategoryModel | None = None
    status: str | None = Field(default=None, max_length=30)


class CompetitorIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-85, le=85)
    lng: float = Field(ge=-180, le=180)
    price: float | None = Field(default=None, gt=0)
    quality: float | None = Field(default=None, ge=0, le=1)
    is_hypothetical: bool = False
    notes: str = Field(default="", max_length=1000)


class CompetitorPatch(BaseModel):
    price: float | None = Field(default=None, ge=0)
    clear_price: bool = False
    quality: float | None = Field(default=None, ge=0, le=1)
    clear_quality: bool = False
    active: bool | None = None
    notes: str | None = Field(default=None, max_length=1000)


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    location_id: str | None = None
    inputs: ScenarioInputs | None = None
    clone_from: str | None = None


class ScenarioPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    location_id: str | None = None
    inputs: ScenarioInputs | None = None


class OutcomeIn(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    units: float | None = Field(default=None, ge=0)
    revenue: float | None = Field(default=None, ge=0)
    costs: float | None = Field(default=None, ge=0)
    note: str = Field(default="", max_length=500)


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    scenario_id: str
    snapshot_id: str | None
    status: str
    model_version: str
    input_hash: str
    seed: int
    started_at: datetime
    finished_at: datetime | None
    duration_ms: float | None
    error: str | None
