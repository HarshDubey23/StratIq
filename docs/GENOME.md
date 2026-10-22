# Agent Genome — 615 parameters per synthetic agent

Every live-market run places **10,000 synthetic agents** at real population density and gives each one a
**615-parameter genome** (6.15 million parameters per run). Code: `backend/app/engine/genome.py`; tests:
`backend/tests/test_genome.py`. Full registry: `GET /api/v1/genome/registry`.

> Agents are synthetic. Their parameters are documented modelling assumptions conditioned on real local
> evidence — not measurements of real people. The genome makes assumptions explicit and inspectable; it does
> not make them true. The field survey kit exists to replace them with real answers.

## Where the 615 come from

| Origin | Count | How |
|---|---:|---|
| Evidence | 46 | Position drawn from WorldPop/OSM density; age–sex from WorldPop where available; road-distance and travel time to every mapped business; competitor rings and nearest-option distances. |
| Latent traits | 16 | Income, price consciousness, quality orientation, convenience, novelty seeking, social connectedness, digital nativity, health, status, time poverty, habit, risk aversion, family load, mobility, neighbourhood attachment, planning. Drawn from a documented correlation matrix **conditioned on the agent's age and income segment** (conditional multivariate normal). |
| Generated | 553 | Each is `x = mu + loadings · z + sd · eps`, then a bounded transform (logistic to 0–1, or log-normal around a centre). Loadings reference the latent traits and observed covariates (age, sex, zone density). |

Blocks: placement & geography (16), latent (16), economics & price psychology (52), time availability (67: 24 weekday
hours, 24 weekend hours, 7 days, 12 months), attribute importance (40), expectation thresholds (40), media channels
(48: 16 channels × exposure/trust/response), social influence (28), mobility (28), competitive geography (30),
decision psychology (48), retention (28), category affinities (40), lifestyle & needs (50), digital behaviour (34),
constraints & context (50).

## How every parameter reaches a decision

`genome.audit()` classifies all 615 and **fails the test suite if any generated parameter is unused**.

| Mechanism | What it does |
|---|---|
| Price channel | `−β_p · sens_i · ln(p/p_ref) − λ_i · ln⁺(p/WTP_i) − shock − cap`. WTP, flexibility, spend cap, sticker-shock, anchoring, loss aversion, mental accounting are all per agent. |
| Travel channel | `−decay · friction_i / tol_i · d_ij − ceiling(t_ij / t_max,i) − value_of_time_i · t_ij`. Friction is a weighted index of 13 travel parameters; mode is chosen from 7 access × 7 preference parameters. |
| Opening-hours fit | Overlap of the agent's 48 hourly availabilities (weighted by 7 day parameters) with each business's opening mask; scaled by personal time rigidity. |
| Attributes | `β_a · Σ_k importance_ik · relevance_k · attr_jk` over 40 attributes; relevance depends on the business type. |
| Expectation gap | Penalty when a business is below the agent's minimum on an attribute, weighted by importance. |
| Utility modulators | ~170 parameters × a business feature (is new, established, has reviews, price tier, hours, marketing…) e.g. review reliance × "has reviews" favours incumbents. Scaled to a documented taste-heterogeneity SD (0.45). |
| Participation | Focal/complement/substitute category affinities, seasonality for the simulated months, lifestyle and goal parameters → logit shift around the category's participation rate (population mean preserved). |
| Outside option | Substitute affinities and home-based alternatives make "buy nothing" more attractive for some agents. |
| Awareness | 48 channel parameters × the category's media mix → each agent's daily hazard of hearing about you. |
| Word of mouth | Sender propensity × receiver susceptibility × local customer density. |
| Retention | Personal churn hazard, habit formation rate and cap, switching resistance, satisfaction sensitivity to expectation gaps. |
| Noise | Personal decision-noise scale. |

## Calibration against incumbents (revealed demand)

Businesses that exist and survive need customers. Before the run, StrataIQ simulates the market **without** you and
measures the demand reaching incumbents in the inner catchment (≤60% of the radius). If the median incumbent is below a
survival floor (default 40% of the category's default capacity), participation is scaled up, bounded at ×2.5, and the
adjustment is reported on the run. It never lowers demand. Disable with `param_overrides.calibrate_incumbents = 0`.
This is an assumption-anchored consistency check, not a calibration against observed sales.

## Inspecting it

* **Agent X-ray** — click any dot on the live map: the agent's full genome (coloured by population percentile), the
  utility of each option broken into 8 channels, the outside option, and the individual parameters that pushed it
  away from you.
* **Market DNA** — a stratified sample of agents × 615 parameters, grouped by outcome; the parameters that most
  separate your customers from competitors' customers; where you win and lose by channel; parameters working against
  you; calibration.
* **Field survey kit** — a questionnaire (Van Westendorp price questions, hours, travel, top attributes for the
  category, awareness channels, trial and switching) that measures the assumptions this result is most sensitive to.

## Reproducibility

Placement uses seed+101, the genome seed+7, dynamics seed+211. A run's population is rebuilt exactly from its stored
inputs and seed when it is not in the in-memory cache (tested).

## Limits

* Distributions, correlations and loadings are assumptions, not estimated from survey microdata (none is used yet).
* Competitor attributes, hours and reviews are unknown in OpenStreetMap and are assumed; they are labelled as such.
* The 615 parameters are a structured way to represent heterogeneity; more parameters do not imply more accuracy.
  Accuracy can only be claimed after comparing forecasts with real outcomes (Monitoring tab).
