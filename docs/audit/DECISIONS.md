# StratIq Architectural & Scientific Decisions Log

This document tracks modeling, architectural, and scientific decisions observed in the StratIq repository, accompanied by independent auditor evaluations.

---

### [DEC-001]: Choice Model Engine — Vectorized Multinomial Logit (MNL) with Outside Option
- **Date**: Baseline (2026-10-31)
- **Component**: `backend/app/engine/model.py`, `backend/app/engine/simulate.py`
- **Specification**:
  ```
  V_zsj = beta_q * (q_j - 0.5) - beta_p * k_s * ln(p_j / p_ref) - (lambda / t_s) * d_zj + ln(a_j)
  A_zsj = F_sj * exp(V_zsj) * 1[d_zj <= max_km * t_s]
  P_zsj = A_zsj / (exp(U_0) + sum_k A_zsk)
  ```
- **Auditor Assessment**: **APPROVED WITH DISCLOSURES**
- **Rationale**:
  The mathematical formulation is internally consistent, enforces valid probability simplex constraints ($0 \le P \le 1$), respects distance decay, and handles outside options rigorously. Monte Carlo draws correctly propagate parameter uncertainty.
- **Scientific Limitation**:
  $\beta_p, \beta_q, \lambda, U_0$ are defined as heuristic priors across archetypes rather than estimated via discrete choice econometric estimation against regional transaction microdata. The codebase transparently documents this in `MODEL.md`.

---

### [DEC-002]: Factor Intelligence Engine — 615-Factor Ontology across 10 Domains
- **Date**: Baseline (2026-10-31)
- **Component**: `backend/app/factors/registry.py`, `backend/app/factors/compute.py`
- **Specification**:
  10 domains, 615 factor definitions with explicit scopes (`zone`, `agent`, `business`, `competitor`, `market`), sources (`osm`, `worldpop`, `derived`, `user`, `assumption`, `simulated`, `reserved`), and roles (`choice`, `agent`, `finance`, `output`, `context`, `reserved`).
- **Auditor Assessment**: **FLAGGED FOR USER-FACING DISCLOSURE**
- **Rationale**:
  The schema and role separation are exceptionally well-structured. Missing factors are safely filled as `"unavailable"` rather than fabricated. However, 193 of 615 factors (31.4%) are currently inactive placeholders (`reserved`), and 98 active parameters rely on uncalibrated heuristics. Documentation must clearly report active vs reserved factor counts.

---

### [DEC-003]: Spatial Allocation via Dasymetric OSM Building Distribution
- **Date**: Baseline (2026-10-31)
- **Component**: `backend/app/providers/osm.py`, `backend/app/providers/population.py`
- **Specification**:
  WorldPop gridded aggregate counts over the catchment are placed into hexagonal zones proportional to OSM building footprint counts, with fallbacks to uniform spatial distribution if building polygons are unavailable.
- **Auditor Assessment**: **APPROVED**
- **Rationale**:
  Dasymetric spatial allocation using building counts is an established geographic information science technique when fine-grained census block data is unavailable. Fallbacks to uniform distribution are explicitly logged in evidence metadata and flagged in decision outputs (`_gaps`).

---

### [DEC-004]: Synthetic Population Generation Without Joint Microdata (Legacy ABM)
- **Date**: Baseline (2026-10-31)
- **Component**: `backend/app/engine/abm.py`
- **Specification**:
  Agents are drawn from 1D WorldPop age-sex pyramids (or fallback Indian urban pyramid) and assigned customer segments, travel modes, and latent psychological parameters independently.
- **Auditor Assessment**: **FLAGGED (SUPERSEDED BY DEC-009 PENDING WIRING)**
- **Rationale**:
  Univariate independent Beta draws create synthetic agents lacking joint covariance structure. Primary agent has implemented an IPF engine in `engine/population/` to solve this, but runtime wiring into `abm.py` is pending.

---

### [DEC-005]: Asymmetric Competitor Capacity Representation
- **Date**: Baseline (2026-10-31)
- **Component**: `backend/app/engine/abm.py`
- **Specification**:
  Capacity turn-away, queue rejection, and congestion penalties are evaluated exclusively for the user's business (`choice == 0`). Competitors are modeled with infinite capacity.
- **Auditor Assessment**: **FLAGGED (SIMULATION BIAS)**
- **Rationale**:
  This creates an asymmetric market where the user's business suffers congestion attrition, but can never capture overflow or spillover demand from congested competitors. Must be disclosed or balanced with archetype-level competitor capacity bounds.

---

### [DEC-006]: Specificity-Weighted Category Resolution Hierarchy
- **Date**: Checkpoint 2 (2026-10-31)
- **Component**: `backend/app/categories/resolver.py`, `backend/app/categories/taxonomy.py`
- **Specification**:
  Query token matching incorporates domain-specific qualifiers (`SPECIFIC_QUALIFIERS`), assigning a +0.20 boost to specific clinical/retail terms (`dentist`, `orthodontist`, `physio`, `spa`) and a -0.30 penalty to generic parent terms (`clinic`, `store`).
- **Auditor Assessment**: **APPROVED — VERIFIED**
- **Rationale**:
  Successfully resolves [SIQ-ISSUE-001]. Multi-token queries such as `"cosmetic dental clinic"` now deterministically select `dentist` over generic `clinic`. Tested across 31 regression cases in `tests/test_categories.py`.

---

### [DEC-007]: Monthly Financial Operating Model
- **Date**: Baseline (2026-10-31)
- **Component**: `backend/app/engine/finance.py`
- **Specification**:
  Linear operating economics: $Revenue = p \cdot Q$, $Variable = v \cdot Q$, $Fixed = rent + payroll + utilities + other + marketing$. Discloses exclusion of taxes, debt servicing, depreciation, and working capital.
- **Auditor Assessment**: **APPROVED**
- **Rationale**:
  Clean, mathematically correct operating contribution identities. Disclosures are prominently surfaced in both code constants (`EXCLUDED`) and UI reports.

---

### [DEC-008]: 6-Tier Competitor Relationship Framework
- **Date**: Checkpoint 2 (2026-10-31)
- **Component**: `backend/app/categories/competitors.py`, `backend/app/services/runs.py`, `backend/app/api/serialize.py`
- **Specification**:
  Classifies nearby POIs into 6 distinct tiers relative to the target business category:
  `direct`, `partial_service`, `indirect_substitute`, `adjacent`, `contextual`, `irrelevant`.
  Only `direct` and `partial_service` enter the choice utility matrix in `competitors_for(direct_only=True)`. Spas and beauty salons are strictly classified as `irrelevant` for dental clinics.
- **Auditor Assessment**: **APPROVED — VERIFIED**
- **Rationale**:
  Prevents unrelated commercial facilities (e.g. spas, retail shops) from contaminating competitor sets in specialized healthcare simulations. Integrated into serialization and simulation filtering with 100% test coverage.

---

### [DEC-009]: Disconnected IPF Population Synthesis Architecture
- **Date**: Checkpoint 2 (2026-10-31)
- **Component**: `backend/app/engine/population/` (`ipf.py`, `synthesis.py`, `validation.py`)
- **Specification**:
  Entropy-minimizing Iterative Proportional Fitting (IPF) against 17 Census/WorldPop age-sex bands and zone totals, with household cohabitant alignment. Supports Mode A (calibrated weights) and Mode B (10,000 deterministic records).
- **Auditor Assessment**: **APPROVED MATHEMATICALLY; FLAGGED ARCHITECTURALLY (SIQ-ISSUE-007)**
- **Rationale**:
  The mathematical formulation in `ipf.py` and `synthesis.py` is rigorous, converges accurately, and satisfies conservation of margins. However, because it is not wired into `abm.py` or `services/runs.py`, the active live market simulation still uses uncalibrated legacy sampling.

---

### [DEC-010]: Procedure-Level Dental Clinical Feasibility Model
- **Date**: Checkpoint 2 (2026-10-31)
- **Component**: `backend/app/engine/economics/dental.py`
- **Specification**:
  Replaces single-price appointment assumption with a 7-procedure clinical mix (Consultations, Scaling, Fillings, Endodontics, Crowns, Extractions, Orthodontics), clinical chair-minute capacity constraints, consumable and lab cost structures, and Capex payback metrics.
- **Auditor Assessment**: **APPROVED MATHEMATICALLY; FLAGGED ARCHITECTURALLY (SIQ-ISSUE-007)**
- **Rationale**:
  Addresses the clinical reality that dental clinics generate revenue from heterogeneous procedures with drastically different chair times and lab costs. Validated with 4 unit tests. Requires runtime wiring into `services/runs.py` to activate for user dental projects.
---

### [DEC-011]: McFadden Conditional Logit Maximum Likelihood Estimation Engine
- **Date**: Checkpoint 3 (2026-10-31)
- **Component**: `backend/app/engine/choice/conditional_logit.py`, `backend/app/engine/choice/validation.py`
- **Specification**:
  Analytical gradient and observed Fisher Information matrix computation for McFadden's Conditional Logit model using `scipy.optimize.minimize(method="L-BFGS-B")`. Provides McFadden pseudo-$R^2$, adjusted pseudo-$R^2$, AIC, BIC, z-statistics, p-values, and holdout cross-validation (Brier score, ECE calibration curve, Top-1 accuracy).
- **Auditor Assessment**: **APPROVED MATHEMATICALLY; FLAGGED ARCHITECTURALLY (SIQ-ISSUE-007)**
- **Rationale**:
  The mathematical derivation of negative log likelihood, score gradient, and Fisher information is textbook McFadden (1974) and Train (2009). The unit tests demonstrate exact parameter recovery within 99% confidence intervals on synthetic choice data ($N=3,500$). However, like IPF and dental economics, it is currently an isolated module uncalled by `services/runs.py`.

---

### [DEC-012]: Deterministic 6x6 Customer Cohort Markov Transition Matrix in ABM
- **Date**: Checkpoint 3 (2026-10-31)
- **Component**: `backend/app/engine/abm.py` (`build_cohort_transition_matrix`, `run_cohort_transition_baseline`)
- **Specification**:
  Constructs a row-stochastic 6x6 transition matrix $T_t$ across 6 customer states: Unaware, Aware, Considering, Trial, Loyal, Churned. Propagates $n_{t+1} = n_t T_t$ with word-of-mouth feedback, guaranteeing zero Monte Carlo variance and strict population conservation. Exposed directly in `run_abm` as `cohort_baseline`.
- **Auditor Assessment**: **APPROVED — VERIFIED**
- **Rationale**:
  Provides a stable, deterministic mathematical expectation of customer acquisition, retention, and churn that balances the stochastic micro-agent simulation. The transition matrix enforces row stochasticity ($\sum_j T_{ij} = 1.0$) and non-negativity.

---

### [DEC-013]: Spatial Accessibility Travel-Time Matrix Routing Integration
- **Date**: Checkpoint 3 (2026-10-31)
- **Component**: `backend/app/engine/geo.py`, `backend/app/engine/model.py`
- **Specification**:
  Introduced `compute_spatial_matrices()` and `travel_time_matrix_minutes()`. `MarketArrays` now stores both `dist_km` and `travel_time_min`, with explicit metadata tracking whether matrices originated from `precomputed_network` or `circuity_speed_fallback`. Utility formulation in `run_choice()` conditionally applies travel-time impedance `beta_travel_time` when available.
- **Auditor Assessment**: **APPROVED — VERIFIED**
- **Rationale**:
  Lays the architecture for network routing matrices while maintaining fallback stability. Verified with passing regression tests in `tests/test_engine.py:test_spatial_matrices_integration`.

---

### [DEC-014]: Reclassification of Benchmark Suite to Structural Identification Check
- **Date**: Checkpoint 3 (2026-10-31)
- **Component**: `backend/tests/test_validation_benchmarks.py`, `docs/research/EXPERIMENTS.md`
- **Specification**:
  Benchmarked StratIq against 4 baselines (Uniform Radius Multiplier, Nearest-Neighbor Voronoi, Huff Gravity, and Unsegmented Logit). Ground truth in `test_validation_benchmarks.py` was generated by StratIq itself plus uniform noise.
- **Auditor Assessment**: **REJECTED AS EMPIRICAL PROOF; APPROVED AS SYNTHETIC SEPARABILITY CHECK (SIQ-ISSUE-011)**
- **Rationale**:
  Generating ground truth from the model under test is circular validation. It proves that StratIq's parameterization is structurally identifiable and separable from Huff gravity, but cannot mathematically substantiate claims of empirical superiority or real-world 1.2% WAPE. The documentation in `EXPERIMENTS.md` must be reclassified from "Empirical Evaluation" to "Synthetic Model Identification and Separability Check".
