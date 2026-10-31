"""Factor Intelligence registry: 615 factor definitions across 10 domains.

Every factor declares:
* ``scope``  — what it describes (zone, agent, business, competitor, market)
* ``source`` — where a value can come from (osm, worldpop, derived, user, assumption, simulated)
* ``role``   — how StrataIQ uses it:
    - ``agent``    sampled into every synthetic agent's profile and used in its decisions
    - ``choice``   enters the utility / choice model directly
    - ``finance``  enters the economics
    - ``output``   produced by the simulation
    - ``context``  computed and shown as evidence (not yet a model input)
    - ``reserved`` defined for future data; reported as not available rather than invented

A definition is not a value. Values are attached per location and per run by
``factors/compute.py``, which marks each one as computed / assumed / user / simulated /
unavailable. Nothing is filled with invented data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .evidence_map import EVIDENCE_STATUS_MAP

DOMAINS = {
    "geography": "Geography & built environment",
    "demographics": "Demographics",
    "economics": "Economics & affordability",
    "behavior": "Customer behaviour & preferences",
    "mobility": "Mobility & accessibility",
    "competition": "Competition",
    "operations": "Business operations",
    "marketing": "Marketing & awareness",
    "retention": "Retention & loyalty",
    "external": "External market conditions",
}


@dataclass(frozen=True)
class Factor:
    key: str
    label: str
    domain: str
    group: str
    unit: str
    scope: str
    source: str
    role: str
    description: str
    evidence_status: str = "UNSUPPORTED"

    def as_dict(self) -> dict:
        return asdict(self)


_F: list[Factor] = []


def f(key, label, domain, group, unit, scope, source, role, description=""):
    status = EVIDENCE_STATUS_MAP.get(key, "UNSUPPORTED")
    _F.append(Factor(key, label, domain, group, unit, scope, source, role, description or label, status))


# ------------------------------------------------------------------ geography (70)
POI_TYPES = [
    ("school", "Schools"), ("college", "Colleges"), ("university", "Universities"), ("hospital", "Hospitals"),
    ("clinic", "Clinics & doctors"), ("pharmacy", "Pharmacies"), ("bank", "Banks"), ("atm", "ATMs"),
    ("bus_stop", "Bus stops"), ("rail_station", "Rail / metro stations"), ("parking", "Parking"),
    ("place_of_worship", "Places of worship"), ("park", "Parks"), ("playground", "Playgrounds"),
    ("marketplace", "Marketplaces"), ("mall", "Malls"), ("supermarket", "Supermarkets"), ("convenience", "Convenience stores"),
    ("restaurant", "Restaurants"), ("cafe", "Cafés"), ("fast_food", "Fast-food outlets"), ("gym", "Gyms"),
    ("office", "Offices"), ("cinema", "Cinemas"), ("hotel", "Hotels"), ("fuel", "Fuel stations"),
    ("police", "Police stations"), ("post_office", "Post offices"), ("library", "Libraries"), ("coworking", "Co-working spaces"),
]
for k, lbl in POI_TYPES:
    f(f"geo_{k}_count_1km", f"{lbl} within 1 km of site", "geography", "Points of interest", "count", "market", "osm", "context")
    f(f"geo_{k}_nearest_km", f"Distance from site to nearest {lbl.lower().rstrip('s')}", "geography", "Points of interest", "km", "market", "osm", "context")
for k, lbl, unit, src, role in [
    ("building_count", "Mapped buildings in catchment", "count", "osm", "context"),
    ("building_density", "Mapped building density", "per km²", "derived", "context"),
    ("catchment_area", "Catchment area", "km²", "derived", "context"),
    ("catchment_radius", "Effective catchment radius", "km", "derived", "choice"),
    ("zone_count", "Demand zones", "count", "derived", "context"),
    ("zone_spacing", "Demand-zone spacing", "km", "derived", "context"),
    ("poi_density", "Point-of-interest density", "per km²", "derived", "context"),
    ("commercial_mix", "Share of commercial POIs (food, retail, office)", "share", "derived", "context"),
    ("civic_mix", "Share of civic POIs (education, health, worship)", "share", "derived", "context"),
    ("activity_points", "Activity points used as visitor-demand proxy", "count", "osm", "choice"),
]:
    f(f"geo_{k}", lbl, "geography", "Built environment", unit, "market", src, role)

for k, lbl, unit in [("zone_pop_p10", "Zone population, 10th percentile", "people"), ("zone_pop_p50", "Zone population, median", "people"),
                     ("zone_pop_p90", "Zone population, 90th percentile", "people"), ("zones_populated_share", "Share of zones with residents", "share"),
                     ("buildings_1km", "Mapped buildings within 1 km of site", "count"), ("buildings_2km", "Mapped buildings within 2 km of site", "count")]:
    f(f"geo_{k}", lbl, "geography", "Built environment", unit, "market", "derived", "context")

# ------------------------------------------------------------------ demographics (60)
AGE_BANDS = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70-74", "75-79", "80+"]
for b in AGE_BANDS:
    f(f"dem_age_{b.replace('-', '_').replace('+', 'plus')}_male", f"Male population aged {b} (share)", "demographics", "Age–sex structure", "share", "market", "worldpop", "agent")
    f(f"dem_age_{b.replace('-', '_').replace('+', 'plus')}_female", f"Female population aged {b} (share)", "demographics", "Age–sex structure", "share", "market", "worldpop", "agent")
for k, lbl, unit, src, role in [
    ("population", "Catchment population", "people", "worldpop", "choice"),
    ("density", "Population density", "people/km²", "derived", "context"),
    ("sex_ratio", "Males per 100 females", "ratio", "worldpop", "context"),
    ("median_age", "Median age", "years", "derived", "context"),
    ("youth_share", "Share aged 15–29", "share", "derived", "agent"),
    ("working_age_share", "Share aged 15–64", "share", "derived", "context"),
    ("elderly_share", "Share aged 65+", "share", "derived", "context"),
    ("child_share", "Share aged 0–14", "share", "derived", "context"),
    ("dependency_ratio", "Dependency ratio", "ratio", "derived", "context"),
    ("household_size", "Average household size", "people", "assumption", "context"),
    ("households", "Estimated households", "households", "derived", "context"),
    ("pop_peak_zone", "Population in densest zone", "people", "derived", "context"),
    ("pop_concentration", "Share of population in top 20% of zones", "share", "derived", "context"),
    ("agent_mean_age", "Mean age of synthetic agents", "years", "simulated", "output"),
    ("agent_female_share", "Female share of synthetic agents", "share", "simulated", "output"),
    ("student_share", "Student share", "share", "reserved", "reserved"),
    ("migrant_share", "Recent-migrant share", "share", "reserved", "reserved"),
    ("literacy_rate", "Literacy rate", "share", "reserved", "reserved"),
    ("language_mix", "Language mix", "index", "reserved", "reserved"),
    ("population_growth", "Population growth rate", "%/yr", "reserved", "reserved"),
    ("daytime_population", "Daytime (worker) population", "people", "reserved", "reserved"),
    ("nighttime_population", "Night-time (resident) population", "people", "worldpop", "context"),
    ("agents_n", "Synthetic agents simulated", "agents", "simulated", "output"),
    ("agent_scale", "Residents represented per agent", "people/agent", "simulated", "output"),
    ("in_market_agents", "Agents in market for this category", "agents", "simulated", "output"),
    ("age_profile_source", "Age profile source (WorldPop vs default)", "flag", "derived", "context"),
]:
    f(f"dem_{k}", lbl, "demographics", "Population", unit, "market", src, role)

# ------------------------------------------------------------------ economics (55)
for s in ("budget", "mainstream", "premium"):
    f(f"eco_{s}_share", f"{s.title()} segment share", "economics", "Segments", "share", "market", "assumption", "agent")
    f(f"eco_{s}_wtp_mult", f"{s.title()} segment willingness-to-pay multiplier", "economics", "Segments", "× ref price", "market", "assumption", "agent")
    f(f"eco_{s}_price_sens", f"{s.title()} segment price-sensitivity multiplier", "economics", "Segments", "×", "market", "assumption", "agent")
    f(f"eco_{s}_affordability", f"{s.title()} segment affordability at your price", "economics", "Segments", "share", "market", "simulated", "output")
    f(f"eco_{s}_distance_tol", f"{s.title()} segment distance tolerance", "economics", "Segments", "×", "market", "assumption", "agent")
for k, lbl, unit, src, role in [
    ("reference_price", "Local reference price", "₹", "user", "choice"),
    ("own_price", "Your price", "₹", "user", "choice"),
    ("price_index", "Your price ÷ reference price", "ratio", "derived", "choice"),
    ("competitor_price_ratio", "Assumed competitor price ratio", "×", "assumption", "choice"),
    ("known_price_share", "Share of competitors with a known price", "share", "derived", "context"),
    ("competitor_price_median", "Median recorded competitor price", "₹", "user", "choice"),
    ("competitor_price_min", "Lowest recorded competitor price", "₹", "user", "context"),
    ("competitor_price_max", "Highest recorded competitor price", "₹", "user", "context"),
    ("wtp_sigma", "Willingness-to-pay dispersion", "log-sd", "assumption", "agent"),
    ("agent_wtp_median", "Median agent willingness to pay", "₹", "simulated", "output"),
    ("agent_wtp_p10", "10th percentile agent willingness to pay", "₹", "simulated", "output"),
    ("agent_wtp_p90", "90th percentile agent willingness to pay", "₹", "simulated", "output"),
    ("afford_share", "Share of in-market agents who can afford your price", "share", "simulated", "output"),
    ("revenue_per_capita", "Your revenue per catchment resident", "₹/person", "simulated", "output"),
    ("market_value", "Modeled monthly category spend in catchment", "₹", "simulated", "output"),
    ("your_value_share", "Your share of category spend", "share", "simulated", "output"),
    ("unit_margin", "Unit contribution margin", "₹", "derived", "finance"),
    ("variable_cost_ratio", "Variable cost ratio", "share", "assumption", "finance"),
    ("income_tier_low", "Low-income agent share", "share", "simulated", "output"),
    ("income_tier_mid", "Middle-income agent share", "share", "simulated", "output"),
    ("income_tier_high", "High-income agent share", "share", "simulated", "output"),
    ("price_elasticity_est", "Arc price elasticity from sweep", "elasticity", "simulated", "output"),
    ("profit_max_price", "Price that maximises modeled profit", "₹", "simulated", "output"),
    ("household_income", "Median household income", "₹/month", "reserved", "reserved"),
    ("consumer_spend_category", "Household spend on this category", "₹/month", "reserved", "reserved"),
    ("land_value", "Commercial land / rent benchmark", "₹/sq ft", "reserved", "reserved"),
    ("credit_access", "Access to formal credit", "index", "reserved", "reserved"),
    ("gst_rate", "GST rate applicable", "%", "reserved", "reserved"),
    ("cpi_local", "Local consumer price index", "index", "reserved", "reserved"),
    ("upi_adoption", "Digital payment adoption", "share", "reserved", "reserved"),
    ("informal_share", "Informal-sector competition share", "share", "reserved", "reserved"),
    ("rent_benchmark", "Rent per sq ft benchmark", "₹", "reserved", "reserved"),
    ("wage_benchmark", "Staff wage benchmark", "₹/month", "reserved", "reserved"),
    ("electricity_tariff", "Commercial electricity tariff", "₹/kWh", "reserved", "reserved"),
    ("discount_depth", "Typical local discount depth", "share", "reserved", "reserved"),
    ("price_anchor_premium", "Premium-anchor price in market", "₹", "reserved", "reserved"),
    ("spend_seasonality", "Spend seasonality amplitude", "share", "reserved", "reserved"),
    ("savings_rate", "Household savings rate", "share", "reserved", "reserved"),
    ("asset_ownership", "Two-wheeler / car ownership", "share", "reserved", "reserved"),
    ("affordability_gap", "Gap between your price and median WTP", "₹", "simulated", "output"),
]:
    f(f"eco_{k}", lbl, "economics", "Prices & affordability", unit, "market", src, role)

# ------------------------------------------------------------------ behaviour (80)
for k, lbl, unit, src, role in [
    ("participation", "Share of residents in this market", "share", "assumption", "agent"),
    ("frequency", "Purchase frequency", "per month", "assumption", "agent"),
    ("beta_price", "Price sensitivity (β price)", "utility", "assumption", "choice"),
    ("beta_quality", "Quality sensitivity (β quality)", "utility", "assumption", "choice"),
    ("outside_utility", "Pull of options outside the model", "utility", "assumption", "choice"),
    ("agent_price_sens", "Agent price sensitivity", "×", "simulated", "agent"),
    ("agent_quality_sens", "Agent quality sensitivity", "×", "simulated", "agent"),
    ("agent_convenience", "Agent convenience preference", "0-1", "simulated", "agent"),
    ("agent_novelty", "Agent novelty seeking", "0-1", "simulated", "agent"),
    ("agent_social", "Agent susceptibility to word of mouth", "0-1", "simulated", "agent"),
    ("agent_digital", "Agent digital adoption", "0-1", "simulated", "agent"),
    ("agent_loyalty", "Agent loyalty propensity", "0-1", "simulated", "agent"),
    ("agent_time_pref", "Agent preferred time of day", "category", "simulated", "agent"),
    ("agent_category_affinity", "Agent affinity for this category (age-based)", "×", "assumption", "agent"),
    ("agent_wtp", "Agent willingness to pay", "₹", "simulated", "agent"),
    ("agent_frequency", "Agent purchase frequency", "per month", "simulated", "agent"),
    ("agent_in_market", "Agent is in market", "flag", "simulated", "agent"),
    ("agent_segment", "Agent segment", "category", "simulated", "agent"),
    ("agent_income_tier", "Agent income tier", "category", "simulated", "agent"),
    ("agent_age", "Agent age", "years", "simulated", "agent"),
    ("agent_sex", "Agent sex", "category", "simulated", "agent"),
    ("agent_home_zone", "Agent home zone", "zone", "simulated", "agent"),
    ("noise_scale", "Taste-noise scale (Gumbel)", "utility", "assumption", "choice"),
    ("habit_bonus", "Utility bonus for last-used business (habit)", "utility", "assumption", "choice"),
    ("trial_bias", "New-business trial bias", "utility", "assumption", "choice"),
    ("morning_share", "Share preferring mornings", "share", "assumption", "agent"),
    ("evening_share", "Share preferring evenings", "share", "assumption", "agent"),
    ("night_share", "Share preferring late hours", "share", "assumption", "agent"),
    ("weekend_uplift", "Weekend demand uplift", "×", "assumption", "agent"),
    ("affinity_young", "Category affinity, ages 15–29", "×", "assumption", "agent"),
    ("affinity_mid", "Category affinity, ages 30–49", "×", "assumption", "agent"),
    ("affinity_senior", "Category affinity, ages 50+", "×", "assumption", "agent"),
    ("affinity_child", "Category affinity, ages 0–14", "×", "assumption", "agent"),
    ("female_affinity", "Relative affinity, female agents", "×", "assumption", "agent"),
    ("choice_share_you", "Share of purchases choosing you", "share", "simulated", "output"),
    ("choice_share_outside", "Share of decisions choosing none", "share", "simulated", "output"),
    ("trial_rate", "Share of aware agents who tried you", "share", "simulated", "output"),
    ("repeat_rate", "Share of your customers who returned", "share", "simulated", "output"),
    ("switchers_in", "Agents who switched to you from a competitor", "agents", "simulated", "output"),
    ("switchers_out", "Agents who left you for a competitor", "agents", "simulated", "output"),
    ("mean_utility_you", "Mean utility of your offer (in-market agents)", "utility", "simulated", "output"),
    ("mean_utility_best_comp", "Mean utility of best competitor", "utility", "simulated", "output"),
    ("decision_events", "Purchase decisions simulated", "count", "simulated", "output"),
    ("review_reliance", "Reliance on online reviews", "0-1", "reserved", "reserved"),
    ("health_consciousness", "Health consciousness", "0-1", "reserved", "reserved"),
    ("dietary_preferences", "Dietary preferences mix", "index", "reserved", "reserved"),
    ("brand_consciousness", "Brand consciousness", "0-1", "reserved", "reserved"),
    ("group_purchase", "Group / family purchase share", "share", "reserved", "reserved"),
    ("impulse_share", "Impulse purchase share", "share", "reserved", "reserved"),
    ("delivery_preference", "Preference for delivery", "share", "reserved", "reserved"),
    ("cash_preference", "Cash payment preference", "share", "reserved", "reserved"),
    ("hygiene_sensitivity", "Hygiene sensitivity", "0-1", "reserved", "reserved"),
    ("ambience_sensitivity", "Ambience sensitivity", "0-1", "reserved", "reserved"),
    ("wait_tolerance", "Tolerance for waiting", "minutes", "reserved", "reserved"),
    ("trust_new_brands", "Trust in new brands", "0-1", "reserved", "reserved"),
    ("festival_spending", "Festival-season spending lift", "×", "reserved", "reserved"),
    ("subscription_aversion", "Aversion to subscriptions", "0-1", "reserved", "reserved"),
    ("personal_trainer_demand", "Demand for premium add-ons", "share", "reserved", "reserved"),
    ("family_decision", "Family-influenced decisions", "share", "reserved", "reserved"),
    ("peer_effect_radius", "Peer-effect radius", "km", "assumption", "agent"),
    ("referral_propensity", "Referral propensity", "0-1", "assumption", "agent"),
    ("complaint_propensity", "Complaint propensity", "0-1", "reserved", "reserved"),
    ("deal_seeking", "Deal seeking", "0-1", "reserved", "reserved"),
    ("quality_perception_lag", "Lag before quality is perceived", "days", "reserved", "reserved"),
    ("first_visit_anxiety", "First-visit hesitation", "0-1", "reserved", "reserved"),
    ("variety_seeking", "Variety seeking", "0-1", "reserved", "reserved"),
    ("environmental_concern", "Environmental concern", "0-1", "reserved", "reserved"),
    ("local_patriotism", "Preference for local businesses", "0-1", "reserved", "reserved"),
    ("online_substitution", "Substitution by online alternatives", "share", "reserved", "reserved"),
    ("time_poverty", "Time poverty", "0-1", "reserved", "reserved"),
    ("price_awareness", "Awareness of competitor prices", "0-1", "reserved", "reserved"),
    ("risk_aversion", "Risk aversion to new providers", "0-1", "reserved", "reserved"),
    ("social_visibility", "Social visibility of purchase", "0-1", "reserved", "reserved"),
    ("habit_formation_days", "Days to form a habit", "days", "reserved", "reserved"),
    ("seasonal_participation", "Seasonal participation swing", "share", "reserved", "reserved"),
    ("gender_norms_effect", "Gender-norm effects on participation", "×", "reserved", "reserved"),
    ("kids_influence", "Children's influence on choice", "0-1", "reserved", "reserved"),
    ("senior_access_needs", "Senior accessibility needs", "share", "reserved", "reserved"),
    ("language_preference", "Service-language preference", "category", "reserved", "reserved"),
]:
    f(f"beh_{k}", lbl, "behavior", "Behaviour", unit, "agent" if k.startswith("agent_") else "market", src, role)

for seg in ("budget", "mainstream", "premium"):
    f(f"beh_customers_{seg}_share", f"Your customers from the {seg} segment", "behavior", "Behaviour", "share", "business", "simulated", "output")

# ------------------------------------------------------------------ mobility (60)
MODES = [("walk", "Walking", 4.5), ("two_wheeler", "Two-wheeler", 18), ("car", "Car", 16), ("auto", "Auto-rickshaw", 14), ("bus", "Bus", 11), ("metro", "Metro / rail", 25), ("cycle", "Cycle", 10)]
for k, lbl, _ in MODES:
    f(f"mob_{k}_share", f"{lbl} mode share (agents)", "mobility", "Travel modes", "share", "market", "assumption", "agent")
    f(f"mob_{k}_speed", f"{lbl} effective urban speed", "mobility", "Travel modes", "km/h", "market", "assumption", "agent")
    f(f"mob_{k}_tolerance", f"{lbl} distance tolerance multiplier", "mobility", "Travel modes", "×", "market", "assumption", "agent")
for k, lbl, unit, src, role in [
    ("distance_decay", "Distance decay (λ)", "utility/km", "assumption", "choice"),
    ("max_km", "Consideration radius", "km", "assumption", "choice"),
    ("circuity", "Road circuity factor", "ratio", "assumption", "choice"),
    ("catchment_method", "Catchment method (radius / isochrone)", "flag", "derived", "context"),
    ("isochrone_minutes", "Travel-time catchment minutes", "min", "user", "context"),
    ("isochrone_profile", "Travel-time profile", "category", "user", "context"),
    ("agent_mode", "Agent travel mode", "category", "simulated", "agent"),
    ("agent_trip_km", "Agent distance to chosen business", "km", "simulated", "output"),
    ("mean_trip_km_you", "Mean customer trip distance to you", "km", "simulated", "output"),
    ("mean_trip_min_you", "Mean customer travel time to you", "min", "simulated", "output"),
    ("p90_trip_km_you", "90th percentile customer trip distance", "km", "simulated", "output"),
    ("share_within_1km", "Your customers living within 1 km", "share", "simulated", "output"),
    ("share_within_2km", "Your customers living within 2 km", "share", "simulated", "output"),
    ("bus_stops_500m", "Bus stops within 500 m of site", "count", "osm", "context"),
    ("rail_1500m", "Rail / metro stations within 1.5 km", "count", "osm", "context"),
    ("parking_500m", "Parking facilities within 500 m", "count", "osm", "context"),
    ("pop_within_1km", "Population within 1 km of site", "people", "derived", "context"),
    ("pop_within_2km", "Population within 2 km of site", "people", "derived", "context"),
    ("pop_within_3km", "Population within 3 km of site", "people", "derived", "context"),
    ("accessibility_index", "Population-weighted accessibility (Σ pop·e^(−λd))", "index", "derived", "context"),
    ("road_density", "Road network density", "km/km²", "reserved", "reserved"),
    ("traffic_congestion", "Peak-hour congestion", "index", "reserved", "reserved"),
    ("footfall_counts", "Observed footfall", "people/hour", "reserved", "reserved"),
    ("visibility_from_road", "Shop-front visibility", "0-1", "reserved", "reserved"),
    ("main_road_frontage", "Main-road frontage", "flag", "reserved", "reserved"),
    ("pedestrian_safety", "Pedestrian safety", "index", "reserved", "reserved"),
    ("flood_risk", "Waterlogging / flood risk", "index", "reserved", "reserved"),
    ("one_way_restrictions", "One-way / access restrictions", "flag", "reserved", "reserved"),
    ("commute_flows", "Commute flows through site", "trips/day", "reserved", "reserved"),
    ("ride_hailing_cost", "Ride-hailing cost to site", "₹", "reserved", "reserved"),
    ("walkability", "Walkability score", "index", "reserved", "reserved"),
    ("night_lighting", "Street lighting at night", "index", "reserved", "reserved"),
    ("delivery_radius", "Delivery radius", "km", "assumption", "choice"),
    ("travel_time_budget", "Agent travel-time budget", "min", "assumption", "agent"),
    ("metro_proximity_bonus", "Utility bonus near rail stations", "utility", "reserved", "reserved"),
    ("mobility_note", "Mobility data note", "text", "derived", "context"),
    ("elevation_change", "Terrain / elevation change", "m", "reserved", "reserved"),
    ("barrier_effects", "Rail / river / highway barriers", "index", "reserved", "reserved"),
    ("parking_cost", "Parking cost", "₹/hour", "reserved", "reserved"),
]:
    f(f"mob_{k}", lbl, "mobility", "Accessibility", unit, "market", src, role)

for k, lbl, _ in MODES:
    f(f"mob_{k}_customer_share", f"Your customers travelling by {lbl.lower()}", "mobility", "Travel modes", "share", "business", "simulated", "output")

# ------------------------------------------------------------------ competition (60)
for r in ("0_5", "1", "2", "3"):
    f(f"cmp_count_{r}km", f"Competitors within {r.replace('_', '.')} km", "competition", "Density", "count", "market", "osm", "context")
for k, lbl, unit, src, role in [
    ("count", "Competitors in model", "count", "osm", "choice"),
    ("user_added", "User-added competitors", "count", "user", "choice"),
    ("hypothetical", "Hypothetical competitors", "count", "user", "choice"),
    ("excluded", "Excluded competitors", "count", "user", "context"),
    ("density", "Competitor density", "per km²", "derived", "context"),
    ("per_10k_pop", "Competitors per 10,000 residents", "ratio", "derived", "context"),
    ("nearest_km", "Distance to nearest competitor", "km", "derived", "context"),
    ("mean_distance_km", "Mean distance to competitors", "km", "derived", "context"),
    ("named_share", "Share of competitor records with a name", "share", "osm", "context"),
    ("hours_known_share", "Share with opening hours", "share", "osm", "context"),
    ("branded_share", "Share that are branded / chains", "share", "osm", "context"),
    ("website_share", "Share with a website", "share", "osm", "context"),
    ("median_record_age_days", "Median days since record edited", "days", "osm", "context"),
    ("quality_assumed", "Assumed competitor quality", "0-1", "assumption", "choice"),
    ("quality_known_share", "Share with user-entered quality", "share", "user", "context"),
    ("hhi", "Market concentration (HHI of modeled shares)", "index", "simulated", "output"),
    ("top_share", "Largest competitor's modeled share", "share", "simulated", "output"),
    ("your_rank", "Your rank by modeled customers", "rank", "simulated", "output"),
    ("overlap_index", "Catchment overlap with competitors", "share", "simulated", "output"),
    ("captured_by_all", "In-market demand captured by modeled businesses", "share", "simulated", "output"),
    ("leakage", "Demand leaking outside the modeled set", "share", "simulated", "output"),
    ("cannibalisation", "Demand you take from competitors", "units", "simulated", "output"),
    ("price_gap", "Your price vs reference", "₹", "derived", "choice"),
    ("quality_gap", "Your quality vs assumed competitor quality", "0-1", "derived", "choice"),
    ("coverage_level", "Data coverage level", "category", "derived", "context"),
    ("buildings_per_1000", "Mapped buildings per 1,000 residents", "ratio", "derived", "context"),
    ("competitor_capacity", "Competitor capacity", "units", "reserved", "reserved"),
    ("competitor_ratings", "Competitor online ratings", "stars", "reserved", "reserved"),
    ("competitor_reviews", "Competitor review counts", "count", "reserved", "reserved"),
    ("competitor_age_years", "Competitor years in business", "years", "reserved", "reserved"),
    ("competitor_promotions", "Competitor active promotions", "flag", "reserved", "reserved"),
    ("competitor_footfall", "Competitor footfall", "people/day", "reserved", "reserved"),
    ("competitor_response", "Expected competitor price response", "×", "reserved", "reserved"),
    ("entry_barriers", "Entry barriers", "index", "reserved", "reserved"),
    ("informal_competitors", "Informal / unmapped competitors (estimate)", "count", "reserved", "reserved"),
    ("substitute_density", "Substitute businesses nearby", "count", "reserved", "reserved"),
    ("complementary_density", "Complementary businesses nearby", "count", "reserved", "reserved"),
    ("anchor_tenants", "Anchor tenants nearby", "count", "reserved", "reserved"),
    ("closures_recent", "Recent competitor closures", "count", "reserved", "reserved"),
    ("openings_recent", "Recent competitor openings", "count", "reserved", "reserved"),
    ("franchise_presence", "National franchise presence", "flag", "reserved", "reserved"),
    ("online_competitors", "Online / aggregator competitors", "count", "reserved", "reserved"),
    ("competitor_hours_overlap", "Opening-hours overlap", "share", "reserved", "reserved"),
    ("differentiation_claims", "Your claimed differentiators", "count", "user", "context"),
    ("agents_choosing_comp", "Agents choosing a competitor", "agents", "simulated", "output"),
    ("agents_choosing_none", "Agents choosing none", "agents", "simulated", "output"),
    ("strongest_competitor", "Competitor with most modeled customers", "name", "simulated", "output"),
    ("competitor_share_spread", "Spread of competitor shares", "share", "simulated", "output"),
    ("threat_index", "Competitive threat index", "0-1", "simulated", "output"),
    ("white_space_zones", "Zones with low competitor capture", "count", "simulated", "output"),
    ("price_known_count", "Competitors with known price", "count", "user", "context"),
    ("competitor_mix_note", "Competition data note", "text", "derived", "context"),
    ("demo_flag", "Competitors from demo data", "count", "derived", "context"),
    ("osm_tag_filters", "Search filters used", "count", "derived", "context"),
    ("search_method", "Category resolution method", "category", "derived", "context"),
    ("competitor_brand_list", "Brands present", "list", "osm", "context"),
]:
    f(f"cmp_{k}", lbl, "competition", "Competitive landscape", unit, "market", src, role)

# ------------------------------------------------------------------ operations (65)
for k, lbl, unit, src, role in [
    ("price", "Price", "₹", "user", "finance"),
    ("quality", "Attractiveness / quality claim", "0-1", "user", "choice"),
    ("capacity_units", "Monthly capacity", "units", "user", "finance"),
    ("max_members", "Maximum members", "members", "user", "finance"),
    ("seats", "Seats", "seats", "user", "finance"),
    ("turns_per_day", "Turns per seat per day", "turns", "user", "finance"),
    ("open_days", "Open days per month", "days", "user", "finance"),
    ("max_orders_day", "Max orders per day", "orders", "user", "finance"),
    ("max_baskets_day", "Max baskets per day", "baskets", "user", "finance"),
    ("stations", "Service stations", "count", "user", "finance"),
    ("slots_per_station", "Slots per station per day", "slots", "user", "finance"),
    ("rooms", "Rooms", "rooms", "user", "finance"),
    ("rent", "Rent", "₹/month", "user", "finance"),
    ("payroll", "Payroll", "₹/month", "user", "finance"),
    ("utilities", "Utilities", "₹/month", "user", "finance"),
    ("other_fixed", "Other fixed costs", "₹/month", "user", "finance"),
    ("variable_cost_unit", "Variable cost per unit", "₹", "user", "finance"),
    ("startup_cost", "Startup cost", "₹", "user", "finance"),
    ("fixed_cost_total", "Total fixed cost", "₹/month", "derived", "finance"),
    ("revenue", "Monthly revenue", "₹", "simulated", "output"),
    ("operating_profit", "Monthly operating profit", "₹", "simulated", "output"),
    ("break_even_units", "Break-even units", "units", "simulated", "output"),
    ("utilization", "Capacity utilisation", "share", "simulated", "output"),
    ("payback_months", "Payback period", "months", "simulated", "output"),
    ("prob_loss", "Modeled probability of loss", "share", "simulated", "output"),
    ("profit_p10", "Profit P10", "₹", "simulated", "output"),
    ("profit_p90", "Profit P90", "₹", "simulated", "output"),
    ("capacity_bound", "Capacity binds", "flag", "simulated", "output"),
    ("congestion_days", "Days at capacity (agent simulation)", "days", "simulated", "output"),
    ("rejected_demand", "Demand turned away at capacity", "units", "simulated", "output"),
    ("ramp_up_weeks", "Weeks to reach 80% of steady state", "weeks", "simulated", "output"),
    ("month1_units", "Units in month 1", "units", "simulated", "output"),
    ("month2_units", "Units in month 2", "units", "simulated", "output"),
    ("month3_units", "Units in month 3", "units", "simulated", "output"),
    ("cash_burn_ramp", "Cash burn during ramp-up", "₹", "simulated", "output"),
    ("operating_hours", "Operating hours", "text", "user", "context"),
    ("staff_count", "Staff count", "people", "reserved", "reserved"),
    ("staff_productivity", "Staff productivity", "units/hour", "reserved", "reserved"),
    ("equipment_quality", "Equipment quality", "0-1", "reserved", "reserved"),
    ("floor_area", "Floor area", "sq ft", "reserved", "reserved"),
    ("inventory_turns", "Inventory turns", "per year", "reserved", "reserved"),
    ("wastage_rate", "Wastage rate", "share", "reserved", "reserved"),
    ("supplier_lead_time", "Supplier lead time", "days", "reserved", "reserved"),
    ("licence_status", "Licences in place", "flag", "reserved", "reserved"),
    ("insurance_cost", "Insurance cost", "₹/month", "reserved", "reserved"),
    ("maintenance_cost", "Maintenance cost", "₹/month", "reserved", "reserved"),
    ("depreciation", "Depreciation", "₹/month", "reserved", "reserved"),
    ("loan_emi", "Loan EMI", "₹/month", "reserved", "reserved"),
    ("working_capital", "Working capital need", "₹", "reserved", "reserved"),
    ("security_deposit", "Security deposit", "₹", "reserved", "reserved"),
    ("power_backup", "Power backup", "flag", "reserved", "reserved"),
    ("accessibility_features", "Accessibility features", "flag", "reserved", "reserved"),
    ("service_time", "Average service time", "minutes", "reserved", "reserved"),
    ("queue_time", "Average queue time", "minutes", "reserved", "reserved"),
    ("menu_breadth", "Offer breadth", "items", "reserved", "reserved"),
    ("delivery_share", "Delivery share of sales", "share", "reserved", "reserved"),
    ("aggregator_commission", "Aggregator commission", "share", "reserved", "reserved"),
    ("owner_hours", "Owner hours per week", "hours", "reserved", "reserved"),
    ("tax_rate", "Effective tax rate", "share", "reserved", "reserved"),
    ("seasonal_staffing", "Seasonal staffing flexibility", "0-1", "reserved", "reserved"),
    ("objective", "Project objective", "category", "user", "context"),
    ("decision_goal", "Decision goal", "category", "user", "context"),
    ("archetype", "Business model type", "category", "derived", "choice"),
    ("category_label", "Category", "text", "user", "context"),
    ("model_version", "Model version", "text", "derived", "context"),
]:
    f(f"ops_{k}", lbl, "operations", "Operations & finance", unit, "business", src, role)

# ------------------------------------------------------------------ marketing (50)
CHANNELS = [("digital", "Digital ads"), ("social", "Social media"), ("print", "Flyers / print"), ("signage", "Signage / storefront"), ("wom", "Word of mouth"), ("referral", "Referral programme"), ("events", "Local events"), ("aggregator", "Aggregator listing")]
for k, lbl in CHANNELS:
    f(f"mkt_{k}_weight", f"{lbl}: share of awareness generation", "marketing", "Channels", "share", "business", "assumption", "agent")
    f(f"mkt_{k}_aware_agents", f"Agents made aware via {lbl.lower()}", "marketing", "Channels", "agents", "business", "simulated", "output")
for k, lbl, unit, src, role in [
    ("spend", "Marketing spend", "₹/month", "user", "agent"),
    ("awareness_base", "Baseline awareness of a new business", "share", "assumption", "agent"),
    ("half_saturation", "Spend for half the awareness gap", "₹", "assumption", "agent"),
    ("daily_reach", "Daily paid reach probability", "per day", "derived", "agent"),
    ("wom_rate", "Word-of-mouth transmission rate", "per day", "assumption", "agent"),
    ("signage_radius", "Signage awareness radius", "km", "assumption", "agent"),
    ("awareness_final", "Awareness after simulation", "share", "simulated", "output"),
    ("awareness_week4", "Awareness after 4 weeks", "share", "simulated", "output"),
    ("awareness_week8", "Awareness after 8 weeks", "share", "simulated", "output"),
    ("aware_to_trial", "Aware → tried conversion", "share", "simulated", "output"),
    ("cost_per_aware", "Marketing cost per aware agent", "₹", "simulated", "output"),
    ("cost_per_customer", "Marketing cost per acquired customer", "₹", "simulated", "output"),
    ("profit_max_spend", "Spend that maximises modeled profit", "₹", "simulated", "output"),
    ("launch_offer", "Launch offer", "flag", "reserved", "reserved"),
    ("brand_strength", "Brand strength", "0-1", "reserved", "reserved"),
    ("online_rating", "Your online rating", "stars", "reserved", "reserved"),
    ("search_visibility", "Search visibility", "index", "reserved", "reserved"),
    ("influencer_reach", "Influencer reach", "people", "reserved", "reserved"),
    ("loyalty_program", "Loyalty programme", "flag", "reserved", "reserved"),
    ("partnerships", "Local partnerships", "count", "reserved", "reserved"),
    ("ad_fatigue", "Ad fatigue rate", "per week", "reserved", "reserved"),
    ("seasonal_campaigns", "Seasonal campaign calendar", "count", "reserved", "reserved"),
    ("creative_quality", "Creative quality", "0-1", "reserved", "reserved"),
    ("targeting_precision", "Targeting precision", "0-1", "reserved", "reserved"),
    ("community_presence", "Community presence", "0-1", "reserved", "reserved"),
    ("google_listing", "Maps listing completeness", "0-1", "reserved", "reserved"),
    ("whatsapp_reach", "Messaging-group reach", "people", "reserved", "reserved"),
    ("pr_mentions", "Local media mentions", "count", "reserved", "reserved"),
    ("grand_opening", "Grand-opening event", "flag", "reserved", "reserved"),
    ("awareness_decay", "Awareness decay without marketing", "per week", "reserved", "reserved"),
    ("share_of_voice", "Share of local advertising voice", "share", "reserved", "reserved"),
    ("trial_incentive", "Trial incentive value", "₹", "reserved", "reserved"),
    ("mkt_note", "Marketing model note", "text", "derived", "context"),
    ("mkt_roi", "Modeled marketing ROI", "×", "simulated", "output"),
]:
    f(f"mkt_{k}", lbl, "marketing", "Awareness", unit, "business", src, role)

# ------------------------------------------------------------------ retention (45)
for k, lbl, unit, src, role in [
    ("monthly_churn", "Monthly churn (membership)", "share", "assumption", "agent"),
    ("loyalty_build", "Loyalty build per visit", "utility", "assumption", "agent"),
    ("loyalty_cap", "Maximum loyalty bonus", "utility", "assumption", "agent"),
    ("congestion_penalty", "Penalty after being turned away", "utility", "assumption", "agent"),
    ("congestion_memory_days", "Days a bad experience is remembered", "days", "assumption", "agent"),
    ("switch_threshold", "Utility gap needed to switch", "utility", "assumption", "agent"),
    ("reconsider_days", "Days between reconsidering (membership)", "days", "assumption", "agent"),
    ("retained_customers", "Customers retained at end", "agents", "simulated", "output"),
    ("churned_customers", "Customers who churned", "agents", "simulated", "output"),
    ("churn_observed", "Simulated churn rate", "share", "simulated", "output"),
    ("repeat_share", "Repeat purchases share", "share", "simulated", "output"),
    ("loyal_customers", "Customers with ≥3 purchases", "agents", "simulated", "output"),
    ("mean_purchases", "Mean purchases per customer", "count", "simulated", "output"),
    ("customer_lifetime_months", "Implied customer lifetime", "months", "simulated", "output"),
    ("clv", "Implied customer lifetime value", "₹", "simulated", "output"),
    ("cac_to_clv", "Acquisition cost ÷ lifetime value", "ratio", "simulated", "output"),
    ("turned_away", "Agents turned away at capacity", "agents", "simulated", "output"),
    ("satisfaction_proxy", "Satisfaction proxy (no congestion)", "share", "simulated", "output"),
    ("nps", "Net promoter score", "score", "reserved", "reserved"),
    ("complaints", "Complaints", "per month", "reserved", "reserved"),
    ("win_back_rate", "Win-back rate", "share", "reserved", "reserved"),
    ("membership_tenure", "Average membership tenure", "months", "reserved", "reserved"),
    ("upsell_rate", "Upsell rate", "share", "reserved", "reserved"),
    ("cross_sell_rate", "Cross-sell rate", "share", "reserved", "reserved"),
    ("service_recovery", "Service recovery rate", "share", "reserved", "reserved"),
    ("staff_turnover", "Staff turnover", "per year", "reserved", "reserved"),
    ("review_velocity", "New reviews per month", "count", "reserved", "reserved"),
    ("loyalty_redemption", "Loyalty redemption rate", "share", "reserved", "reserved"),
    ("family_plans", "Family / group plans", "flag", "reserved", "reserved"),
    ("freeze_options", "Membership freeze options", "flag", "reserved", "reserved"),
    ("contract_length", "Contract length", "months", "reserved", "reserved"),
    ("prepaid_share", "Prepaid plan share", "share", "reserved", "reserved"),
    ("attendance_rate", "Member attendance rate", "share", "reserved", "reserved"),
    ("community_events", "Community events per month", "count", "reserved", "reserved"),
    ("personalisation", "Personalisation level", "0-1", "reserved", "reserved"),
    ("feedback_loop", "Feedback collection", "flag", "reserved", "reserved"),
    ("dormant_share", "Dormant customer share", "share", "reserved", "reserved"),
    ("retention_note", "Retention model note", "text", "derived", "context"),
    ("first_month_retention", "Retention after first month", "share", "simulated", "output"),
    ("habit_strength_mean", "Mean habit strength of your customers", "utility", "simulated", "output"),
    ("loyalty_vs_price", "Loyalty bonus ÷ price disutility", "ratio", "simulated", "output"),
    ("customers_week12", "Active customers at week 12", "agents", "simulated", "output"),
    ("peak_customers", "Peak weekly customers", "agents", "simulated", "output"),
    ("stable_week", "Week demand stabilised", "week", "simulated", "output"),
    ("retention_curve_points", "Retention curve points", "count", "simulated", "output"),
]:
    f(f"ret_{k}", lbl, "retention", "Retention", unit, "business", src, role)

# ------------------------------------------------------------------ external (remaining to 615)
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
for m in MONTHS:
    f(f"ext_season_{m}", f"Seasonality index — {m.title()}", "external", "Seasonality", "×", "market", "reserved", "reserved")
for k, lbl, unit, src, role in [
    ("inflation", "Inflation rate", "%/yr", "reserved", "reserved"),
    ("rent_escalation", "Annual rent escalation", "%/yr", "reserved", "reserved"),
    ("wage_growth", "Wage growth", "%/yr", "reserved", "reserved"),
    ("fuel_price", "Fuel price index", "index", "reserved", "reserved"),
    ("festival_calendar", "Festival-season effect", "×", "reserved", "reserved"),
    ("monsoon_effect", "Monsoon effect on footfall", "×", "reserved", "reserved"),
    ("heatwave_effect", "Heatwave effect", "×", "reserved", "reserved"),
    ("exam_season", "Exam-season effect", "×", "reserved", "reserved"),
    ("new_infrastructure", "Upcoming infrastructure (metro, roads)", "flag", "reserved", "reserved"),
    ("zoning_change", "Zoning / regulation change", "flag", "reserved", "reserved"),
    ("licensing_difficulty", "Licensing difficulty", "index", "reserved", "reserved"),
    ("local_events", "Local events calendar", "count", "reserved", "reserved"),
    ("pandemic_risk", "Public-health disruption risk", "index", "reserved", "reserved"),
    ("interest_rate", "Business loan interest rate", "%/yr", "reserved", "reserved"),
    ("consumer_confidence", "Consumer confidence", "index", "reserved", "reserved"),
    ("employment_trend", "Local employment trend", "index", "reserved", "reserved"),
    ("real_estate_trend", "Real-estate development trend", "index", "reserved", "reserved"),
    ("competitor_entry_rate", "Competitor entry rate", "per year", "reserved", "reserved"),
    ("platform_policy", "Delivery-platform policy changes", "flag", "reserved", "reserved"),
    ("power_reliability", "Power reliability", "index", "reserved", "reserved"),
    ("water_supply", "Water supply reliability", "index", "reserved", "reserved"),
    ("crime_index", "Area safety index (aggregate)", "index", "reserved", "reserved"),
    ("air_quality", "Air quality", "AQI", "reserved", "reserved"),
    ("tourism_flow", "Tourism flow", "visitors/month", "reserved", "reserved"),
    ("student_calendar", "Academic calendar effect", "×", "reserved", "reserved"),
    ("simulation_horizon", "Simulated horizon", "days", "simulated", "context"),
    ("mc_draws", "Monte Carlo draws", "count", "derived", "context"),
    ("random_seed", "Random seed", "integer", "user", "context"),
    ("data_retrieved_at", "Market data retrieved at", "timestamp", "derived", "context"),
    ("osm_base_time", "OpenStreetMap database time", "timestamp", "osm", "context"),
    ("worldpop_year", "WorldPop reference year", "year", "worldpop", "context"),
    ("snapshot_status", "Market snapshot status", "category", "derived", "context"),
    ("provider_errors", "Provider errors in snapshot", "count", "derived", "context"),
    ("cache_hits", "Layers served from cache", "count", "derived", "context"),
    ("demo_mode", "Demo mode", "flag", "derived", "context"),
    ("validation_status", "Validation status", "text", "derived", "context"),
    ("actuals_recorded", "Months of actual outcomes recorded", "count", "user", "context"),
    ("district_gdp", "District GDP per capita", "₹", "reserved", "reserved"),
    ("urbanisation_rate", "Urbanisation rate", "share", "reserved", "reserved"),
    ("smartphone_penetration", "Smartphone penetration", "share", "reserved", "reserved"),
    ("festival_dates", "Festival dates in horizon", "count", "reserved", "reserved"),
    ("election_period", "Election / model-code period", "flag", "reserved", "reserved"),
    ("forecast_wape", "Forecast error (WAPE)", "share", "derived", "context"),
]:
    f(f"ext_{k}", lbl, "external", "Macro & context", unit, "market", src, role)

FACTORS: tuple[Factor, ...] = tuple(_F)
BY_KEY = {x.key: x for x in FACTORS}


def counts() -> dict:
    out = {"total": len(FACTORS), "by_domain": {}, "by_role": {}, "by_source": {}, "by_evidence_status": {}}
    for x in FACTORS:
        out["by_domain"][x.domain] = out["by_domain"].get(x.domain, 0) + 1
        out["by_role"][x.role] = out["by_role"].get(x.role, 0) + 1
        out["by_source"][x.source] = out["by_source"].get(x.source, 0) + 1
        out["by_evidence_status"][x.evidence_status] = out["by_evidence_status"].get(x.evidence_status, 0) + 1
    return out
