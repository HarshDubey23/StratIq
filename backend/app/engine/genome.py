"""Agent Genome: a 615-parameter profile for every synthetic agent.

Each synthetic agent carries exactly ``GENOME_SIZE`` (615) parameters. They are
produced in three ways, and every parameter records which:

* ``evidence``  - computed from real local evidence (position drawn from
  WorldPop/OSM population density, distance and travel time to every mapped
  business, competitor rings). These are facts about the *synthetic* agent's
  placement, derived from real geography.
* ``latent``    - 16 correlated latent traits (income, price consciousness,
  time poverty, ...). Drawn from a documented correlation matrix and
  *conditioned* on the agent's age and income segment (conditional Gaussian).
* ``generated`` - the remaining parameters, each a documented function of the
  latent traits and observed covariates plus idiosyncratic noise:
  ``x = mu + loadings . z + sd * eps`` then a bounded transform.

Every parameter has a ``mechanism`` that says how it enters the simulation:
``utility`` (a term of the random-utility choice), ``price``, ``travel``,
``time_fit``, ``expectation`` (penalty when a business falls below what the
agent expects), ``participation`` (being in the market at all), ``outside``
(attractiveness of buying nothing / a substitute), ``awareness``, ``social``
(word of mouth), ``retention`` (habit, churn, switching), ``noise`` (choice
randomness), or ``placement``. No parameter is decorative.

All values are SYNTHETIC. Distributions and loadings are modelling assumptions,
not measurements of real people. See docs/GENOME.md.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

GENOME_SIZE = 615

# ---------------------------------------------------------------- latent structure
LATENTS = [
    ("income", "Income / purchasing power"), ("price_consc", "Price consciousness"), ("quality_orient", "Quality orientation"),
    ("convenience", "Convenience orientation"), ("novelty", "Novelty seeking"), ("social", "Social connectedness"),
    ("digital", "Digital nativity"), ("health", "Health & wellness orientation"), ("status", "Status orientation"),
    ("time_poverty", "Time poverty"), ("habit", "Habit strength"), ("risk_aversion", "Risk aversion"),
    ("family_load", "Family / care load"), ("mobility", "Personal mobility"), ("locality", "Neighbourhood attachment"),
    ("planning", "Planning orientation"),
]
LAT = {k: i for i, (k, _) in enumerate(LATENTS)}
NL = len(LATENTS)
# extra observed covariates appended after latents in the design matrix
COVS = ["age", "female", "density"]
COLS = [k for k, _ in LATENTS] + COVS + ["age_obs"]
CI = {k: i for i, k in enumerate(COLS)}

# Correlations among latent traits and the observed age z-score (assumptions, documented).
_PAIRS = {
    ("income", "price_consc"): -0.50, ("income", "status"): 0.45, ("income", "quality_orient"): 0.35, ("income", "mobility"): 0.40,
    ("income", "digital"): 0.20, ("income", "planning"): 0.15, ("age_obs", "digital"): -0.50, ("age_obs", "novelty"): -0.35,
    ("age_obs", "habit"): 0.30, ("age_obs", "risk_aversion"): 0.30, ("age_obs", "family_load"): 0.30, ("age_obs", "mobility"): -0.20,
    ("age_obs", "health"): 0.10, ("age_obs", "locality"): 0.25, ("family_load", "time_poverty"): 0.40, ("time_poverty", "convenience"): 0.50,
    ("social", "novelty"): 0.25, ("social", "digital"): 0.30, ("status", "quality_orient"): 0.40, ("status", "novelty"): 0.20,
    ("price_consc", "habit"): 0.15, ("risk_aversion", "habit"): 0.35, ("risk_aversion", "novelty"): -0.40, ("locality", "habit"): 0.30,
    ("locality", "mobility"): -0.25, ("planning", "risk_aversion"): 0.25, ("health", "quality_orient"): 0.20, ("convenience", "mobility"): -0.10,
    ("income", "time_poverty"): 0.15, ("digital", "novelty"): 0.25, ("price_consc", "planning"): 0.20, ("social", "status"): 0.15,
}
_SEG_INCOME = {"budget": -0.85, "mainstream": 0.15, "premium": 1.25}


def _corr() -> np.ndarray:
    keys = [k for k, _ in LATENTS] + ["age_obs", "income_obs"]
    idx = {k: i for i, k in enumerate(keys)}
    R = np.eye(len(keys))
    for (a, b), r in _PAIRS.items():
        R[idx[a], idx[b]] = R[idx[b], idx[a]] = r
    # income_obs is the segment-implied income signal: strongly tied to latent income
    R[idx["income"], idx["income_obs"]] = R[idx["income_obs"], idx["income"]] = 0.8
    w, v = np.linalg.eigh(R)
    w = np.clip(w, 0.05, None)
    R = v @ np.diag(w) @ v.T
    d = np.sqrt(np.diag(R))
    return R / d[:, None] / d[None, :]


CORR = _corr()

# ---------------------------------------------------------------- business feature space
ATTRS = [
    ("cleanliness", "Cleanliness"), ("staff", "Staff friendliness"), ("wait", "Short waiting time"), ("parking", "Parking availability"),
    ("ac", "Air conditioning / climate"), ("ambience", "Ambience & décor"), ("hygiene", "Hygiene standards"), ("brand", "Brand reputation"),
    ("variety", "Variety / range"), ("speed", "Speed of service"), ("safety", "Safety of premises & route"), ("women_friendly", "Women-friendly environment"),
    ("step_free", "Step-free accessibility"), ("wifi", "Wi-Fi / connectivity"), ("digital_pay", "Digital payments (UPI/cards)"), ("loyalty", "Loyalty programme"),
    ("trial", "Free trial / intro offer"), ("personal", "Personalisation"), ("expertise", "Staff expertise"), ("core_quality", "Core product / equipment quality"),
    ("crowding", "Low crowding"), ("music", "Music / atmosphere"), ("light", "Natural light & space"), ("family", "Family / kid friendly"),
    ("pet", "Pet friendly"), ("veg", "Vegetarian / dietary options"), ("healthy", "Healthy options"), ("portion", "Portion / value size"),
    ("consistency", "Consistency"), ("booking", "Ease of booking / ordering"), ("delivery", "Delivery / home service"), ("online", "Online presence & listings"),
    ("community", "Community feel"), ("privacy", "Privacy"), ("quiet", "Low noise"), ("comfort", "Seating / comfort"),
    ("amenities", "Lockers, showers & amenities"), ("guidance", "Trainer / advisor availability"), ("punctual", "Opens on time, reliable hours"), ("extras", "Value-added services"),
]
AK = {k: i for i, (k, _) in enumerate(ATTRS)}
# attribute relevance by archetype (1 = core, 0.5 = secondary, 0.15 = marginal)
_REL = {
    "membership": "core_quality amenities guidance crowding cleanliness hygiene community trial ac safety women_friendly parking punctual personal expertise",
    "dine_in": "ambience core_quality cleanliness hygiene veg comfort wifi music staff wait portion family consistency parking ac",
    "takeaway": "speed delivery core_quality portion consistency hygiene digital_pay booking online veg healthy wait",
    "retail": "variety parking digital_pay speed staff brand wait delivery online consistency safety extras",
    "appointment": "expertise booking wait hygiene personal privacy staff punctual consistency cleanliness women_friendly comfort",
    "lodging": "cleanliness safety comfort quiet wifi ac staff hygiene brand privacy online booking parking amenities",
}
FEATURES = ["inside", "is_new", "established", "has_reviews", "price_rel", "quality_c", "premium", "budget", "marketing",
            "hours_span", "late_open", "early_open", "weekend_open"] + [f"attr_{k}" for k, _ in ATTRS]
FI = {k: i for i, k in enumerate(FEATURES)}

DEFAULT_HOURS = {"membership": (5, 23), "dine_in": (8, 23), "takeaway": (11, 23), "retail": (9, 22), "appointment": (10, 20), "lodging": (0, 24)}

CHANNELS = [
    ("search", "Search & maps"), ("instagram", "Instagram"), ("whatsapp", "WhatsApp groups"), ("youtube", "YouTube"),
    ("facebook", "Facebook"), ("aggregator", "Aggregator apps"), ("reviews", "Review platforms"), ("signage", "Storefront signage"),
    ("flyers", "Flyers & print"), ("newspaper", "Local newspaper"), ("radio", "FM radio"), ("outdoor", "Hoardings / outdoor"),
    ("events", "Local events"), ("referral", "Referral offers"), ("wom", "Word of mouth"), ("influencer", "Local influencers"),
]
# share of marketing budget per channel by archetype (assumption). Missing channels get 0.02.
_MIX = {
    "membership": {"instagram": .22, "search": .18, "flyers": .12, "signage": .10, "referral": .12, "whatsapp": .08, "influencer": .08, "events": .06, "youtube": .04},
    "dine_in": {"instagram": .24, "aggregator": .18, "search": .14, "reviews": .12, "influencer": .10, "signage": .08, "whatsapp": .06, "flyers": .04},
    "takeaway": {"aggregator": .36, "instagram": .16, "search": .12, "reviews": .10, "flyers": .08, "whatsapp": .08, "signage": .05},
    "retail": {"search": .20, "signage": .16, "flyers": .14, "whatsapp": .12, "instagram": .10, "newspaper": .06, "outdoor": .08, "facebook": .06},
    "appointment": {"search": .26, "reviews": .18, "instagram": .14, "whatsapp": .12, "referral": .12, "signage": .06},
    "lodging": {"aggregator": .40, "search": .20, "reviews": .18, "instagram": .08, "facebook": .04},
}

CATEGORIES = [
    "gym", "yoga", "home_fitness", "sports_club", "dance", "martial_arts", "swimming", "running_club", "cafe", "restaurant", "street_food",
    "fast_food", "bakery", "cloud_kitchen", "grocery", "pharmacy", "apparel", "electronics", "salon", "spa", "clinic", "dental",
    "coaching", "tuition", "coworking", "hotel", "homestay", "cinema", "gaming", "bookstore", "pet_care", "laundry", "repair",
    "supplements", "health_food", "sportswear", "physio", "beauty_products", "online_shopping", "food_delivery",
]
CAT = {k: i for i, k in enumerate(CATEGORIES)}
# per archetype: (focal categories -> participation), (substitutes -> outside option), (complements -> participation)
_CAT_ROLE = {
    "membership": ("gym coworking coaching", "yoga home_fitness sports_club dance martial_arts swimming running_club", "supplements health_food sportswear physio"),
    "dine_in": ("cafe restaurant", "street_food fast_food food_delivery cloud_kitchen bakery", "cinema bookstore gaming"),
    "takeaway": ("fast_food cloud_kitchen bakery food_delivery", "restaurant cafe street_food grocery", "gaming cinema"),
    "retail": ("grocery apparel electronics pharmacy", "online_shopping", "beauty_products sportswear"),
    "appointment": ("salon spa clinic dental physio tuition", "beauty_products online_shopping", "pharmacy health_food"),
    "lodging": ("hotel homestay", "coworking", "restaurant cinema"),
}

# Baseline mode shares (walk, two-wheeler, car, auto, bus, metro, cycle). Walk 28.3% and two-wheeler 42.6% are the
# national shares of work trips in MoSPI's National Household Travel Survey 2025-26; the remaining 29.1% is split
# across the other modes in the previous assumed proportions (8:10:12:5:5) - those five are assumptions.
MODE_BASE_SHARES = np.array([0.283, 0.426] + [0.291 * w / 40 for w in (8, 10, 12, 5, 5)])
MODES = [("walk", 4.5, 0.55), ("two_wheeler", 18.0, 1.25), ("car", 16.0, 1.4), ("auto", 14.0, 1.1), ("bus", 11.0, 0.95), ("metro", 25.0, 1.2), ("cycle", 10.0, 0.8)]

# ---------------------------------------------------------------- parameter registry
@dataclass(frozen=True)
class Param:
    key: str
    label: str
    block: str
    unit: str
    origin: str          # evidence | latent | generated
    mechanism: str
    mu: float = 0.0
    loads: tuple = ()     # ((column, coef), ...)
    sd: float = 0.6
    tr: str = "sig"       # sig | logn | lin | raw
    lo: float = 0.0
    hi: float = 1.0
    w: float = 0.0        # signed weight within its mechanism
    feat: str | None = None  # business feature it interacts with (utility mechanism)

    def public(self) -> dict:
        return {"key": self.key, "label": self.label, "block": self.block, "unit": self.unit, "origin": self.origin,
                "mechanism": self.mechanism, "w": self.w, "feat": self.feat,
                "loads": {a: b for a, b in self.loads}, "sd": self.sd, "transform": self.tr, "range": [self.lo, self.hi]}


def _L(s: str) -> tuple:
    out = []
    for tok in s.split():
        k, v = tok.split(":")
        out.append((k, float(v)))
    return tuple(out)


REG: list[Param] = []


def P(key, label, block, unit, mech, loads="", mu=0.0, sd=0.6, tr="sig", lo=0.0, hi=1.0, w=0.0, feat=None, origin="generated"):
    REG.append(Param(key, label, block, unit, origin, mech, mu, _L(loads), sd, tr, lo, hi, w, feat))


BLOCKS = {
    "evidence": "Placement & real geography", "latent": "Latent traits", "economics": "Economics & price psychology",
    "temporal": "Time availability", "importance": "Attribute importance", "expectation": "Expectation thresholds",
    "channels": "Media & channel receptivity", "social": "Social influence", "mobility": "Mobility & travel",
    "competition": "Competitive geography", "behavior": "Decision psychology", "retention": "Retention & loyalty",
    "affinity": "Category affinities", "lifestyle": "Lifestyle & needs", "digital": "Digital behaviour", "constraints": "Constraints & context",
}

# 1. evidence (16) — values computed, not generated
for k, lbl, unit, mech in [
    ("lat", "Latitude", "°", "placement"), ("lng", "Longitude", "°", "placement"), ("zone", "Demand zone index", "id", "placement"),
    ("zone_population", "Residents in agent's zone (WorldPop)", "people", "placement"), ("zone_activity", "Activity points in zone (OSM)", "count", "participation"),
    ("zone_density_z", "Zone density z-score", "z", "social"), ("age", "Age (WorldPop age–sex structure)", "years", "participation"),
    ("female", "Female", "flag", "participation"), ("household_size", "Household size", "people", "participation"),
    ("segment", "Income segment", "id", "price"), ("mode", "Main travel mode", "id", "travel"), ("mode_speed", "Travel speed of main mode", "km/h", "travel"),
    ("dist_site", "Road distance to your site", "km", "travel"), ("time_site", "Travel time to your site", "min", "travel"),
    ("reach_site", "Your site inside consideration range", "flag", "travel"), ("in_market", "In market this horizon", "flag", "participation"),
]:
    REG.append(Param(f"ev_{k}", lbl, "evidence", unit, "evidence", mech, tr="raw"))

# 2. latent (16)
for k, lbl in LATENTS:
    mech = {"income": "price", "price_consc": "price", "quality_orient": "utility", "convenience": "travel", "novelty": "utility", "social": "social",
            "digital": "awareness", "health": "participation", "status": "utility", "time_poverty": "time_fit", "habit": "retention",
            "risk_aversion": "utility", "family_load": "participation", "mobility": "travel", "locality": "travel", "planning": "retention"}[k]
    REG.append(Param(f"lt_{k}", lbl, "latent", "z", "latent", mech, tr="raw"))

# 3. economics (52)
E = "economics"
P("ec_wtp_multiple", "Willingness to pay (× local reference price)", E, "×", "price", "income:.35 status:.15 price_consc:-.2 quality_orient:.1", sd=.38, tr="logn", lo=1.0, hi=6.0)
P("ec_price_sens", "Price sensitivity multiplier", E, "×", "price", "price_consc:.35 income:-.2 planning:.08", sd=.2, tr="logn", lo=1.0, hi=4.0)
P("ec_loss_aversion", "Loss aversion above WTP", E, "×", "price", "risk_aversion:.3 price_consc:.2", sd=.25, tr="logn", lo=2.5, hi=8.0)
P("ec_sticker_shock", "Sticker-shock threshold (× WTP)", E, "×", "price", "income:.15 price_consc:-.15", mu=0.0, sd=.12, tr="logn", lo=1.05, hi=2.0)
P("ec_budget_share", "Share of discretionary budget for category", E, "share", "participation", "income:.3 health:.2 status:.2 price_consc:-.25", mu=-2.6, sd=.5, w=.18)
P("ec_budget_flex", "Budget flexibility", E, "0-1", "price", "income:.4 planning:-.2", w=.0)
P("ec_discount_resp", "Responsiveness to discounts", E, "0-1", "utility", "price_consc:.5 novelty:.15", w=-.25, feat="price_rel")
P("ec_bundle_aff", "Bundle / package affinity", E, "0-1", "utility", "planning:.3 price_consc:.25", w=.08, feat="attr_extras")
P("ec_upfront_tol", "Tolerance for upfront payment", E, "0-1", "retention", "income:.4 planning:.3 risk_aversion:-.2", w=.12)
P("ec_installment", "Preference for instalments", E, "0-1", "utility", "income:-.35 planning:.15", w=.05, feat="attr_digital_pay")
P("ec_cash_pref", "Cash preference", E, "0-1", "utility", "digital:-.6 age:.3", w=-.12, feat="attr_digital_pay")
P("ec_upi_pref", "UPI preference", E, "0-1", "utility", "digital:.6 age:-.2", w=.15, feat="attr_digital_pay")
P("ec_card_pref", "Card preference", E, "0-1", "utility", "income:.4 digital:.3", w=.06, feat="attr_digital_pay")
P("ec_fairness", "Price-fairness sensitivity", E, "0-1", "utility", "price_consc:.4 social:.1", w=-.2, feat="price_rel")
P("ec_premium_will", "Willingness to pay for premium tier", E, "0-1", "utility", "status:.45 income:.35 quality_orient:.2", w=.35, feat="premium")
P("ec_budget_tier_pull", "Attraction to budget tier", E, "0-1", "utility", "price_consc:.5 income:-.4", w=.3, feat="budget")
P("ec_switch_cost", "Perceived switching cost", E, "0-1", "retention", "habit:.4 risk_aversion:.3", w=-.3)
P("ec_ref_anchor", "Reference-price anchoring", E, "0-1", "price", "planning:.3 price_consc:.3", w=0)
P("ec_ref_drift", "Reference-price drift from last paid", E, "0-1", "price", "habit:.3", w=0)
P("ec_income_stability", "Income stability", E, "0-1", "retention", "income:.4 planning:.2 age:.1", w=-.2)
P("ec_debt_aversion", "Debt aversion", E, "0-1", "utility", "risk_aversion:.4 age:.2", w=-.05, feat="premium")
P("ec_value_focus", "Value-for-money focus", E, "0-1", "utility", "price_consc:.4 quality_orient:.2", w=.15, feat="attr_portion")
P("ec_tip_prop", "Tipping / extras spend propensity", E, "0-1", "utility", "income:.3 social:.2", w=.04, feat="attr_extras")
P("ec_impulse_spend", "Impulse spending", E, "0-1", "participation", "novelty:.35 planning:-.4 income:.15", w=.08)
P("ec_saving_mode", "Currently in saving mode", E, "0-1", "participation", "price_consc:.3 family_load:.25 income:-.3", w=-.12)
P("ec_promo_wait", "Waits for promotions before buying", E, "0-1", "retention", "price_consc:.4 planning:.3", w=-.05)
P("ec_free_trial_resp", "Response to free trials", E, "0-1", "utility", "price_consc:.3 novelty:.3 risk_aversion:.2", w=.18, feat="attr_trial")
P("ec_membership_pref", "Prefers subscription over pay-per-use", E, "0-1", "retention", "planning:.35 habit:.3 income:.15", w=.15)
P("ec_price_memory", "Price recall accuracy", E, "0-1", "utility", "planning:.4 price_consc:.3", w=-.08, feat="price_rel")
P("ec_compare_prices", "Compares prices across options", E, "0-1", "utility", "price_consc:.45 digital:.2", w=-.18, feat="price_rel")
P("ec_quality_price_inference", "Infers quality from price", E, "0-1", "utility", "status:.3 risk_aversion:.2 price_consc:-.3", w=.12, feat="premium")
P("ec_household_budget_pressure", "Household budget pressure", E, "0-1", "participation", "family_load:.4 income:-.4", w=-.15)
P("ec_disc_income", "Discretionary income index", E, "index", "participation", "income:.6 family_load:-.2", w=.18)
P("ec_spend_monthly_cat", "Monthly spend capacity for category (× ref)", E, "×", "price", "income:.4 status:.15 price_consc:-.2", sd=.35, tr="logn", lo=1.2, hi=8.0)
P("ec_gst_awareness", "Sensitivity to taxes & hidden fees", E, "0-1", "utility", "planning:.3 price_consc:.3", w=-.06, feat="price_rel")
P("ec_cashback_pull", "Cashback / wallet offer pull", E, "0-1", "utility", "digital:.4 price_consc:.3", w=.06, feat="attr_digital_pay")
P("ec_corporate_benefit", "Has employer / corporate benefit", E, "0-1", "price", "income:.4 time_poverty:.2", mu=-1.2, w=0)
P("ec_student_discount_elig", "Eligible for student pricing", E, "0-1", "price", "age:-.9 income:-.2", mu=-1.0, w=0)
P("ec_senior_discount_elig", "Eligible for senior pricing", E, "0-1", "price", "age:1.1", mu=-1.6, w=0)
P("ec_risk_of_overpay", "Fear of overpaying", E, "0-1", "utility", "risk_aversion:.35 price_consc:.3", w=-.1, feat="premium")
P("ec_luxury_signal", "Values luxury signalling", E, "0-1", "utility", "status:.6 income:.3", w=.18, feat="attr_brand")
P("ec_negotiation", "Negotiation propensity", E, "0-1", "utility", "price_consc:.4 social:.1 digital:-.15", w=-.05, feat="established")
P("ec_paid_ads_trust", "Trust in paid promotions", E, "0-1", "awareness", "novelty:.2 age:-.15 planning:-.1", w=.1)
P("ec_sunk_cost", "Sunk-cost effect (stays after paying)", E, "0-1", "retention", "risk_aversion:.3 habit:.2", w=-.15)
P("ec_family_pricing_pull", "Pull of family / couple pricing", E, "0-1", "utility", "family_load:.5", w=.06, feat="attr_family")
P("ec_monthly_cycle", "Salary-cycle spending effect", E, "0-1", "participation", "income:-.2 planning:-.15", w=.04)
P("ec_price_threshold_round", "Sensitivity to price endings (₹999 vs ₹1,000)", E, "0-1", "utility", "price_consc:.3 planning:-.2", w=-.03, feat="price_rel")
P("ec_willing_deposit", "Willing to pay deposits / joining fees", E, "0-1", "retention", "income:.4 planning:.2", w=.06)
P("ec_premium_service_add", "Buys add-on services", E, "0-1", "utility", "income:.35 status:.25 novelty:.15", w=.08, feat="attr_extras")
P("ec_coupon_use", "Coupon usage", E, "0-1", "awareness", "price_consc:.45 digital:.25", w=.08)
P("ec_affordability_stress", "Affordability stress at your price", E, "0-1", "price", "income:-.5 family_load:.2", w=0)
P("ec_value_seek_new", "Tries new places for better value", E, "0-1", "utility", "price_consc:.3 novelty:.3 habit:-.3", w=.1, feat="is_new")

# 4. temporal (24 weekday hours + 24 weekend hours + 7 days + 12 months = 67)
_WD = [-3.2, -3.4, -3.5, -3.5, -2.8, -0.9, 0.6, 1.2, 0.6, -0.2, -0.5, -0.4, -0.2, -0.4, -0.6, -0.5, -0.1, 0.6, 1.3, 1.4, 1.0, 0.3, -0.8, -2.2]
_WE = [-3.0, -3.3, -3.5, -3.5, -3.0, -1.6, -0.4, 0.5, 1.0, 1.1, 1.0, 0.8, 0.5, 0.2, 0.2, 0.4, 0.7, 1.0, 1.2, 1.2, 1.0, 0.5, -0.4, -1.6]
for h in range(24):
    tp = -0.5 if 9 <= h <= 17 else (0.3 if h in (6, 7, 20, 21) else 0.0)
    P(f"tm_wd_{h:02d}", f"Weekday availability {h:02d}:00–{h + 1:02d}:00", "temporal", "0-1", "time_fit",
      f"time_poverty:{tp} age:{0.25 if 9 <= h <= 16 else -0.1} family_load:{-0.3 if h in (7, 8, 18, 19) else 0.0}", mu=_WD[h], sd=.7)
for h in range(24):
    P(f"tm_we_{h:02d}", f"Weekend availability {h:02d}:00–{h + 1:02d}:00", "temporal", "0-1", "time_fit",
      f"family_load:{-0.25 if 10 <= h <= 13 else 0.0} social:{0.3 if h >= 19 else 0.0}", mu=_WE[h], sd=.7)
for d, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
    P(f"tm_day_{name.lower()}", f"Likelihood of visiting on {name}", "temporal", "0-1", "time_fit",
      f"time_poverty:{-0.25 if d < 5 else 0.2} social:{0.2 if d >= 4 else 0.0}", mu=0.6 if d < 5 else 0.9, sd=.5)
for mth, name in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]):
    base = [0.35, 0.15, 0.0, -0.05, -0.2, -0.25, -0.3, -0.2, -0.05, 0.15, 0.2, 0.1][mth]
    P(f"tm_month_{name.lower()}", f"Seasonal propensity in {name}", "temporal", "×", "participation", f"health:{0.15 if mth == 0 else 0.0}",
      mu=base, sd=.25, tr="logn", lo=1.0, hi=3.0)

# 5. importance (40) & 6. expectation thresholds (40)
for k, lbl in ATTRS:
    loads = {
        "cleanliness": "quality_orient:.3 age:.15", "staff": "social:.3 quality_orient:.2", "wait": "time_poverty:.5 convenience:.3",
        "parking": "mobility:.5 income:.3", "ac": "income:.3 quality_orient:.2", "ambience": "status:.4 social:.2", "hygiene": "quality_orient:.3 risk_aversion:.2 age:.15",
        "brand": "status:.5 risk_aversion:.2", "variety": "novelty:.4", "speed": "time_poverty:.5 convenience:.4", "safety": "risk_aversion:.4 female:.6",
        "women_friendly": "female:1.2", "step_free": "age:.6 family_load:.2", "wifi": "digital:.5 age:-.2", "digital_pay": "digital:.6",
        "loyalty": "habit:.4 price_consc:.3", "trial": "price_consc:.3 risk_aversion:.3 novelty:.2", "personal": "status:.3 quality_orient:.3",
        "expertise": "quality_orient:.4 health:.3", "core_quality": "quality_orient:.6", "crowding": "time_poverty:.2 quality_orient:.2 female:.2",
        "music": "age:-.4 social:.2", "light": "health:.2 quality_orient:.2", "family": "family_load:.8", "pet": "family_load:.1 locality:.2",
        "veg": "health:.3", "healthy": "health:.6", "portion": "price_consc:.4", "consistency": "habit:.4 risk_aversion:.2", "booking": "digital:.4 planning:.3",
        "delivery": "convenience:.5 time_poverty:.3", "online": "digital:.5", "community": "social:.5 locality:.3", "privacy": "female:.4 status:.2",
        "quiet": "age:.3 status:.2", "comfort": "age:.3 income:.2", "amenities": "income:.3 time_poverty:.2", "guidance": "health:.3 risk_aversion:.2 novelty:.1",
        "punctual": "planning:.4 time_poverty:.3", "extras": "income:.3 novelty:.2",
    }[k]
    P(f"im_{k}", f"Importance: {lbl}", "importance", "0-1", "utility", loads, mu=-0.2, sd=.7, w=1.0, feat=f"attr_{k}")
for k, lbl in ATTRS:
    P(f"ex_{k}", f"Minimum acceptable: {lbl}", "expectation", "0-1", "expectation", "quality_orient:.4 status:.2 price_consc:-.15", mu=-0.7, sd=.6, w=1.0, feat=f"attr_{k}")

# 7. channels (16 x 3 = 48)
_CH_LOAD = {
    "search": "digital:.5 planning:.3", "instagram": "digital:.6 age:-.5 social:.2", "whatsapp": "social:.5 locality:.2", "youtube": "digital:.4 age:-.3",
    "facebook": "age:.2 digital:.2", "aggregator": "digital:.5 convenience:.4", "reviews": "digital:.4 risk_aversion:.3", "signage": "locality:.4 mobility:-.2",
    "flyers": "age:.3 locality:.3", "newspaper": "age:.6 digital:-.3", "radio": "mobility:.4 age:.2", "outdoor": "mobility:.4",
    "events": "social:.5 novelty:.3", "referral": "social:.5", "wom": "social:.6 locality:.3", "influencer": "age:-.5 status:.3 digital:.3",
}
for k, lbl in CHANNELS:
    P(f"ch_{k}_reach", f"{lbl}: exposure", "channels", "0-1", "awareness", _CH_LOAD[k], mu=-0.3, sd=.7, w=1.0)
    P(f"ch_{k}_trust", f"{lbl}: trust", "channels", "0-1", "awareness", "risk_aversion:-.2 " + ("social:.3" if k in ("wom", "referral", "whatsapp") else "age:.1"), mu=0.0, sd=.6, w=1.0)
    P(f"ch_{k}_resp", f"{lbl}: response propensity", "channels", "0-1", "awareness", "novelty:.3 planning:-.1", mu=-0.4, sd=.6, w=1.0)

# 8. social (28)
S = "social"
for k, lbl, loads, mech, w, feat in [
    ("network_size", "Personal network size", "social:.6 age:-.1", "social", .25, None),
    ("local_ties", "Local ties in neighbourhood", "locality:.6 social:.3", "social", .25, None),
    ("wom_propensity", "Talks about places they like", "social:.5 novelty:.2", "social", .3, None),
    ("wom_susceptibility", "Influenced by friends' choices", "social:.4 risk_aversion:.2", "social", .35, None),
    ("review_reliance", "Relies on online reviews", "digital:.4 risk_aversion:.4", "utility", -.3, "is_new"),
    ("review_writer", "Writes reviews", "digital:.4 social:.3", "social", .1, None),
    ("referral_prop", "Refers others when offered reward", "social:.4 price_consc:.3", "social", .2, None),
    ("group_buying", "Buys / visits in groups", "social:.5 age:-.3", "utility", .08, "attr_community"),
    ("peer_conformity", "Conforms to peers' choices", "social:.4 risk_aversion:.3 novelty:-.2", "utility", .2, "established"),
    ("opinion_leader", "Opinion leadership", "social:.5 status:.3 novelty:.3", "social", .2, None),
    ("family_influence", "Decisions shaped by family", "family_load:.5 age:-.2", "utility", .05, "attr_family"),
    ("partner_coord", "Coordinates visits with partner", "family_load:.3 social:.2", "time_fit", .1, None),
    ("community_belonging", "Wants a community", "social:.4 locality:.3", "utility", .15, "attr_community"),
    ("status_display", "Shares visits on social media", "status:.4 digital:.4 age:-.3", "utility", .1, "attr_ambience"),
    ("neg_wom", "Shares bad experiences", "social:.3 quality_orient:.3", "retention", .2, None),
    ("herding", "Follows crowded places", "social:.3 risk_aversion:.2", "utility", .12, "established"),
    ("contrarian", "Avoids popular places", "novelty:.3 status:.2 social:-.2", "utility", .1, "is_new"),
    ("trust_strangers", "Trust in strangers' opinions", "digital:.3 age:-.2", "social", .1, None),
    ("rwa_member", "Resident-association / society member", "locality:.5 age:.3", "social", .1, None),
    ("workplace_network", "Hears about places at work", "time_poverty:.3 social:.3", "social", .1, None),
    ("student_network", "Campus / batch network", "age:-.9", "social", .12, None),
    ("whatsapp_groups", "Active local WhatsApp groups", "social:.4 locality:.3 age:.1", "social", .15, None),
    ("influencer_follow", "Follows local influencers", "digital:.5 age:-.4", "awareness", .1, None),
    ("celebrity_endorse", "Swayed by endorsements", "status:.4 age:-.2", "utility", .05, "attr_brand"),
    ("recommendation_seek", "Asks for recommendations", "risk_aversion:.3 social:.3", "social", .15, None),
    ("loyal_advocate", "Becomes a vocal advocate", "habit:.3 social:.4", "social", .2, None),
    ("social_proof_need", "Needs social proof before trying", "risk_aversion:.5 novelty:-.3", "utility", -.25, "is_new"),
    ("gossip_reach", "Reach of local gossip", "locality:.4 social:.3", "social", .1, None),
]:
    P(f"so_{k}", lbl, S, "0-1", mech, loads, w=w, feat=feat)

# 9. mobility (28)
M = "mobility"
for k, sp, _tol in MODES:
    ld = {"walk": "mobility:-.4 age:.2 income:-.3", "two_wheeler": "mobility:.4 age:-.3 female:-.3", "car": "income:.8 mobility:.4 age:.2",
          "auto": "mobility:-.1 income:.1", "bus": "income:-.5 mobility:-.2", "metro": "density:.4 time_poverty:.3", "cycle": "age:-.4 health:.4 income:-.2"}[k]
    P(f"mb_access_{k}", f"Access to {k.replace('_', '-')}", M, "0-1", "travel", ld, mu=-0.2, sd=.8)
for k, sp, _tol in MODES:
    P(f"mb_pref_{k}", f"Preference for {k.replace('_', '-')}", M, "0-1", "travel", {"walk": "health:.3 locality:.3", "two_wheeler": "time_poverty:.3",
      "car": "status:.4 income:.3", "auto": "convenience:.3", "bus": "price_consc:.4", "metro": "time_poverty:.3 planning:.2", "cycle": "health:.5"}[k], sd=.7)
for k, lbl, loads, unit, tr, lo, hi, mu, sd, w in [
    ("dist_tol", "Distance tolerance multiplier", "mobility:.3 convenience:-.25 time_poverty:-.2 locality:-.15 age:-.1", "×", "logn", 1.0, 3.0, 0.0, .22, 0),
    ("value_of_time", "Value of time (₹/hour)", "income:.6 time_poverty:.4", "₹/h", "logn", 80.0, 2000.0, 0.0, .5, 0),
    ("max_trip_min", "Maximum acceptable trip time", "mobility:.3 time_poverty:-.3 health:.1", "min", "logn", 18.0, 60.0, 0.0, .3, 0),
    ("parking_need", "Needs parking", "income:.4 mobility:.4", "0-1", "sig", 0, 1, 0.0, .6, .25),
    ("trip_chaining", "Combines trips (on the way)", "time_poverty:.4 planning:.3", "0-1", "sig", 0, 1, 0.0, .6, -0.15),
    ("commute_pass", "Passes your site on commute", "mobility:.2 time_poverty:.2", "0-1", "sig", 0, 1, -0.8, .9, -0.2),
    ("weather_sens", "Weather sensitivity of travel", "mobility:-.3 age:.3", "0-1", "sig", 0, 1, 0.0, .6, 0.1),
    ("night_travel_comfort", "Comfort travelling at night", "female:-.8 age:-.2 mobility:.2", "0-1", "sig", 0, 1, 0.0, .6, -0.1),
    ("traffic_aversion", "Traffic aversion", "time_poverty:.4 age:.2", "0-1", "sig", 0, 1, 0.0, .6, 0.15),
    ("ride_hail_use", "Uses ride-hailing", "income:.4 digital:.3", "0-1", "sig", 0, 1, 0.0, .6, -0.05),
    ("route_familiarity", "Familiarity with local routes", "locality:.5 age:.2", "0-1", "sig", 0, 1, 0.0, .6, -0.1),
    ("home_bound", "Home-bound hours share", "family_load:.4 age:.3 time_poverty:-.2", "0-1", "sig", 0, 1, 0.0, .6, 0.1),
    ("work_dist", "Distance home → work", "mobility:.4 income:.2", "km", "logn", 6.0, 40.0, 0.0, .6, -0.05),
    ("walk_tolerance", "Walking tolerance", "health:.4 age:-.3 mobility:-.2", "km", "logn", 0.8, 4.0, 0.0, .35, -0.15),
]:
    P(f"mb_{k}", lbl, M, unit, "travel", loads, mu=mu, sd=sd, tr=tr, lo=lo, hi=hi, w=w, feat="attr_parking" if k == "parking_need" else None)

# 10. competitive geography (30) — computed from real business locations
for r in (0.5, 1.0, 1.5, 2.0, 3.0, 5.0):
    REG.append(Param(f"cg_ring_{str(r).replace('.', '_')}km", f"Mapped businesses within {r} km of agent", "competition", "count", "evidence", "travel", tr="raw"))
for n in range(1, 11):
    REG.append(Param(f"cg_d{n:02d}", f"Distance to {n}{'st' if n == 1 else 'nd' if n == 2 else 'rd' if n == 3 else 'th'} nearest option", "competition", "km", "evidence", "travel", tr="raw"))
for n in range(1, 11):
    REG.append(Param(f"cg_t{n:02d}", f"Travel time to {n}{'st' if n == 1 else 'nd' if n == 2 else 'rd' if n == 3 else 'th'} nearest option", "competition", "min", "evidence", "travel", tr="raw"))
for k, lbl, unit in [("n_reach", "Options inside consideration range", "count"), ("rank_site", "Rank of your site by distance", "rank"),
                     ("gap_site", "Your distance minus nearest competitor", "km"), ("mean_t", "Mean time to options in range", "min")]:
    REG.append(Param(f"cg_{k}", lbl, "competition", unit, "evidence", "travel", tr="raw"))

# 11. behaviour (48)
B = "behavior"
for k, lbl, loads, mech, w, feat in [
    ("noise", "Choice randomness (taste noise scale)", "planning:-.3 novelty:.2", "noise", 1.0, None),
    ("inertia", "Status-quo inertia", "habit:.5 risk_aversion:.3", "retention", .35, None),
    ("variety_seek", "Variety seeking", "novelty:.6 habit:-.3", "retention", -.3, None),
    ("impulsivity", "Impulsivity", "planning:-.5 novelty:.3", "utility", .12, "is_new"),
    ("deal_seeking", "Deal seeking", "price_consc:.6", "utility", -.2, "price_rel"),
    ("trial_bias", "Willingness to try a new business", "novelty:.6 risk_aversion:-.4", "utility", .45, "is_new"),
    ("brand_trust_need", "Needs an established brand", "risk_aversion:.5 status:.2 novelty:-.3", "utility", .35, "established"),
    ("satisficing", "Satisficer (first acceptable option)", "time_poverty:.3 planning:-.3", "noise", .3, None),
    ("choice_set", "Size of considered set", "planning:.4 digital:.3", "noise", -.2, None),
    ("regret_aversion", "Regret aversion", "risk_aversion:.5", "utility", -.15, "is_new"),
    ("ambiguity_aversion", "Ambiguity aversion", "risk_aversion:.5 planning:.2", "utility", -.12, "is_new"),
    ("decision_speed", "Decision speed", "time_poverty:.3 planning:-.3 novelty:.2", "noise", .1, None),
    ("info_search", "Information search effort", "planning:.5 digital:.3", "awareness", .2, None),
    ("first_impression", "Weight on first impression", "status:.3 novelty:.2", "utility", .15, "attr_ambience"),
    ("optimism", "Optimism about new places", "novelty:.4 risk_aversion:-.3", "utility", .15, "is_new"),
    ("perfectionism", "Perfectionism", "quality_orient:.5 status:.2", "utility", .2, "quality_c"),
    ("loss_framing", "Sensitivity to loss framing", "risk_aversion:.4", "price", .0, None),
    ("default_effect", "Sticks to defaults", "habit:.4 planning:-.2", "retention", .2, None),
    ("scarcity_resp", "Responds to scarcity / urgency", "novelty:.3 planning:-.3", "awareness", .1, None),
    ("authority_resp", "Responds to expert authority", "risk_aversion:.3 health:.2", "utility", .1, "attr_expertise"),
    ("reciprocity", "Reciprocity (returns favours)", "social:.4", "retention", .1, None),
    ("commitment_consistency", "Commitment consistency", "planning:.4 habit:.3", "retention", .2, None),
    ("present_bias", "Present bias", "planning:-.5 novelty:.2", "retention", -.2, None),
    ("goal_orientation", "Goal orientation", "planning:.4 health:.3", "participation", .15, None),
    ("self_efficacy", "Self-efficacy", "health:.3 income:.2 risk_aversion:-.2", "participation", .1, None),
    ("procrastination", "Procrastination", "planning:-.5 time_poverty:.2", "participation", -.15, None),
    ("intrinsic_motiv", "Intrinsic motivation for category", "health:.5 quality_orient:.2", "participation", .2, None),
    ("extrinsic_motiv", "Extrinsic motivation (looks, status)", "status:.5 age:-.3", "participation", .1, None),
    ("anchoring", "Anchoring on first price seen", "planning:-.2 price_consc:.3", "price", .0, None),
    ("framing_sens", "Framing sensitivity", "planning:-.3", "utility", .05, "attr_trial"),
    ("decoy_sens", "Decoy-pricing sensitivity", "planning:-.2 price_consc:.2", "utility", .04, "premium"),
    ("mental_accounting", "Mental accounting strictness", "planning:.4 price_consc:.3", "price", .0, None),
    ("overconfidence", "Overconfidence in usage", "novelty:.3 planning:-.2", "participation", .1, None),
    ("attention_span", "Attention to ads", "digital:.2 age:.1 time_poverty:-.3", "awareness", .2, None),
    ("ad_fatigue", "Ad fatigue", "digital:.3 age:-.2", "awareness", -.2, None),
    ("curiosity", "Curiosity", "novelty:.6", "awareness", .2, None),
    ("brand_switch_hist", "History of switching brands", "novelty:.4 habit:-.4", "retention", -.2, None),
    ("complaint_prop", "Complaint propensity", "quality_orient:.3 status:.2", "retention", -.05, None),
    ("forgiveness", "Forgives service failures", "habit:.3 social:.2 quality_orient:-.2", "retention", .2, None),
    ("congestion_tol", "Tolerance of crowding", "social:.3 time_poverty:-.3", "utility", -.15, "attr_crowding"),
    ("queue_tol", "Tolerance of queues", "time_poverty:-.5", "utility", -.15, "attr_wait"),
    ("risk_new_place", "Perceived risk of a new place", "risk_aversion:.6", "utility", -.3, "is_new"),
    ("experiment_budget", "Budget set aside to try new things", "novelty:.4 income:.3", "utility", .15, "is_new"),
    ("routine_strength", "Routine strength", "habit:.6 planning:.2", "retention", .25, None),
    ("seasonal_motivation", "New-year / seasonal motivation", "health:.3 novelty:.3", "participation", .08, None),
    ("fomo", "Fear of missing out", "social:.4 novelty:.3 age:-.3", "awareness", .15, None),
    ("persuadability", "Persuadability", "risk_aversion:-.2 social:.3", "awareness", .15, None),
    ("rationality", "Deliberative (vs intuitive) decisions", "planning:.5", "noise", -.2, None),
]:
    P(f"bh_{k}", lbl, B, "0-1", mech, loads, w=w, feat=feat)

# 12. retention (28)
R = "retention"
for k, lbl, loads, w in [
    ("churn_base", "Baseline churn hazard", "habit:-.3 novelty:.3 planning:-.2", -.4), ("habit_rate", "Habit formation speed", "habit:.5", .5),
    ("habit_cap", "Maximum habit strength", "habit:.4 locality:.2", .3), ("habit_decay", "Habit decay when not visiting", "habit:-.4", -.2),
    ("satisfaction_sens", "Sensitivity of loyalty to satisfaction", "quality_orient:.4", .3), ("reactivation", "Reactivation propensity", "habit:.2 locality:.3", .1),
    ("loyalty_prog_resp", "Loyalty-programme response", "price_consc:.3 habit:.3", .1), ("relationship_value", "Values relationship with staff", "social:.4 age:.2", .2),
    ("commitment_months", "Preferred commitment length", "planning:.4 income:.2", .15), ("switch_threshold", "Advantage needed to switch", "habit:.4 risk_aversion:.3", .4),
    ("pause_prop", "Pauses rather than quits", "planning:.3", .1), ("moving_out_risk", "Likelihood of moving away", "age:-.4 locality:-.4", -.15),
    ("life_event_risk", "Life-event disruption risk", "family_load:.3 age:-.2", -.1), ("burnout", "Usage burnout", "time_poverty:.4 health:-.2", -.15),
    ("progress_need", "Needs visible progress", "health:.3 planning:.3", .05), ("fairness_memory", "Remembers unfair treatment", "quality_orient:.3", -.05),
    ("renewal_inertia", "Auto-renew inertia", "habit:.3 planning:-.3", .2), ("winback_resp", "Response to win-back offers", "price_consc:.4", .05),
    ("tenure_pride", "Pride in long tenure", "habit:.4 status:.2", .1), ("friend_retention", "Stays because friends attend", "social:.5", .2),
    ("crowd_churn", "Churns when crowded", "time_poverty:.3 quality_orient:.2", -.25), ("price_rise_churn", "Churns on price rises", "price_consc:.5", -.15),
    ("competitor_poach", "Susceptible to competitor offers", "price_consc:.3 novelty:.3 habit:-.3", -.2), ("visit_freq_stability", "Visit-frequency stability", "habit:.4 planning:.3", .15),
    ("seasonal_dropout", "Seasonal drop-out", "health:-.2 habit:-.3", -.1), ("payment_failure", "Payment-failure risk", "income:-.4 planning:-.3", -.05),
    ("upgrade_prop", "Upgrades plan over time", "income:.4 status:.3", .05), ("recommend_after", "Recommends after 3+ visits", "social:.4 habit:.2", .1),
]:
    P(f"rt_{k}", lbl, R, "0-1", "retention", loads, w=w)

# 13. category affinity (40)
for c in CATEGORIES:
    ld = {"gym": "health:.6 age:-.4 status:.2", "yoga": "health:.5 age:.2 female:.4", "home_fitness": "health:.3 time_poverty:.4 digital:.3",
          "sports_club": "health:.4 social:.4", "dance": "social:.4 female:.5 age:-.3", "martial_arts": "health:.3 age:-.5", "swimming": "health:.4 income:.3",
          "running_club": "health:.5 social:.3", "cafe": "social:.4 digital:.3 age:-.3", "restaurant": "income:.4 social:.3", "street_food": "price_consc:.4 age:-.3",
          "fast_food": "convenience:.4 age:-.4", "bakery": "family_load:.3", "cloud_kitchen": "digital:.4 convenience:.4", "grocery": "family_load:.5",
          "pharmacy": "age:.5", "apparel": "status:.4 female:.3", "electronics": "digital:.5 income:.3", "salon": "status:.4 female:.4", "spa": "income:.5 status:.3",
          "clinic": "age:.5 family_load:.3", "dental": "income:.2 age:.2", "coaching": "age:-.8 planning:.3", "tuition": "family_load:.6", "coworking": "digital:.5 income:.3 age:-.2",
          "hotel": "income:.5 mobility:.4", "homestay": "novelty:.4 digital:.3", "cinema": "social:.4 age:-.3", "gaming": "digital:.5 age:-.6", "bookstore": "planning:.3 quality_orient:.2",
          "pet_care": "family_load:.2 income:.2", "laundry": "time_poverty:.5", "repair": "price_consc:.3", "supplements": "health:.6 age:-.3", "health_food": "health:.6 income:.3",
          "sportswear": "health:.4 status:.3", "physio": "age:.4 health:.3", "beauty_products": "status:.4 female:.6", "online_shopping": "digital:.6 convenience:.3",
          "food_delivery": "digital:.5 convenience:.5 time_poverty:.3"}[c]
    P(f"af_{c}", f"Affinity: {c.replace('_', ' ')}", "affinity", "0-1", "participation", ld, mu=-0.4, sd=.7, w=0.0)

# 14. lifestyle & needs (50)
LS = "lifestyle"
for k, lbl, loads, mech, w, feat in [
    ("health_goal", "Active health goal", "health:.6", "participation", .25, None), ("weight_goal", "Weight-management goal", "health:.4 age:.2", "participation", .12, None),
    ("strength_goal", "Strength / muscle goal", "health:.4 age:-.4 female:-.4", "participation", .1, None), ("stress_level", "Stress level", "time_poverty:.5 family_load:.3", "participation", .05, None),
    ("sleep_regularity", "Sleep regularity", "planning:.4 time_poverty:-.3", "time_fit", .1, None), ("shift_worker", "Shift / night worker", "time_poverty:.3 income:-.2", "time_fit", .15, None),
    ("wfh", "Works from home", "digital:.4 income:.3", "time_fit", .1, None), ("student", "Student", "age:-1.4", "participation", .1, None),
    ("retired", "Retired", "age:1.4", "time_fit", .1, None), ("young_kids", "Has young children", "family_load:.8 age:-.1", "time_fit", -.15, None),
    ("elder_care", "Cares for elderly", "family_load:.5 age:.3", "time_fit", -.1, None), ("pet_owner", "Pet owner", "family_load:.2 locality:.2", "utility", .05, "attr_pet"),
    ("dietary_veg", "Vegetarian", "health:.2", "utility", .3, "attr_veg"), ("dietary_vegan", "Vegan / plant-based", "health:.3 age:-.2", "utility", .05, "attr_veg"),
    ("calorie_conscious", "Calorie conscious", "health:.5", "utility", .15, "attr_healthy"), ("eats_out_freq", "Eats out frequently", "income:.3 social:.3 age:-.2", "participation", .1, None),
    ("cooks_home", "Cooks at home", "family_load:.4 price_consc:.3", "outside", .15, None), ("late_night_life", "Late-night lifestyle", "age:-.4 social:.3", "time_fit", .1, None),
    ("early_riser", "Early riser", "age:.3 health:.3 planning:.2", "time_fit", .1, None), ("weekend_busy", "Busy weekends", "family_load:.4 social:.3", "time_fit", -.05, None),
    ("travel_freq", "Travels out of town often", "income:.4 mobility:.4", "participation", -.08, None), ("hobby_intensity", "Hobby intensity", "novelty:.3 social:.3", "participation", .05, None),
    ("screen_time", "Leisure screen time", "digital:.5 health:-.2", "outside", .08, None), ("outdoor_pref", "Prefers outdoor activities", "health:.3 social:.2", "outside", .1, None),
    ("home_activity", "Prefers home-based activities", "family_load:.3 social:-.3", "outside", .15, None), ("aesthetic_pref", "Aesthetic sensitivity", "status:.4", "utility", .1, "attr_ambience"),
    ("cleanliness_obsession", "High cleanliness standards", "quality_orient:.3 age:.2", "utility", .1, "attr_hygiene"), ("quiet_pref", "Prefers quiet places", "age:.4 social:-.2", "utility", .05, "attr_quiet"),
    ("music_pref", "Likes music / buzz", "age:-.4 social:.3", "utility", .05, "attr_music"), ("ac_need", "Needs air-conditioning", "income:.3 age:.2", "utility", .1, "attr_ac"),
    ("injury_history", "Past injury / limitation", "age:.4", "utility", .05, "attr_guidance"), ("beginner", "Beginner in category", "health:-.3 novelty:.2", "utility", .1, "attr_guidance"),
    ("expert_user", "Experienced user", "health:.4 habit:.3", "utility", .1, "attr_core_quality"), ("social_motive", "Goes for social reasons", "social:.6", "utility", .1, "attr_community"),
    ("me_time_motive", "Goes for personal time", "time_poverty:.3 social:-.2", "utility", .05, "attr_privacy"), ("routine_slot", "Has a fixed weekly slot", "planning:.5 habit:.3", "time_fit", .1, None),
    ("festival_spend", "Festival-season spending lift", "family_load:.2 income:.2", "participation", .05, None), ("new_resident", "Recently moved to area", "locality:-.6 age:-.2", "utility", .15, "is_new"),
    ("long_resident", "Long-time resident", "locality:.6 age:.3", "utility", .1, "established"), ("household_decider", "Main household decision-maker", "age:.3 family_load:.3", "participation", .05, None),
    ("kid_activity_need", "Needs activities for children", "family_load:.7", "utility", .1, "attr_family"), ("convenience_need", "Needs convenience above all", "convenience:.6 time_poverty:.3", "utility", .15, "attr_speed"),
    ("experience_seek", "Seeks experiences over goods", "novelty:.4 income:.2", "utility", .1, "attr_ambience"), ("premium_lifestyle", "Premium lifestyle", "income:.5 status:.4", "utility", .2, "premium"),
    ("frugal_lifestyle", "Frugal lifestyle", "price_consc:.6 income:-.3", "utility", .2, "budget"), ("work_hours_long", "Long working hours", "time_poverty:.6", "time_fit", -.1, None),
    ("commute_long", "Long commute", "time_poverty:.4 mobility:.2", "time_fit", -.1, None), ("free_mornings", "Free mornings", "time_poverty:-.3 age:.3", "time_fit", .1, None),
    ("free_evenings", "Free evenings", "time_poverty:-.3 family_load:-.3", "time_fit", .1, None), ("weather_seasonal", "Activity drops in monsoon / summer", "mobility:-.2 health:-.2", "participation", -.05, None),
]:
    P(f"ls_{k}", lbl, LS, "0-1", mech, loads, w=w, feat=feat)

# 15. digital (34)
DG = "digital"
for k, lbl, loads, mech, w, feat in [
    ("smartphone", "Smartphone user", "digital:.8 age:-.3", "awareness", .2, None), ("data_budget", "Mobile data budget", "income:.3 digital:.4", "awareness", .1, None),
    ("maps_search", "Searches places on maps", "digital:.6", "utility", .2, "attr_online"), ("review_reader", "Reads reviews before visiting", "digital:.4 risk_aversion:.3", "utility", .2, "has_reviews"),
    ("aggregator_user", "Uses aggregator apps", "digital:.5 convenience:.3", "utility", .15, "attr_delivery"), ("delivery_user", "Orders delivery", "convenience:.5 digital:.4", "utility", .15, "attr_delivery"),
    ("online_booking", "Books online", "digital:.5 planning:.3", "utility", .15, "attr_booking"), ("social_scroller", "Heavy social-media user", "digital:.6 age:-.4", "awareness", .15, None),
    ("video_consumer", "Short-video consumer", "digital:.5 age:-.5", "awareness", .1, None), ("ad_click", "Clicks ads", "digital:.3 novelty:.3", "awareness", .15, None),
    ("ad_blocker", "Avoids ads", "digital:.5 income:.2", "awareness", -.15, None), ("email_open", "Opens promotional email", "age:.2 planning:.2", "awareness", .05, None),
    ("sms_open", "Reads promotional SMS", "age:.3 digital:-.2", "awareness", .05, None), ("push_optin", "Accepts app notifications", "digital:.4", "awareness", .05, None),
    ("qr_use", "Scans QR codes", "digital:.6", "awareness", .05, None), ("wallet_use", "Uses wallets", "digital:.5", "utility", .08, "attr_digital_pay"),
    ("online_research", "Researches before buying", "planning:.4 digital:.4", "awareness", .1, None), ("photo_sharer", "Posts photos", "digital:.4 status:.3", "social", .1, None),
    ("rating_threshold", "Minimum star rating considered", "risk_aversion:.3 digital:.3", "utility", -.15, "is_new"), ("listing_trust", "Trusts online listings", "digital:.4", "utility", .1, "attr_online"),
    ("digital_literacy", "Digital literacy", "digital:.7 age:-.3", "awareness", .1, None), ("language_english", "Comfortable with English content", "income:.4 age:-.2", "awareness", .05, None),
    ("language_local", "Prefers local-language content", "income:-.3 age:.3", "awareness", .05, None), ("app_installer", "Installs brand apps", "digital:.5 habit:.2", "retention", .05, None),
    ("streaming_user", "Streaming subscriber", "digital:.5 income:.3", "outside", .03, None), ("online_fitness", "Uses online / app alternatives", "digital:.5 time_poverty:.3", "outside", .12, None),
    ("ecommerce_buyer", "Buys online instead of in store", "digital:.6 convenience:.3", "outside", .1, None), ("whatsapp_business", "Messages businesses on WhatsApp", "digital:.4 social:.3", "utility", .08, "attr_booking"),
    ("local_groups_online", "In local online groups", "social:.4 digital:.4", "social", .1, None), ("influencer_trust", "Trusts influencer reviews", "age:-.4 digital:.4", "awareness", .1, None),
    ("privacy_concern", "Online privacy concern", "risk_aversion:.3 age:.2", "awareness", -.05, None), ("deal_apps", "Uses deal / coupon apps", "price_consc:.5 digital:.4", "utility", -.05, "price_rel"),
    ("voice_search", "Uses voice search", "digital:.3 age:.1", "awareness", .03, None), ("night_browsing", "Browses late at night", "digital:.4 age:-.3", "awareness", .03, None),
]:
    P(f"dg_{k}", lbl, DG, "0-1", mech, loads, w=w, feat=feat)

# 16. constraints & context (fills to 615)
CO = "constraints"
for k, lbl, loads, mech, w, feat in [
    ("mobility_impair", "Mobility impairment", "age:.6", "utility", .2, "attr_step_free"), ("safety_concern", "Safety concern on route", "female:.6 risk_aversion:.3", "utility", .2, "attr_safety"),
    ("women_only_pref", "Prefers women-only spaces / hours", "female:1.0", "utility", .15, "attr_women_friendly"), ("chaperone_need", "Needs company to visit", "female:.3 age:.4", "time_fit", -.05, None),
    ("time_window", "Narrow daily time window", "time_poverty:.6", "time_fit", .2, None), ("childcare_constraint", "Childcare constraint", "family_load:.7", "time_fit", .1, None),
    ("budget_cap_hard", "Hard monthly budget cap", "income:-.5 planning:.3", "price", .0, None), ("dress_code_comfort", "Comfort with dress codes", "status:.2", "utility", .02, "attr_privacy"),
    ("language_barrier", "Language barrier with staff", "income:-.3 age:.2", "utility", .05, "attr_staff"), ("hygiene_health_need", "Health condition needing hygiene", "age:.3", "utility", .08, "attr_hygiene"),
    ("noise_sensitivity", "Noise sensitivity", "age:.4", "utility", .05, "attr_quiet"), ("heat_sensitivity", "Heat sensitivity", "age:.3", "utility", .08, "attr_ac"),
    ("crowd_anxiety", "Anxiety in crowds", "risk_aversion:.3 social:-.3", "utility", .1, "attr_crowding"), ("vehicle_parking_need", "Needs vehicle parking", "income:.5 mobility:.4", "utility", .1, "attr_parking"),
    ("guest_policy", "Brings guests", "social:.4", "utility", .03, "attr_community"), ("dietary_religious", "Dietary rules to follow", "family_load:.2", "utility", .1, "attr_veg"),
    ("allergy_need", "Needs allergen information", "health:.2", "utility", .03, "attr_healthy"), ("contract_aversion", "Avoids long contracts", "risk_aversion:.3 planning:-.2", "retention", -.05, None),
    ("id_doc_hassle", "Avoids paperwork / KYC", "digital:-.2 age:.2", "utility", -.03, "attr_booking"), ("weekday_only", "Can only visit on weekdays", "family_load:.3", "time_fit", .05, None),
    ("weekend_only", "Can only visit on weekends", "time_poverty:.5", "time_fit", .1, None), ("mobility_seasonal", "Seasonal travel restriction", "age:.2", "travel", .05, None),
    ("power_backup_need", "Needs power backup", "age:.1", "utility", .03, "attr_amenities"), ("locker_need", "Needs lockers / storage", "time_poverty:.3", "utility", .05, "attr_amenities"),
    ("shower_need", "Needs showers", "time_poverty:.4", "utility", .06, "attr_amenities"), ("female_staff_pref", "Prefers female staff", "female:.8", "utility", .06, "attr_women_friendly"),
    ("trainer_need", "Needs a trainer / guide", "health:-.2 novelty:.3", "utility", .08, "attr_guidance"), ("kid_care_need", "Needs kid-care while visiting", "family_load:.6", "utility", .05, "attr_family"),
    ("pet_restriction", "Needs pet-friendly premises", "family_load:.1", "utility", .03, "attr_pet"), ("late_hours_need", "Needs late hours", "time_poverty:.5 age:-.2", "utility", .15, "late_open"),
    ("early_hours_need", "Needs early hours", "time_poverty:.3 age:.2", "utility", .12, "early_open"), ("weekend_hours_need", "Needs weekend opening", "time_poverty:.4", "utility", .1, "weekend_open"),
    ("long_hours_value", "Values long opening hours", "time_poverty:.4", "utility", .1, "hours_span"), ("marketing_receptive", "Receptive to brand outreach", "novelty:.3 digital:.2", "utility", .1, "marketing"),
    ("quality_premium_need", "Needs top quality", "quality_orient:.6", "utility", .3, "quality_c"),
    ("wifi_need", "Needs Wi-Fi while there", "digital:.5 time_poverty:.2", "utility", .08, "attr_wifi"),
    ("light_need", "Needs bright, open spaces", "health:.2 age:.2", "utility", .04, "attr_light"),
    ("music_aversion", "Dislikes loud music", "age:.5", "utility", -.06, "attr_music"),
    ("seating_need", "Needs comfortable seating", "age:.4", "utility", .06, "attr_comfort"),
    ("consistency_need", "Needs a predictable experience", "risk_aversion:.4 habit:.3", "utility", .08, "attr_consistency"),
    ("variety_need", "Needs wide choice", "novelty:.4", "utility", .08, "attr_variety"),
    ("brand_shy", "Avoids flashy brands", "status:-.4 price_consc:.2", "utility", -.06, "attr_brand"),
    ("cleanliness_need", "Needs visible cleanliness", "quality_orient:.4 female:.2", "utility", .08, "attr_cleanliness"),
    ("staff_interaction_need", "Wants staff interaction", "social:.4 age:.2", "utility", .05, "attr_staff"),
    ("loyalty_points_need", "Wants loyalty points", "price_consc:.3 habit:.3", "utility", .05, "attr_loyalty"),
    ("portion_need", "Needs generous portions / value", "price_consc:.4 age:-.2", "utility", .06, "attr_portion"),
    ("speed_need", "Needs fast service", "time_poverty:.5", "utility", .08, "attr_speed"),
    ("personal_touch_need", "Wants personal attention", "status:.3 age:.2", "utility", .06, "attr_personal"),
    ("punctuality_need", "Needs reliable hours", "planning:.5", "utility", .05, "attr_punctual"),
    ("extras_need", "Wants value-added services", "income:.3", "utility", .04, "attr_extras"),
]:
    P(f"co_{k}", lbl, CO, "0-1", mech, loads, w=w, feat=feat)

assert len(REG) == GENOME_SIZE, f"genome has {len(REG)} parameters, expected {GENOME_SIZE}"
KEYS = [p.key for p in REG]
KI = {k: i for i, k in enumerate(KEYS)}
_GEN = [i for i, p in enumerate(REG) if p.origin == "generated"]
_MECH = np.array([p.mechanism for p in REG])


def registry_public() -> dict:
    by_block, by_mech, by_origin = {}, {}, {}
    for p in REG:
        by_block[p.block] = by_block.get(p.block, 0) + 1
        by_mech[p.mechanism] = by_mech.get(p.mechanism, 0) + 1
        by_origin[p.origin] = by_origin.get(p.origin, 0) + 1
    return {"size": GENOME_SIZE, "blocks": BLOCKS, "by_block": by_block, "by_mechanism": by_mech, "by_origin": by_origin,
            "latents": [{"key": k, "label": lbl} for k, lbl in LATENTS], "params": [p.public() for p in REG],
            "features": FEATURES, "attributes": [{"key": k, "label": lbl} for k, lbl in ATTRS], "channels": [{"key": k, "label": lbl} for k, lbl in CHANNELS]}


# ---------------------------------------------------------------- loading matrix
def _loading_matrix() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    Lm = np.zeros((len(COLS), len(_GEN)))
    mu = np.zeros(len(_GEN))
    sd = np.zeros(len(_GEN))
    for c, gi in enumerate(_GEN):
        p = REG[gi]
        mu[c], sd[c] = p.mu, p.sd
        for col, coef in p.loads:
            Lm[CI[col], c] += coef
    return Lm, mu, sd


_LM, _MU, _SD = _loading_matrix()


def _transform(x: np.ndarray) -> np.ndarray:
    out = np.empty_like(x)
    for c, gi in enumerate(_GEN):
        p = REG[gi]
        if p.tr == "sig":
            out[:, c] = p.lo + (p.hi - p.lo) / (1 + np.exp(-x[:, c]))
        elif p.tr == "logn":
            out[:, c] = np.clip(p.lo * np.exp(x[:, c]), p.lo * 0.15, p.hi)
        else:
            out[:, c] = p.lo + p.hi * x[:, c]
    return out


# ---------------------------------------------------------------- business features
def parse_hours(text: str | None) -> tuple[float, float] | None:
    """Parse '6am–10pm' / '06:00-22:00' / '24x7'. Returns (open, close) hours or None."""
    if not text:
        return None
    t = text.lower().replace("–", "-").replace("—", "-").replace(" to ", "-")
    if "24" in t and ("7" in t or "hour" in t):
        return (0.0, 24.0)
    m = re.findall(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if len(m) < 2:
        return None

    def conv(h, mi, ap):
        h = int(h) % 24
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return h + (int(mi) / 60 if mi else 0)

    a, b = conv(*m[0]), conv(*m[1])
    if b <= a:
        b += 12 if b + 12 > a and not m[1][2] else 24
    return (a, min(b, 24.0))


POSITION_ATTRS = {
    "Better service": {"staff": .2, "wait": .15, "personal": .15, "guidance": .1},
    "Premium experience": {"ambience": .25, "brand": .1, "comfort": .2, "amenities": .2, "ac": .15, "core_quality": .1},
    "Greater convenience": {"parking": .15, "speed": .2, "booking": .2, "delivery": .15, "wait": .1},
    "More specialised offering": {"expertise": .25, "core_quality": .15, "guidance": .15},
    "Extended operating hours": {"punctual": .1},
    "Better accessibility": {"step_free": .3, "safety": .1, "women_friendly": .1},
    "Lower price": {"portion": .1},
}


def business_features(arch_key: str, biz, comps, ref_price: float, quality_default: float, profile: dict | None,
                      awareness_target: float, offer: dict | None = None) -> tuple[np.ndarray, dict]:
    """Feature matrix F (J x len(FEATURES)) and per-business hour masks. Returns (F, meta)."""
    J = 1 + len(comps)
    F = np.zeros((J, len(FEATURES)))
    F[:, FI["inside"]] = 1.0
    F[0, FI["is_new"]] = 1.0
    F[1:, FI["established"]] = 1.0
    F[1:, FI["has_reviews"]] = 1.0  # assumption: incumbents have a review history; OSM does not say
    prices = np.array([biz.price] + [c.price if c.price else ref_price for c in comps], float)
    qual = np.array([biz.quality] + [c.quality if c.quality is not None else quality_default for c in comps], float)
    rel = prices / max(ref_price, 1e-9)
    F[:, FI["price_rel"]] = np.log(rel)
    F[:, FI["quality_c"]] = qual - 0.5
    F[:, FI["premium"]] = np.clip(rel - 1.0, 0, 2)
    F[:, FI["budget"]] = np.clip(1.0 - rel, 0, 1)
    F[0, FI["marketing"]] = awareness_target - 0.5
    attrs = np.repeat((qual - 0.5)[:, None], len(ATTRS), axis=1)
    sources = {"you": "derived from your positioning and quality score", "competitors": "assumed equal to competitor quality (unknown attributes)"}
    pos = (profile or {}).get("positioning") or []
    for lbl in pos:
        for a, d in POSITION_ATTRS.get(lbl, {}).items():
            attrs[0, AK[a]] += d
    for a, v in ((offer or {}).get("attributes") or {}).items():
        if a in AK and v is not None:
            attrs[0, AK[a]] = float(v) - 0.5
            sources["you"] = "your entered attributes, positioning elsewhere"
    F[:, len(FEATURES) - len(ATTRS):] = np.clip(attrs, -0.5, 0.5)
    dflt = DEFAULT_HOURS[arch_key]
    your = None
    if offer and offer.get("open_hour") is not None and offer.get("close_hour") is not None:
        your = (float(offer["open_hour"]), float(offer["close_hour"]))
    if your is None:
        your = parse_hours((profile or {}).get("operating_hours"))
    hours_src = "your stated hours" if your else "category default (assumption)"
    your = your or dflt
    hours = [your] + [dflt] * (J - 1)
    weekend = [True] * J
    if offer and offer.get("weekend_open") is False:
        weekend[0] = False
    mask = np.zeros((J, 24))
    for j, (o, c) in enumerate(hours):
        spans = [(o, c)] if c > o else [(o, 24.0), (0.0, c)]  # overnight hours wrap past midnight
        for h in range(24):
            mask[j, h] = sum(max(0.0, min(h + 1, b) - max(h, a)) for a, b in spans)
    F[:, FI["hours_span"]] = mask.sum(1) / 24 - 0.6
    F[:, FI["late_open"]] = np.array([1.0 if (c >= 22 or c <= o) else 0.0 for o, c in hours]) - 0.5
    F[:, FI["early_open"]] = np.array([1.0 if o <= 6 else 0.0 for o, _ in hours]) - 0.5
    F[:, FI["weekend_open"]] = np.array([1.0 if w else 0.0 for w in weekend]) - 0.5
    return F, {"hours_mask": mask, "weekend": np.array(weekend), "hours": hours, "hours_source": hours_src, "prices": prices, "quality": qual,
               "attr_sources": sources}


# ---------------------------------------------------------------- generation
@dataclass
class Genome:
    G: np.ndarray            # N x 615 parameter values (float32)
    Z: np.ndarray            # N x len(COLS) latent + covariates
    mode: np.ndarray
    dist: np.ndarray         # N x J road-distance estimate
    reach: np.ndarray        # N x J bool
    lin_scale: float
    channels: dict


def generate(rng: np.random.Generator, *, age: np.ndarray, female: np.ndarray, seg_keys: list[str], seg: np.ndarray, zone_pop: np.ndarray,
             zone_act: np.ndarray, lat: np.ndarray, lng: np.ndarray, zi: np.ndarray, blat: np.ndarray, blng: np.ndarray, circuity: float,
             max_km: float, seg_dt: np.ndarray, hh_size: float = 4.2, income_z: np.ndarray | None = None,
             dist_km: np.ndarray | None = None, walk_min: np.ndarray | None = None) -> Genome:
    from .geo import haversine_km

    N = age.size
    # ---- conditional latent draw: observed = (age_obs, income_obs)
    age_z = (age - 34.0) / 15.0
    # observed income signal: the agent's real national consumption rank (z) when the income layer ran, else segment mean
    inc_obs = income_z if income_z is not None else np.array([_SEG_INCOME.get(k, 0.0) for k in seg_keys])[seg] / 1.0
    o_idx = [NL, NL + 1]
    u_idx = list(range(NL))
    S_oo = CORR[np.ix_(o_idx, o_idx)]
    S_uo = CORR[np.ix_(u_idx, o_idx)]
    S_uu = CORR[np.ix_(u_idx, u_idx)]
    A = S_uo @ np.linalg.inv(S_oo)
    cond_cov = S_uu - A @ S_uo.T
    w, v = np.linalg.eigh((cond_cov + cond_cov.T) / 2)
    Lc = v @ np.diag(np.sqrt(np.clip(w, 1e-6, None)))
    obs = np.stack([np.clip(age_z, -2.5, 3.5), inc_obs], 1)
    lat_z = obs @ A.T + rng.standard_normal((N, NL)) @ Lc.T
    dens = np.log1p(zone_pop[zi] + 1.0)
    dens_z = (dens - dens.mean()) / (dens.std() + 1e-9)
    Z = np.concatenate([lat_z, age_z[:, None], (female.astype(float) - 0.5)[:, None] * 2, dens_z[:, None], age_z[:, None]], 1)

    # ---- generated parameters
    X = _MU[None, :] + Z @ _LM + rng.standard_normal((N, len(_GEN))) * _SD[None, :]
    Gg = _transform(X)
    G = np.zeros((N, GENOME_SIZE), np.float32)
    G[:, _GEN] = Gg.astype(np.float32)
    for k, i in LAT.items():
        G[:, KI[f"lt_{k}"]] = lat_z[:, i]

    # ---- travel mode from access x preference (multinomial logit)
    acc = np.stack([G[:, KI[f"mb_access_{m[0]}"]] for m in MODES], 1)
    prf = np.stack([G[:, KI[f"mb_pref_{m[0]}"]] for m in MODES], 1)
    base = np.log(MODE_BASE_SHARES)
    util = base + 3.0 * (acc - 0.5) + 2.0 * (prf - 0.5) + rng.gumbel(0, 1, (N, len(MODES)))
    mode = np.argmax(util, 1)
    speed = np.array([m[1] for m in MODES])[mode]
    mtol = np.array([m[2] for m in MODES])[mode]

    # ---- real geometry: distances to every business
    if dist_km is not None:  # road-network distance (OSRM) supplied by the caller
        dist = np.maximum(dist_km, 0.05)
    else:
        dist = np.maximum(haversine_km(lat[:, None], lng[:, None], blat[None, :], blng[None, :]) * circuity, 0.1)
    tol = seg_dt * mtol * G[:, KI["mb_dist_tol"]]
    reach = dist <= (max_km * tol)[:, None]
    tmin = dist / speed[:, None] * 60 + np.where(mode == 0, 0, 4)[:, None]  # + access / parking minutes for vehicles
    if walk_min is not None:  # walkers: routed walking time
        tmin = np.where((mode == 0)[:, None], walk_min, tmin)

    ev = {
        "ev_lat": lat, "ev_lng": lng, "ev_zone": zi, "ev_zone_population": zone_pop[zi], "ev_zone_activity": zone_act[zi], "ev_zone_density_z": dens_z,
        "ev_age": age, "ev_female": female.astype(float), "ev_household_size": np.clip(hh_size + Z[:, CI["family_load"]] * 0.9 + rng.normal(0, .5, N), 1, 10).round(),
        "ev_segment": seg, "ev_mode": mode, "ev_mode_speed": speed, "ev_dist_site": dist[:, 0], "ev_time_site": tmin[:, 0],
        "ev_reach_site": reach[:, 0].astype(float), "ev_in_market": np.zeros(N),
    }
    for k, v_ in ev.items():
        G[:, KI[k]] = v_
    # competitive geography
    for r in (0.5, 1.0, 1.5, 2.0, 3.0, 5.0):
        G[:, KI[f"cg_ring_{str(r).replace('.', '_')}km"]] = (dist[:, 1:] <= r).sum(1) if dist.shape[1] > 1 else 0
    order = np.argsort(dist, 1)
    ds = np.take_along_axis(dist, order, 1)
    ts = np.take_along_axis(tmin, order, 1)
    for n in range(10):
        G[:, KI[f"cg_d{n + 1:02d}"]] = ds[:, n] if n < ds.shape[1] else np.nan
        G[:, KI[f"cg_t{n + 1:02d}"]] = ts[:, n] if n < ts.shape[1] else np.nan
    G[:, KI["cg_n_reach"]] = reach.sum(1)
    G[:, KI["cg_rank_site"]] = (dist < dist[:, :1]).sum(1) + 1
    G[:, KI["cg_gap_site"]] = dist[:, 0] - (dist[:, 1:].min(1) if dist.shape[1] > 1 else dist[:, 0])
    nr = np.maximum(reach.sum(1), 1)
    G[:, KI["cg_mean_t"]] = np.where(reach, tmin, 0).sum(1) / nr
    return Genome(G=G, Z=Z, mode=mode, dist=dist, reach=reach, lin_scale=1.0, channels={"tmin": tmin})


# ---------------------------------------------------------------- utility assembly
UTIL_IDX = np.array([i for i, p in enumerate(REG) if p.mechanism == "utility" and p.feat and p.block != "importance"])
IMP_IDX = np.array([KI[f"im_{k}"] for k, _ in ATTRS])
EXP_IDX = np.array([KI[f"ex_{k}"] for k, _ in ATTRS])
CHANNEL_GROUPS = ["price", "quality", "travel", "time_fit", "attributes", "expectation", "trust_novelty", "lifestyle_fit"]
_TRUST_FEATS = {"is_new", "established", "has_reviews"}


def _zcols(G: np.ndarray, idx: np.ndarray) -> np.ndarray:
    X = G[:, idx].astype(np.float64)
    mu = np.nanmean(X, 0)
    sd = np.nanstd(X, 0) + 1e-9
    return np.nan_to_num((X - mu) / sd)


def mech_index(G: np.ndarray, mech: str, target_sd: float) -> np.ndarray:
    """Weighted sum of z-scored parameters belonging to a mechanism, scaled to ``target_sd``."""
    idx = np.array([i for i, p in enumerate(REG) if p.mechanism == mech and p.origin == "generated" and p.w != 0])
    if idx.size == 0:
        return np.zeros(G.shape[0])
    w = np.array([REG[i].w for i in idx])
    s = _zcols(G, idx) @ w
    sd = s.std()
    return s / sd * target_sd if sd > 0 else s


def relevance(arch_key: str) -> np.ndarray:
    core = set(_REL[arch_key].split())
    return np.array([1.0 if k in core else 0.25 for k, _ in ATTRS])


@dataclass
class UtilityParts:
    parts: dict          # channel -> N x J
    total: np.ndarray    # N x J (with -inf for out of reach)
    outside: np.ndarray  # N
    noise: np.ndarray    # N
    lin_contrib_w: np.ndarray  # P_util x J effective weights (for per-param attribution)
    lin_scale: float


def assemble_utility(arch_key: str, gen: Genome, F: np.ndarray, meta: dict, P: dict, ref_price: float, seg_psens: np.ndarray,
                     *, lin_target_sd: float = 0.45, beta_time: float = 1.2, beta_attr: float = 2.2, beta_exp: float = 2.0) -> UtilityParts:
    G = gen.G
    N, J = G.shape[0], F.shape[0]
    prices = meta["prices"]
    g = lambda k: G[:, KI[k]].astype(float)  # noqa: E731
    c = lambda k: g(k) - 0.5  # noqa: E731  centred 0-1 parameter
    # ---- price: WTP, its flexibility and caps; sensitivity with anchoring; loss aversion above WTP
    wtp = ref_price * g("ec_wtp_multiple") * (1 + 0.25 * c("ec_budget_flex")) * (1 + 0.15 * g("ec_corporate_benefit"))
    wtp_cap = ref_price * g("ec_spend_monthly_cat")  # hard ceiling of monthly category spend
    psens = (seg_psens * g("ec_price_sens") * (1 + 0.2 * c("ec_ref_anchor") + 0.2 * c("bh_anchoring") + 0.15 * c("ec_ref_drift")
             + 0.3 * c("ec_affordability_stress")) * (1 + 0.15 * g("ec_student_discount_elig") + 0.1 * g("ec_senior_discount_elig")))
    la = g("ec_loss_aversion") * (1 + 0.3 * c("bh_loss_framing") + 0.3 * c("bh_mental_accounting") + 0.4 * c("co_budget_cap_hard"))
    over = np.log(np.maximum(prices[None, :] / wtp[:, None], 1.0))
    shock = np.maximum(prices[None, :] / (wtp * g("ec_sticker_shock"))[:, None] - 1.0, 0)
    capped = (prices[None, :] > wtp_cap[:, None]) * (1.5 + 2.0 * g("co_budget_cap_hard"))[:, None]
    price = -P["beta_price"] * psens[:, None] * np.log(prices[None, :] / ref_price) - la[:, None] * over - 2.0 * shock - capped
    # quality
    quality = np.repeat((P["beta_quality"] * (meta["quality"] - 0.5))[None, :], N, 0)
    # ---- travel: distance decay x personal tolerance x friction (13 travel parameters), plus time cost and trip-time ceiling
    friction = np.exp(mech_index(G, "travel", 0.2))
    decay = P["distance_decay"] * friction / np.maximum(g("mb_dist_tol"), 0.2)
    tmin = gen.channels["tmin"]
    tmax = g("mb_max_trip_min")
    visits = 12.0 if arch_key == "membership" else 1.0
    time_cost = 2 * visits * tmin / 60 * g("mb_value_of_time")[:, None] / max(ref_price, 1.0)
    walk_pen = np.where(gen.mode[:, None] == 0, np.clip(gen.dist / g("mb_walk_tolerance")[:, None] - 1, 0, 3), 0)
    travel = -decay[:, None] * gen.dist - 0.8 * np.clip(tmin / tmax[:, None] - 1.0, 0, 3) - 0.35 * np.clip(time_cost, 0, 3) - 0.5 * walk_pen
    # time fit: weekday/weekend availability vs opening mask
    wd = np.stack([G[:, KI[f"tm_wd_{h:02d}"]] for h in range(24)], 1).astype(float)
    we = np.stack([G[:, KI[f"tm_we_{h:02d}"]] for h in range(24)], 1).astype(float)
    dw = np.stack([G[:, KI[f"tm_day_{d}"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")], 1).astype(float)
    wd_w = dw[:, :5].sum(1, keepdims=True)
    we_w = dw[:, 5:].sum(1, keepdims=True)
    mask = meta["hours_mask"]
    fit_wd = (wd @ mask.T) / np.maximum(wd.sum(1, keepdims=True), 1e-6)
    fit_we = (we @ mask.T) / np.maximum(we.sum(1, keepdims=True), 1e-6) * meta["weekend"][None, :]
    fit = (fit_wd * wd_w + fit_we * we_w) / np.maximum(wd_w + we_w, 1e-6)
    rigidity = np.clip(0.5 + g("co_time_window") + 0.5 * mech_index(G, "time_fit", 0.5), 0.2, 2.5)
    time_fit = beta_time * rigidity[:, None] * (fit - 0.75)
    # attributes: importance x relevance x attribute level
    rel = relevance(arch_key)
    imp = G[:, IMP_IDX].astype(float) * rel[None, :]
    attr = F[:, len(FEATURES) - len(ATTRS):]
    attributes = beta_attr * (imp @ attr.T) / rel.sum()
    # expectation gaps: penalty if attribute level below the agent's minimum, weighted by importance
    thr = G[:, EXP_IDX].astype(float) - 0.5
    gap = np.maximum(thr[:, None, :] - attr[None, :, :], 0)  # N x J x A
    expectation = -beta_exp * (gap * imp[:, None, :]).sum(2) / rel.sum()
    # linear modulators: z(param) * w * feature
    Zu = _zcols(G, UTIL_IDX)
    Wf = np.array([[REG[i].w * F[j, FI[REG[i].feat]] for j in range(J)] for i in UTIL_IDX])  # P_u x J
    is_trust = np.array([REG[i].feat in _TRUST_FEATS for i in UTIL_IDX])
    raw_trust = Zu[:, is_trust] @ Wf[is_trust]
    raw_life = Zu[:, ~is_trust] @ Wf[~is_trust]
    tot = raw_trust + raw_life
    sd = float(np.std(tot - tot.mean(1, keepdims=True))) or 1.0
    scale = lin_target_sd / sd
    trust = raw_trust * scale
    life = raw_life * scale
    parts = {"price": price, "quality": quality, "travel": travel, "time_fit": time_fit, "attributes": attributes,
             "expectation": expectation, "trust_novelty": trust, "lifestyle_fit": life}
    total = sum(parts.values())
    total = np.where(gen.reach, total, -np.inf)
    outside = P["outside_utility"] + mech_index(G, "outside", 0.35)
    noise = np.clip(1.0 + mech_index(G, "noise", 0.18), 0.6, 1.6)
    return UtilityParts(parts=parts, total=total, outside=outside, noise=noise, lin_contrib_w=Wf * scale, lin_scale=scale)


def channel_awareness(arch_key: str, G: np.ndarray) -> np.ndarray:
    """Per-agent multiplier on paid-awareness hazard from 48 channel parameters x the category's media mix."""
    mix = _MIX[arch_key]
    m = np.array([mix.get(k, 0.02) for k, _ in CHANNELS])
    m = m / m.sum()
    eff = np.stack([G[:, KI[f"ch_{k}_reach"]] * G[:, KI[f"ch_{k}_trust"]] * G[:, KI[f"ch_{k}_resp"]] for k, _ in CHANNELS], 1).astype(float)
    a = eff @ m
    a = a * np.exp(mech_index(G, "awareness", 0.25))
    return a / max(a.mean(), 1e-9)


def participation_index(arch_key: str, G: np.ndarray, month0: int, horizon_days: int) -> np.ndarray:
    focal, subs, comp = (s.split() for s in _CAT_ROLE[arch_key])
    aff = lambda names: np.mean([G[:, KI[f"af_{c}"]] for c in names], 0).astype(float)  # noqa: E731
    z = lambda x: (x - x.mean()) / (x.std() + 1e-9)  # noqa: E731
    related = set(focal) | set(subs) | set(comp)
    other = [c_ for c_ in CATEGORIES if c_ not in related]
    # share-of-wallet / share-of-time: strong interests elsewhere slightly reduce participation in this category
    idx = (0.55 * z(aff(focal)) + 0.15 * z(aff(comp)) - 0.15 * z(aff(subs)) - 0.08 * z(aff(other))
           + mech_index(G, "participation", 0.35))
    months = [(month0 + int(d / 30.4)) % 12 for d in range(0, horizon_days, 30)] or [month0]
    names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    seas = np.mean([G[:, KI[f"tm_month_{names[m]}"]] for m in months], 0).astype(float)
    return idx + np.log(seas)


def outside_substitutes(arch_key: str, G: np.ndarray) -> np.ndarray:
    _, subs, _ = (s.split() for s in _CAT_ROLE[arch_key])
    x = np.mean([G[:, KI[f"af_{c}"]] for c in subs], 0).astype(float)
    return 0.3 * (x - x.mean()) / (x.std() + 1e-9)


# ---------------------------------------------------------------- explanation of one agent
def explain(i: int, gen: Genome, up: UtilityParts, names: list[str], final_choice: int, G_pct: np.ndarray | None = None) -> dict:
    G = gen.G
    J = up.total.shape[1]
    opts = []
    for j in range(J):
        reach = bool(gen.reach[i, j])
        opts.append({"idx": j, "name": names[j], "reachable": reach, "dist_km": round(float(gen.dist[i, j]), 2),
                     "time_min": round(float(gen.channels["tmin"][i, j]), 1),
                     "utility": round(float(up.total[i, j]), 3) if reach else None,
                     "parts": {k: round(float(v[i, j]), 3) for k, v in up.parts.items()}})
    reach_opts = [o for o in opts if o["reachable"]]
    reach_opts.sort(key=lambda o: -o["utility"])
    top = reach_opts[:6]
    if all(o["idx"] != 0 for o in top):
        top.append(opts[0])
    if len(top) < 3:  # out-of-range agent: show the nearest options it will not consider
        for o in sorted((o for o in opts if not o["reachable"] and o not in top), key=lambda o: o["dist_km"])[:3 - len(top)]:
            top.append(o)
    # driver attribution: chosen (or best) vs your business
    ref = final_choice if final_choice >= 0 else (reach_opts[0]["idx"] if reach_opts else 0)
    Zu = _zcols(G, UTIL_IDX)[i]
    diff_w = up.lin_contrib_w[:, ref] - up.lin_contrib_w[:, 0]
    contrib = Zu * diff_w
    drivers = []
    for k in np.argsort(-np.abs(contrib))[:8]:
        p = REG[UTIL_IDX[k]]
        drivers.append({"key": p.key, "label": p.label, "feat": p.feat, "value": float(G[i, UTIL_IDX[k]]), "z": round(float(Zu[k]), 2),
                        "effect": round(float(contrib[k]), 3)})
    vals = G[i].astype(float)
    pct = G_pct[i].tolist() if G_pct is not None else None
    return {
        "agent": i, "final_choice": final_choice, "outside_utility": round(float(up.outside[i]), 3), "noise_scale": round(float(up.noise[i]), 3),
        "options": top, "drivers_vs_you": drivers, "ref_option": ref,
        "genome": [None if not np.isfinite(v) else round(v, 4) for v in vals], "percentile": pct,
    }


def percentiles(G: np.ndarray) -> np.ndarray:
    """Per-parameter population percentile (0-100, uint8) for every agent — used by the X-ray and DNA matrix."""
    N, P_ = G.shape
    out = np.empty((N, P_), np.uint8)
    pos = np.arange(N, dtype=np.int32)
    for c0 in range(0, P_, 64):  # column chunks keep peak memory low on small servers
        X = np.nan_to_num(G[:, c0:c0 + 64], nan=-1e9)
        order = np.argsort(X, 0, kind="stable").astype(np.int32)
        ranks = np.empty_like(order)
        np.put_along_axis(ranks, order, pos[:, None], axis=0)
        out[:, c0:c0 + 64] = np.clip(np.round(ranks / max(1, N - 1) * 100), 0, 100).astype(np.uint8)
    return out


EXPLICIT = {
    "ec_wtp_multiple", "ec_budget_flex", "ec_corporate_benefit", "ec_spend_monthly_cat", "ec_price_sens", "ec_ref_anchor", "bh_anchoring",
    "ec_ref_drift", "ec_affordability_stress", "ec_student_discount_elig", "ec_senior_discount_elig", "ec_loss_aversion", "bh_loss_framing",
    "bh_mental_accounting", "co_budget_cap_hard", "ec_sticker_shock", "mb_dist_tol", "mb_max_trip_min", "mb_value_of_time", "mb_walk_tolerance",
    "co_time_window", "rt_satisfaction_sens", "rt_habit_rate", "rt_habit_cap", "rt_churn_base", "so_wom_propensity", "so_wom_susceptibility",
}
_MECH_INDEXED = {"participation", "outside", "noise", "awareness", "social", "retention", "travel", "time_fit"}


def audit() -> dict:
    """How each of the 615 parameters reaches a decision. Raises if any generated parameter is unused."""
    use: dict[str, list[str]] = {}
    for p in REG:
        if p.origin == "evidence":
            how = "measured from real geometry / population (placement, distances, travel)"
        elif p.origin == "latent":
            how = "latent trait driving generated parameters"
        elif p.key in EXPLICIT or p.block in ("temporal", "importance", "expectation", "channels", "affinity") or p.key.startswith("mb_access_") or p.key.startswith("mb_pref_"):
            how = f"explicit term in {p.mechanism}"
        elif p.w != 0 and p.mechanism == "utility" and p.feat:
            how = f"utility term x business feature '{p.feat}'"
        elif p.w != 0 and p.mechanism in _MECH_INDEXED:
            how = f"weighted into {p.mechanism} index"
        else:
            raise AssertionError(f"parameter {p.key} is not consumed by the model")
        use.setdefault(how.split(" x ")[0].split(" '")[0], []).append(p.key)
    return {k: len(v) for k, v in use.items()}


def month_now() -> int:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).month - 1


__all__ = ["GENOME_SIZE", "REG", "KEYS", "KI", "generate", "assemble_utility", "business_features", "explain", "percentiles",
           "channel_awareness", "participation_index", "outside_substitutes", "registry_public", "MODES", "mech_index", "parse_hours",
           "month_now", "CHANNEL_GROUPS", "math"]
