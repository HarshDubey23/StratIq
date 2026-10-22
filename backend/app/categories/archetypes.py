"""Economic archetypes.

Categories are open-ended (a user can type any business). Every category is
resolved to one of a small set of *economic archetypes*. The archetype fixes
the structure of the model (what a "unit" is, how capacity works, which inputs
the wizard asks for). Numeric parameters are explicit ASSUMPTIONS with a
documented low/high range; the UI shows them and lets the user override them.

None of these defaults are calibrated against real outcome data. They exist so
that the model is runnable on day one, and they are always labelled
``status="assumption"`` in API responses.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal

ArchetypeKey = Literal[
    "membership", "dine_in", "takeaway", "retail", "appointment", "lodging"
]


@dataclass(frozen=True)
class Param:
    value: float
    low: float
    high: float
    unit: str
    description: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["status"] = "assumption"
        return d


@dataclass(frozen=True)
class Segment:
    key: str
    label: str
    share: float  # share of in-market population
    wtp_multiplier: float  # median willingness-to-pay relative to reference price
    price_sensitivity: float  # multiplier on beta_price
    distance_tolerance: float  # multiplier dividing the distance decay


@dataclass(frozen=True)
class InputField:
    key: str
    label: str
    unit: str
    default: float | None
    help: str
    kind: Literal["money", "count", "number", "percent"] = "number"


@dataclass(frozen=True)
class Archetype:
    key: ArchetypeKey
    label: str
    description: str
    unit_label: str  # what one sold unit is
    price_label: str
    period_note: str
    demand_base: Literal["residents", "residents_and_activity"]
    params: dict[str, Param]
    segments: tuple[Segment, ...]
    capacity_fields: tuple[InputField, ...]
    default_catchment_km: float
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def capacity_units(self, inputs: dict) -> float:
        """Monthly capacity in model units, from archetype-specific inputs."""
        g = lambda k, d=0.0: float(inputs.get(k) if inputs.get(k) is not None else d)  # noqa: E731
        if self.key == "membership":
            return g("max_members", 300)
        if self.key == "dine_in":
            return g("seats", 30) * g("turns_per_day", 3) * g("open_days_per_month", 30)
        if self.key == "takeaway":
            return g("max_orders_per_day", 150) * g("open_days_per_month", 30)
        if self.key == "retail":
            return g("max_baskets_per_day", 300) * g("open_days_per_month", 30)
        if self.key == "appointment":
            return g("stations", 3) * g("slots_per_station_per_day", 8) * g("open_days_per_month", 26)
        if self.key == "lodging":
            return g("rooms", 20) * 30.0
        raise ValueError(self.key)

    def to_public(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "unit_label": self.unit_label,
            "price_label": self.price_label,
            "period_note": self.period_note,
            "demand_base": self.demand_base,
            "params": {k: v.as_dict() for k, v in self.params.items()},
            "segments": [asdict(s) for s in self.segments],
            "capacity_fields": [asdict(f) for f in self.capacity_fields],
            "default_catchment_km": self.default_catchment_km,
            "limitations": list(self.limitations),
        }


def _common(**over: Param) -> dict[str, Param]:
    base = {
        "beta_price": Param(1.0, 0.5, 1.8, "utility per log-price ratio", "How strongly customers avoid prices above the local reference price."),
        "beta_quality": Param(2.0, 1.0, 3.0, "utility per quality point", "Weight of perceived quality/attractiveness (0-1 scale)."),
        "outside_utility": Param(0.0, -0.5, 0.5, "utility", "Attractiveness of NOT buying from any modeled business (going elsewhere, doing without)."),
        "wtp_sigma": Param(0.45, 0.3, 0.7, "log-sd", "Spread of willingness-to-pay around each segment's median."),
        "awareness_base": Param(0.25, 0.1, 0.4, "share", "Share of in-market people aware of a NEW business with zero marketing."),
        "marketing_half_saturation": Param(25000, 10000, 60000, "currency / month", "Monthly marketing spend that closes half the remaining awareness gap."),
        "circuity": Param(1.3, 1.15, 1.5, "ratio", "Road distance / straight-line distance. Used only when no routing engine result is available."),
        "competitor_quality": Param(0.5, 0.35, 0.65, "0-1", "Assumed quality of competitors whose quality is unknown."),
        "competitor_price_ratio": Param(1.0, 0.8, 1.25, "x reference", "Assumed competitor price relative to the reference price when unknown."),
        "variable_cost_ratio": Param(0.3, 0.2, 0.45, "share of price", "Variable cost per unit as a share of price, used only when the user gives none."),
    }
    base.update(over)
    return base


_SEG_STD = (
    Segment("budget", "Budget-conscious", 0.45, 0.75, 1.4, 0.8),
    Segment("mainstream", "Mainstream", 0.40, 1.05, 1.0, 1.0),
    Segment("premium", "Premium-seeking", 0.15, 1.7, 0.6, 1.3),
)

OPEN_DAYS = InputField("open_days_per_month", "Open days per month", "days", 30, "Days the business operates in a typical month.", "count")

ARCHETYPES: dict[str, Archetype] = {
    "membership": Archetype(
        key="membership",
        label="Membership / subscription",
        description="Customers pay a recurring monthly fee (gyms, coaching centres, studios, co-working).",
        unit_label="active members",
        price_label="Monthly membership fee",
        period_note="Units are active memberships in a steady month.",
        demand_base="residents",
        params=_common(
            participation=Param(0.04, 0.02, 0.07, "share of residents", "Share of catchment residents who hold a membership in this category at all."),
            frequency=Param(1.0, 1.0, 1.0, "per month", "One membership per member per month."),
            distance_decay=Param(0.55, 0.35, 0.8, "per km", "Utility lost per km of travel."),
            max_km=Param(4.0, 3.0, 6.0, "km", "Beyond this distance a zone does not consider the business."),
            variable_cost_ratio=Param(0.1, 0.05, 0.2, "share of price", "Per-member consumables, payment fees, wear as share of fee."),
        ),
        segments=_SEG_STD,
        capacity_fields=(
            InputField("max_members", "Maximum active members", "members", 300, "Members you can serve without overcrowding.", "count"),
        ),
        default_catchment_km=3.0,
        limitations=("Churn/retention is not modeled month to month; results describe a steady state.",),
    ),
    "dine_in": Archetype(
        key="dine_in",
        label="Dine-in food & drink",
        description="Customers visit and spend an average ticket per visit (cafés, restaurants, bars).",
        unit_label="visits",
        price_label="Average spend per visit",
        period_note="Units are customer visits (tickets) per month.",
        demand_base="residents_and_activity",
        params=_common(
            participation=Param(0.30, 0.15, 0.45, "share of residents", "Share of residents who visit this category in a given month."),
            frequency=Param(3.0, 1.5, 5.0, "visits per month", "Visits per in-market person per month."),
            distance_decay=Param(0.9, 0.6, 1.3, "per km", "Utility lost per km of travel."),
            max_km=Param(3.0, 2.0, 4.0, "km", "Consideration radius."),
            variable_cost_ratio=Param(0.38, 0.28, 0.5, "share of price", "Food & consumables cost as share of ticket."),
        ),
        segments=_SEG_STD,
        capacity_fields=(
            InputField("seats", "Seats", "seats", 30, "Seating capacity.", "count"),
            InputField("turns_per_day", "Table turns per seat per day", "turns", 3, "How many times a seat is used per day.", "number"),
            OPEN_DAYS,
        ),
        default_catchment_km=2.0,
    ),
    "takeaway": Archetype(
        key="takeaway",
        label="Takeaway & delivery",
        description="Orders picked up or delivered (pizza outlets, cloud kitchens, bakeries, QSR).",
        unit_label="orders",
        price_label="Average order value",
        period_note="Units are orders per month, including delivery.",
        demand_base="residents_and_activity",
        params=_common(
            participation=Param(0.25, 0.12, 0.4, "share of residents", "Share of residents ordering from this category in a month."),
            frequency=Param(2.5, 1.2, 4.0, "orders per month", "Orders per in-market person per month."),
            distance_decay=Param(0.6, 0.4, 0.9, "per km", "Utility lost per km (delivery makes this weaker)."),
            max_km=Param(5.0, 3.5, 7.0, "km", "Delivery / consideration radius."),
            variable_cost_ratio=Param(0.42, 0.3, 0.55, "share of price", "Ingredients, packaging and delivery cost as share of order value."),
        ),
        segments=_SEG_STD,
        capacity_fields=(
            InputField("max_orders_per_day", "Max orders per day", "orders", 150, "Kitchen throughput per day.", "count"),
            OPEN_DAYS,
        ),
        default_catchment_km=3.5,
        limitations=("Aggregator commissions should be included in variable cost if you sell via delivery apps.",),
    ),
    "retail": Archetype(
        key="retail",
        label="Retail store",
        description="Customers buy baskets of goods (pharmacies, grocery, apparel, electronics, books).",
        unit_label="baskets",
        price_label="Average basket value",
        period_note="Units are purchase transactions per month.",
        demand_base="residents_and_activity",
        params=_common(
            participation=Param(0.35, 0.15, 0.6, "share of residents", "Share of residents buying this category in a month."),
            frequency=Param(2.0, 1.0, 4.0, "baskets per month", "Purchases per in-market person per month."),
            distance_decay=Param(1.0, 0.6, 1.5, "per km", "Utility lost per km of travel."),
            max_km=Param(2.5, 1.5, 4.0, "km", "Consideration radius."),
            variable_cost_ratio=Param(0.7, 0.55, 0.82, "share of price", "Cost of goods sold as share of basket value."),
        ),
        segments=_SEG_STD,
        capacity_fields=(
            InputField("max_baskets_per_day", "Max transactions per day", "baskets", 300, "Checkout / staff throughput.", "count"),
            OPEN_DAYS,
        ),
        default_catchment_km=2.0,
    ),
    "appointment": Archetype(
        key="appointment",
        label="Appointment-based service",
        description="Customers book time slots (salons, clinics, dentists, spas, repair shops).",
        unit_label="appointments",
        price_label="Average price per appointment",
        period_note="Units are completed appointments per month.",
        demand_base="residents",
        params=_common(
            participation=Param(0.15, 0.07, 0.25, "share of residents", "Share of residents using this service in a month."),
            frequency=Param(1.2, 0.8, 2.0, "appointments per month", "Appointments per in-market person per month."),
            distance_decay=Param(0.7, 0.45, 1.0, "per km", "Utility lost per km of travel."),
            max_km=Param(4.0, 2.5, 6.0, "km", "Consideration radius."),
            variable_cost_ratio=Param(0.2, 0.1, 0.35, "share of price", "Consumables per appointment as share of price."),
        ),
        segments=_SEG_STD,
        capacity_fields=(
            InputField("stations", "Chairs / rooms / stations", "stations", 3, "Parallel service points.", "count"),
            InputField("slots_per_station_per_day", "Slots per station per day", "slots", 8, "Appointments one station handles per day.", "count"),
            InputField("open_days_per_month", "Open days per month", "days", 26, "Operating days per month.", "count"),
        ),
        default_catchment_km=3.0,
    ),
    "lodging": Archetype(
        key="lodging",
        label="Lodging",
        description="Guests book room-nights (hotels, guest houses, hostels).",
        unit_label="room-nights",
        price_label="Average room rate per night",
        period_note="Units are room-nights sold per month.",
        demand_base="residents_and_activity",
        params=_common(
            participation=Param(0.004, 0.001, 0.01, "room-nights per resident-equivalent", "Visitor room-nights generated per resident-equivalent of local activity per month. Very uncertain."),
            frequency=Param(1.0, 1.0, 1.0, "per month", "Folded into participation."),
            distance_decay=Param(0.35, 0.2, 0.6, "per km", "Guests compare hotels across a wide area."),
            max_km=Param(6.0, 4.0, 10.0, "km", "Comparison radius."),
            variable_cost_ratio=Param(0.25, 0.15, 0.35, "share of price", "Housekeeping, laundry, OTA commission."),
        ),
        segments=_SEG_STD,
        capacity_fields=(InputField("rooms", "Rooms", "rooms", 20, "Number of rentable rooms.", "count"),),
        default_catchment_km=5.0,
        limitations=(
            "Lodging demand comes mostly from visitors, not residents. This model uses residents plus nearby activity points (stations, offices, attractions, hospitals) only as a proxy; treat results as highly uncertain and verify with local occupancy data.",
        ),
    ),
}


def get_archetype(key: str) -> Archetype:
    try:
        return ARCHETYPES[key]
    except KeyError as e:
        raise ValueError(f"Unknown archetype '{key}'") from e
