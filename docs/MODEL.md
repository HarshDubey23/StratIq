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
