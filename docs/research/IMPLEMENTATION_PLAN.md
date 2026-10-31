# StratIq Master Scientific Re-Engineering & Production Implementation Plan

**Date:** October 31, 2026  
**Audited Head Commit:** `0883fb4`  
**Plan Status:** Ready for User Review and Explicit Authorization  

---

## 1. Overview and Phasing Strategy

This document details the complete architectural and scientific transformation of StratIq from a heuristic-driven simulation into an evidence-constrained, empirically calibrated spatial market feasibility platform.

### Strict Non-Negotiables:
1. **No arbitrary parameter assignment.**
2. **No undocumented hard-coded behavioural coefficients.**
3. **No random values presented as real individual facts.**
4. **No claiming empirical calibration when only internal consistency tests exist.**
5. **No modifying production source code without complete regression test coverage.**

---

## Phase 1 — P0 Correctness Fixes: Taxonomy, Resolver & Competitor Filtering

### 1.1 Specificity-Aware Category Resolver
- **Problem:** When a user queries `"dentist clinic"`, `rank_taxonomy` computes a score of `0.92` for both `clinic` (index 88) and `dentist` (index 89). Python's stable sort preserves index order, causing generic `clinic` to defeat specific `dentist`. Similarly, `"medical clinic"` resolves to `pharmacy` due to synonym overlap with `"medical store"`, and `"orthodontist"` falls back to crude name-keyword matching.
- **Current Implementation:** `backend/app/categories/resolver.py:rank_taxonomy` and `score_entry` using unweighted `SequenceMatcher` and token subset checks.
- **Proposed Implementation:**
  1. Implement token specificity weighting: Give higher weight to rarer and more specific domain terms (e.g. `dentist`, `orthodontist`) over broad organizational terms (`clinic`, `store`, `centre`, `shop`).
  2. Implement hierarchical depth preference: When a child category (`dentist`) and parent category (`clinic`) both match, the more specific child category receives a hierarchical boost.
  3. Strict semantic disambiguation: Require primary purpose alignment (e.g. medical treatment vs drug dispensing for `pharmacy`).
  4. Explicit tie handling: Any score difference $< 0.03$ triggers `needs_confirmation = True` with alternative candidates presented to the user.
- **Mathematical Method:**
  $$\text{Score}(q, c) = \alpha \cdot \text{Jaccard}(q, c) + \beta \cdot \text{TokenIDF}(q \cap c) + \gamma \cdot \text{Depth}(c)$$
- **Files to Change:**
  - `backend/app/categories/resolver.py`
  - `backend/app/categories/taxonomy.py`
  - `backend/tests/test_categories.py` (new regression suite)
- **Tests & Acceptance Criteria:**
  - `"dentist clinic"` MUST resolve to `key="dentist"` with $\ge 98\%$ confidence.
  - `"dental clinic"`, `"dental hospital"`, `"orthodontist"` MUST resolve to dental categories.
  - `"medical clinic"` MUST resolve to `clinic`, never `pharmacy`.
  - Regression suite passes 100% of tested business queries.

### 1.2 6-Tier Competitor Relationship Engine
- **Problem:** All POIs fetched from OSM around a project location are saved to `competitors` and retrieved via `competitors_for` without service-level filtering. A dental clinic simulation can thus pull in wellness spas or generic outpatient health centres that do not provide dental care.
- **Current Implementation:** `services/runs.py:competitors_for` selects purely on geographic distance (`ST_DWithin`) and `project_id`.
- **Proposed Implementation:**
  1. Classify every candidate POI into one of 6 explicit relationship tiers:
     - `DIRECT`: Exact category match (e.g., `amenity=dentist`, `healthcare=dentist`).
     - `PARTIAL_SERVICE`: Multi-specialty hospital with verified dental department.
     - `INDIRECT_SUBSTITUTE`: Alternative modality (e.g., cosmetic clinic offering teeth whitening).
     - `ADJACENT`: Complementary healthcare service (e.g., pharmacy, diagnostic lab).
     - `CONTEXTUAL_POI`: Footfall generator (e.g., metro station, supermarket).
     - `IRRELEVANT`: Spas, salons, general retail (excluded from dental competitor sets).
  2. Store explicit classification explanation and source confidence for each POI.
- **Files to Change:**
  - `backend/app/categories/taxonomy.py`
  - `backend/app/services/market.py`
  - `backend/app/models.py` (add `relationship_tier` and `classification_rationale` columns)
  - `backend/app/engine/model.py` (only direct and partial competitors enter the choice set)
- **Tests & Acceptance Criteria:**
  - When category is `dentist`, spas (`amenity=spa`, `leisure=spa`) are strictly classified as `IRRELEVANT` and never enter the choice utility matrix.

---

## Phase 2 — Evidence Architecture & Parameter Lineage

### 2.1 Refactor 615 Parameters into Strict Evidence Classes
- **Problem:** The current 615-factor engine mixes uncalibrated hypotheses, simulation outputs, and completely unsupported placeholders into a single undifferentiated list.
- **Proposed Implementation:**
  Structure the canonical registry into 5 non-negotiable scientific statuses:
  - `OBSERVED`: Directly verified from trustworthy sources (OSM tags, Census totals).
  - `DERIVED`: Deterministic mathematical functions of observed inputs (e.g., densities, network distances).
  - `ESTIMATED`: Statistically estimated via documented econometric models with standard errors and confidence intervals.
  - `PROXY`: Documented indirect indicators (explicitly flagged, e.g., circuity).
  - `UNSUPPORTED`: Factors without empirical data (marked unavailable; prevented from entering causal models).
- **Files to Change:**
  - `backend/app/factors/registry.py`
  - `backend/app/factors/compute.py`
  - `docs/research/PARAMETER_EVIDENCE_AUDIT.csv` (maintain as live artifact)
- **Acceptance Criteria:**
  - 109 simulation outputs are decoupled from input factors.
  - 193 reserved factors cannot affect strict-evidence forecasts.

---

## Phase 3 — Spatial Synthetic Population Engine

### 3.1 Census-Constrained IPF / IPU Population Synthesis
- **Problem:** Currently, agents are sampled from hexagonal cells using WorldPop raster totals multiplied by building centroids, with individual traits drawn from arbitrary univariate beta distributions.
- **Mathematical Method:**
  Implement Iterative Proportional Fitting (IPF) and Iterative Proportional Updating (IPU) (Beckman et al., 1996; Ye et al., 2009):
  $$\min_{\{w_i\}} \sum_{i} w_i \ln\left(\frac{w_i}{w_i^{(0)}}\right) \quad \text{subject to} \quad \sum_{i} w_i x_{ik} = m_k \quad \forall k$$
  Where $m_k$ are known marginal totals (Census Ward age distributions, sex ratios, household sizes) and $w_i^{(0)}$ are baseline sample weights from representative survey microdata (IHDS / MoSPI HCES).
- **Supported Modes:**
  - **Mode A (Scientific Baseline):** Weighted synthetic records where each record represents $w_i$ real residents.
  - **Mode B (Deterministic 10,000 Records):** Controlled integer rounding preserving population margins with reported calibration residuals.
- **Files to Create / Change:**
  - `backend/app/engine/population/` (new package)
  - `backend/app/engine/population/ipu.py`
  - `backend/app/engine/population/synthesis.py`
  - `backend/tests/test_population_synthesis.py`
- **Acceptance Criteria:**
  - Marginal absolute error (MAE) on age-sex distributions $< 2\%$.
  - Exact reproducibility for a given random seed and dataset snapshot.

---

## Phase 4 — Behavioural Discrete Choice Engine

### 4.1 McFadden Conditional Logit with Outside Option
- **Problem:** Behavioral coefficients ($\beta_p, \beta_q, \lambda, U_0$) are currently arbitrary constants.
- **Mathematical Method:**
  Estimate systematic utility $V_{ij} = \boldsymbol{\beta}^\top \mathbf{x}_{ij}$ using Maximum Likelihood Estimation on consumer choice data (McFadden, 1974; Train, 2009).
  Choice probability:
  $$P_{ij} = \frac{\exp(V_{ij})}{\exp(U_0) + \sum_{k \in C_i} \exp(V_{ik})}$$
  Outside option $U_0$ calibrated so that total captured volume equals empirical service participation rates.
- **Validation Metrics:**
  - Holdout Log Loss (Cross-Entropy).
  - Brier Score: $\text{BS} = \frac{1}{N} \sum_{n=1}^N \sum_{j} (P_{nj} - y_{nj})^2$.
  - Predicted vs. Observed market share discrepancy.
- **Files to Change:**
  - `backend/app/engine/model.py`
  - `backend/app/engine/choice/` (new package for estimation and validation)
  - `backend/tests/test_choice_model.py`

---

## Phase 5 — Spatial Accessibility & Travel-Time Routing

### 5.1 True Network Travel-Time Matrix
- **Problem:** Straight-line distance multiplied by $1.3$ circuity ignores real-world urban road barriers, one-way systems, and traffic bottlenecks.
- **Proposed Implementation:**
  - Integrate OpenRouteService matrix API / local OSRM / pgRouting for true network travel times and walking isochrones.
  - Graceful fallback with explicit uncertainty documentation when external routing is unreachable.
- **Files to Change:**
  - `backend/app/providers/population.py`
  - `backend/app/engine/geo.py`
  - `backend/app/engine/model.py`

---

## Phase 6 — Business-Specific Economics: Dental Feasibility Model

### 6.1 Clinical Procedure & Capacity Economics
- **Problem:** Dental clinics are treated as generic appointment services with a single price and single throughput.
- **Proposed Implementation:**
  Model dental economics at the procedure level:
  1. **Procedure Mix:**
     - Consultations & Diagnostics.
     - Preventive Cleanings & Scaling.
     - Restorative Fillings.
     - Endodontics (Root Canal Treatments).
     - Extractions & Minor Oral Surgery.
     - Prosthodontics & Crowns.
     - Orthodontics.
  2. **Capacity Constraints:**
     $$\text{Capacity}_s = \frac{\text{Chairs} \times \text{Dentist Hours/Day} \times 60 \times \text{Open Days}}{\text{Average Procedure Duration}_s}$$
  3. **Financial Statement:**
     $$\text{Revenue} = \sum_{s} \text{Completed}_s \times \text{Price}_s$$
     $$\text{Contribution} = \text{Revenue} - \sum_{s} (\text{Consumables}_s + \text{Lab Fees}_s) \times \text{Completed}_s$$
     $$\text{Operating Profit} = \text{Contribution} - \text{Fixed Costs (Rent, Staff Salaries, Equipment EMI, Utilities)}$$
- **Files to Create:**
  - `backend/app/engine/economics/dental.py`
  - `backend/tests/test_dental_economics.py`

---

## Phase 7 — Dynamic Simulation & ODD Documentation

### 7.1 Formal ABM Specification
- **Implementation:**
  - Isolate stochastic dynamic ABM from deterministic expected-value baseline.
  - Complete `docs/research/ABM_ODD_PROTOCOL.md` adhering strictly to Grimm et al. (2020) standards.
  - Replace uncalibrated arbitrary daily transitions with deterministic cohort transition matrix baseline $\mathbf{n}_{t+1} = \mathbf{n}_t \mathbf{T}_t$.

---

## Phase 8 — Independent Validation Research & Baselines

### 8.1 Empirical Benchmarking & Ablation Suite
- **Comparative Baselines:**
  1. Baseline 1: Simple circular radius demographic multiplier.
  2. Baseline 2: Nearest-competitor allocation.
  3. Baseline 3: Standard Huff (1963) gravity model.
  4. Baseline 4: Basic Conditional Logit without spatial segmentation.
  5. Baseline 5: StratIq existing model (`siq-choice-1.1`).
  6. Proposed: StratIq Evidence-Constrained Spatially Calibrated Model.
- **Ablation Studies:**
  - Model without travel-time impedance.
  - Model without competitor relationship classification.
  - Model without procedure-level clinical capacity.
- **Metrics:** MAE, WAPE, Brier Score, and Interval Coverage.
- **Files to Create:**
  - `docs/research/EXPERIMENTS.md`
  - `backend/tests/test_validation_benchmarks.py`

---

## Phase 9 — Production Hardening & Resilience

### 9.1 Durable Asynchronous Worker Architecture
- **Problem:** Data snapshot refresh jobs run via `asyncio.create_task` in server memory.
- **Proposed Implementation:**
  - Implement durable job queue with state transitions (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`).
  - Store job execution progress, retry policies, and error traces in PostgreSQL.
- **Files to Change:**
  - `backend/app/services/runs.py`
  - `backend/app/models.py` (Job schema)

---

## 2. Deliverables and Gate Milestones

| Gate | Name | Mandatory Success Criteria |
|---|---|---|
| **Gate 1** | Category & Competitor Correctness | `"dentist clinic"` resolves to `dentist`; spas strictly excluded from dental competitor sets; 100% regression tests pass. |
| **Gate 2** | Evidence Integrity | All 615 parameters audited and mapped into 5 evidence statuses; simulation outputs decoupled from inputs. |
| **Gate 3** | Synthetic Population | Deterministic 10,000 representative records generated via IPF; demographic marginal error $< 2\%$. |
| **Gate 4** | Behavioural Model | Discrete choice coefficients estimated or bounded with explicit evidence classifications; outside option calibrated. |
| **Gate 5** | Dental Clinical Economics | 7 clinical procedures independently modeled with clinical durations, variable lab fees, and chair capacities. |
| **Gate 6** | Research Validation | Comparison against 5 baselines documented with WAPE and Brier scores; reproducible scripts delivered. |
| **Gate 7** | Production Hardening | Background tasks survive process restarts; database migrations fully verified. |
| **Gate 8** | Documentation | All docs in `docs/research/` reflect actual running code; zero fabricated citations or metrics. |
