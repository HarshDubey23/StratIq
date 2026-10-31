# StrataIQ simulation model (`siq-choice-1.1`)

Source: `backend/app/engine/`. Tests: `backend/tests/test_engine.py`.

## 1. Inputs

| Input | Origin | Label |
|---|---|---|
| Demand zones (hex cells, ~250–600 m) with population | WorldPop total over the catchment, placed by OSM building counts (dasymetric) | official estimate / derived |
| Activity points (stations, offices, colleges, hospitals, malls, attractions) | OSM | observed |
| Competitors (location, optional price, optional quality) | OSM + user | observed / user |
| Your price, quality claim, marketing, capacity, costs | user | user |
| Behaviour parameters per archetype | `categories/archetypes.py` | assumption (documented low/high) |

## 2. Archetypes (economic model types)

| Key | Unit | Capacity |
|---|---|---|
| membership | active members / month | max members |
| dine_in | visits / month | seats × turns/day × open days |
| takeaway | orders / month | max orders/day × open days |
| retail | baskets / month | max baskets/day × open days |
| appointment | appointments / month | stations × slots/day × open days |
| lodging | room-nights / month | rooms × 30 |

## 3. Equations

For zone z, segment s ∈ {budget, mainstream, premium}, alternative j (0 = you):

```
W_z   = pop_z                                   (residents archetypes)
W_z   = pop_z + activity_z · activity_equivalent (residents_and_activity archetypes)
N_zs  = W_z · participation · share_s
F_sj  = 1 − Φ((ln p_j − ln(m_s · p_ref)) / σ)                     affordability
V_zsj = β_q (q_j − 0.5) − β_p k_s ln(p_j / p_ref) − (λ / t_s) d_zj + ln a_j
A_zsj = F_sj · exp(V_zsj) · 1[d_zj ≤ max_km · t_s]
P_zsj = A_zsj / (exp(U_0) + Σ_k A_zsk)
D_j   = frequency · Σ_zs N_zs P_zsj
Q_0   = min(D_0, K)
```

* `d_zj` = haversine distance × circuity (default 1.3), floored at 0.15 km. Labelled as an approximation.
* `a_0 = a_base + (1 − a_base)(1 − 2^(−spend / half_saturation))`; competitors `a_j = 1` (established).
* `p_ref`: user-entered typical price → median of recorded competitor prices → baseline scenario price (flagged).
* Unknown competitor price = `p_ref × competitor_price_ratio`; unknown quality = `competitor_quality`.
* Segments: shares 0.45/0.40/0.15, WTP multipliers 0.75/1.05/1.7, price-sensitivity multipliers 1.4/1.0/0.6, distance tolerance 0.8/1.0/1.3.

## 4. Economics (monthly)

```
Revenue = p · Q;  Variable = v · Q  (v user-entered, else p · variable_cost_ratio)
Fixed   = rent + payroll + utilities + other_fixed + marketing
Profit  = Revenue − Variable − Fixed
Break-even units = Fixed / (p − v);  Payback = startup / Profit (if Profit > 0)
```
Excluded and shown on every result: taxes, financing, depreciation, working capital, deposits.

## 5. Uncertainty

`participation, frequency, β_p, β_q, λ, a_base, competitor_quality, competitor_price_ratio, σ, U_0` (and the variable-cost
ratio when not user-entered) are drawn from triangular distributions over [low, mode, high]; default 800 draws, seed stored
with the run. Reported: mean, P10, P50, P90 of profit, units and revenue; P(profit < 0); P(capacity-bound); histogram.
User-overridden parameters use ±15% around the entered value.

Sensitivity: one-at-a-time low/high (tornado), 15-point price sweep, marketing sweep, five stress tests, Spearman ρ of each
parameter vs profit across draws, and a bisection for the participation rate at which profit = 0.

## 6. Invariants tested

Probabilities non-negative and < 1 per zone-segment; captured units ≤ in-market units; higher own price ⇒ lower demand;
added competitor ⇒ lower demand; more marketing ⇒ higher demand; capacity binds; finance identities; reproducible Monte Carlo;
every archetype runs end to end.

## 7. What this model is not

It is not calibrated on observed sales. Probabilities are conditional on the assumed ranges. Synthetic agents are a
visual sample, not people. Competitor capacity and spill-over are not modeled.

## 8. Agent-based live market (`engine/abm.py`)

Every run also simulates a **live market** of synthetic people (default 6,000 agents, 84 days):

* **Placement at real density** — agents are sampled from demand zones in proportion to WorldPop population
  (distributed over OSM buildings) plus activity points; each agent represents `total / N` resident-equivalents.
* **Profile** — age and sex from the WorldPop age–sex structure of the catchment (default pyramid if unavailable),
  segment, individual willingness to pay (lognormal), price/quality sensitivity, travel mode (7 modes, segment-dependent),
  distance tolerance, digital adoption (age-dependent), word-of-mouth susceptibility, loyalty, novelty, time preference,
  category affinity by age and sex, purchase frequency.
* **Daily dynamics** — awareness of the new business spreads by paid reach (hazard calibrated so that one month of
  marketing reaches the static model's awareness, scaled by digital adoption), word of mouth from customers in the same
  zone, and storefront signage nearby; in-market agents decide with their own random utility (price vs their WTP, quality,
  distance, habit, congestion memory, Gumbel taste noise) including a "none" option; membership agents reconsider monthly
  with churn/switching; capacity turns people away and they remember it.
* **Outputs** — daily and weekly series (customers, awareness, competitor volume, turned-away demand), month-by-month
  units and operating profit during ramp-up, customer composition (segments, travel modes), trip distances, and
  animation frames for the map. Seeded and reproducible.

## 9. Factor Intelligence Engine (`factors/`)

615 factor definitions across 10 domains (geography, demographics, economics, behaviour, mobility, competition,
operations, marketing, retention, external). Each declares scope, source and role (agent profile, choice model,
economics, output, evidence, or future data). Per location and run every factor gets a status: computed (live data),
user, assumed, simulated, pending, or unavailable. Factors with no connected data source are shown empty — never invented.

## Field evidence (ground truth from a field researcher)

`engine/field.py` turns street-intercept interviews into evidence tuples `(value, low, high, "field", source)` that
`ResolvedParams.from_archetype` already understands. Field evidence outranks published/derived evidence; explicit user
overrides still win. A parameter is only replaced once enough answers exist:

| Parameter | Estimate | Interval | Minimum n |
|---|---|---|---|
| `participation` | share of interviewees who use the category | Wilson 90 % | 8 interviews |
| `frequency` | mean stated visits per month among users (not for structural frequencies, e.g. memberships) | mean ± 1.645·SE | 5 users |
| `max_km` | 80th percentile of stated travel distance | P60–P95 | 6 users |
| `wtp_sigma` | log-SD of stated maximum prices, clamped 0.15–1.0 | ×0.8–×1.25 | 6 answers |

Visited competitors enter the choice model with their observed price and the researcher's 1–5 rating mapped to 0–1
quality. Footfall counts and rent quotes are summarised for the decision but not converted into demand. Intercept
samples are not random samples of the catchment; every source string says so.
