# StratIq Master Engineering & Scientific Audit

**Repository**: `C:\Users\Lenovo\OneDrive\Desktop\INNOTECH\StratIq`  
**GitHub**: `https://github.com/HarshDubey23/StratIq`  
**Auditor**: Independent Engineering Auditor  
**Audit Skill**: `stratiq-watch` ([`.agents/skills/stratiq-watch/SKILL.md`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/.agents/skills/stratiq-watch/SKILL.md))  
**Last Checkpoint**: Checkpoint 3 (2026-10-31T05:55:00Z)  

---

## 1. Executive Summary & Health Scorecard

StratIq provides local market simulation combining OpenStreetMap geospatial features, WorldPop gridded demographics, multinomial logit discrete choice modeling, Monte Carlo risk simulation, and an agent-based live market simulation (`engine/abm.py`).

At Checkpoint 3, the Independent Engineering Auditor has conducted a comprehensive, skeptical re-evaluation of all repository changes, code mutations, and research claims:
1. **Critical Defect Caught ([SIQ-ISSUE-010])**: Uncovered a production runtime crash in `backend/app/api/projects.py:200` where `competitors_for(db, p, loc, radius, direct_only=False)` is called, but `competitors_for` in `backend/app/services/runs.py:173` does not accept `direct_only`. This raises an uncaught `TypeError` and returns a 500 server crash on `GET /projects/{project_id}/market`. This bug went unnoticed because `test_api.py` was skipped during offline test runs.
2. **Scientific Methodological Defect Caught ([SIQ-ISSUE-011])**: In `docs/research/EXPERIMENTS.md` and `tests/test_validation_benchmarks.py`, the primary agent claimed "empirical validation" and a "1.2% WAPE" demonstrating superiority over Huff gravity and naive baselines. Auditor analysis reveals that the "ground truth" was generated directly from StratIq's own output perturbed by ±3% uniform noise—a classic circular / tautological validation fallacy that violates the project's own rule #4 ("No claiming empirical calibration when only internal consistency tests exist").
3. **Subsystem Disconnection Confirmed ([SIQ-ISSUE-007])**: Confirmed that `build_synthetic_population()` (`engine/population/`), `DentalClinicEconomics` (`engine/economics/dental.py`), and `ConditionalLogitEstimator` (`engine/choice/conditional_logit.py`) are fully implemented and passing tests, but are completely uncalled and unreferenced in `backend/app/services/runs.py` or `backend/app/engine/simulate.py`.
4. **Verified Progress**:
   - Total offline passing tests expanded to **76 passed, 9 skipped** (out of 85 collected tests, 100% pass rate for runnable offline tests).
   - Category resolver subphrase collision fix ([SIQ-ISSUE-001]) and 5-tier factor evidence architecture ([SIQ-ISSUE-002]) remain **VERIFIED**.
   - Spatial travel-time matrix engine (`compute_spatial_matrices` in `geo.py`) and travel-time choice impedance (`model.py`) are successfully integrated and verified via unit tests.
   - Deterministic 6x6 row-stochastic cohort transition matrix (`COHORT_STATES`) implemented in `abm.py` and wired into `run_abm`.

### Integrity Scorecard

| Assessment Dimension | Rating | Trend | Core Finding & Evidence |
|---|:---:|:---:|---|
| **A. Scientific Validity** | **B** | ↔ Steady | Transparent assumption flags (`computed`, `user`, `assumed`, `simulated`). McFadden Conditional Logit MLE estimator authored with analytical scores and Fisher info, but disconnected from runtime simulation ([SIQ-ISSUE-007]). |
| **B. 615-Factor Genome** | **A-** | ↗ Improving | **VERIFIED FIX ([SIQ-ISSUE-002])**: Canonical 5-tier evidence architecture implemented in [`backend/app/factors/evidence_map.py`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/backend/app/factors/evidence_map.py), surfaced in `registry.py` and API `/factors/registry`. |
| **C. Synthetic Population** | **B+** | ↗ Improving | Iterative Proportional Fitting (IPF) entropy minimization engine implemented in [`backend/app/engine/population/`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/backend/app/engine/population/) (5/5 unit tests passed). Runtime wiring into `abm.py` remains pending ([SIQ-ISSUE-007]). |
| **D. Agent-Based Model (ABM)** | **B+** | ↗ Improving | Added deterministic 6x6 Markov customer cohort transition matrix baseline with word-of-mouth feedback into `abm.py`. Asymmetric competitor capacity ([SIQ-ISSUE-004]) remains open. |
| **E. Competitor Intelligence** | **B** | ↘ Regression | **VERIFIED FIX ([SIQ-ISSUE-001])**: Specificity-weighted resolver and 6-tier competitor framework (`competitors.py`) active. **CRITICAL DEFECT ([SIQ-ISSUE-010])**: Signature mismatch `competitors_for(direct_only=False)` crashes `GET /projects/{id}/market`. Symmetric imputation remains open ([SIQ-ISSUE-008]). |
| **F. Financial & Economic Logic** | **A** | ↗ Improving | Linear operating economics verified. Dedicated 7-procedure dental clinical feasibility model authored in [`backend/app/engine/economics/dental.py`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/backend/app/engine/economics/dental.py) (4/4 unit tests passed), pending runtime wiring ([SIQ-ISSUE-007]). |
| **G. Engineering Quality** | **B+** | ↔ Steady | Test suite grew to 76 passing offline tests in 48.99s. However, API endpoint crash was masked because `test_api.py` was skipped offline. Frontend dependencies remain missing ([SIQ-ISSUE-005]). |
| **H. Research & Claims Quality** | **B** | ↘ Scrutinized | **CRITICAL AUDIT FINDING ([SIQ-ISSUE-011])**: `docs/research/EXPERIMENTS.md` claims empirical superiority (1.2% WAPE) based on circular synthetic data generated by StratIq itself. Must be reclassified as a synthetic structural separability check. |

---

## 2. Issue Summary Matrix

| Severity | Total | OPEN | ACKNOWLEDGED | FIXED | VERIFIED |
|---|:---:|:---:|:---:|:---:|:---:|
| **P0 — Critical** | 0 | 0 | 0 | 0 | 0 |
| **P1 — High** | 3 | 2 | 0 | 0 | 1 |
| **P2 — Medium** | 7 | 3 | 1 | 0 | 3 |
| **P3 — Low** | 2 | 2 | 0 | 0 | 0 |
| **INFO** | 0 | 0 | 0 | 0 | 0 |
| **Total** | **12** | **7** | **1** | **0** | **4** |

### Issue Quick Reference
- [`[SIQ-ISSUE-001]`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md#siq-issue-001-category-resolver-subphrase-collision-causes-dental--medical-clinic-misclassification) (P1): **VERIFIED**. Category resolver subphrase collision resolved via specificity weighting and 6-tier competitor classification engine.
- [`[SIQ-ISSUE-002]`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md#siq-issue-002-193-of-615-genome-factors-are-unconnected-placeholders-lacking-data-ingestion) (P2): **VERIFIED**. 5-tier evidence architecture formally mapped across all 615 factors in `evidence_map.py`, surfaced in `registry.py`, API `/factors/registry`, and verified by unit tests.
- [`[SIQ-ISSUE-003]`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md#siq-issue-003-synthetic-agent-latent-traits-sampled-independently-without-covariance-structure) (P2): **ACKNOWLEDGED**. IPF population synthesis engine authored; pending runtime connection to ABM.
- [`[SIQ-ISSUE-004]`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md#siq-issue-004-asymmetric-competitor-capacity-representation-in-agent-based-simulation) (P2): **OPEN**. Asymmetric competitor capacity representation in ABM simulation.
- [`[SIQ-ISSUE-005]`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md#siq-issue-005-frontend-node-dependencies-missing-in-workspace) (P3): **OPEN**. Frontend node dependencies missing in local workspace.
- [`[SIQ-ISSUE-006]`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md#siq-issue-006-untracked-local-docker-compose-file-present-in-repository-root) (P3): **OPEN**. Untracked local Docker Compose file present in repository root.
- [`[SIQ-ISSUE-007]`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md#siq-issue-007-spatial-population-synthesis-engine-and-dedicated-dental-clinical-economics-disconnected-from-production-simulation-runtime) (P1): **OPEN**. Disconnected subsystems: `build_synthetic_population()`, `DentalClinicEconomics`, and `ConditionalLogitEstimator` are implemented and tested, but uncalled in `abm.py` and `services/runs.py`.
- [`[SIQ-ISSUE-008]`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md#siq-issue-008-symmetric-competitor-imputation-collapses-non-spatial-choice-heterogeneity-in-openstreetmap-data) (P2): **OPEN**. Symmetric competitor price/quality imputation in `model.py` and `abm.py` collapses non-spatial choice differentiation across OpenStreetMap POIs.
- [`[SIQ-ISSUE-009]`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md#siq-issue-009-temporary-nameerror-bug-in-dental-economics-module-exposes-need-for-pre-commit-test-hooks) (P2): **VERIFIED**. Temporary `NameError` in `dental.py` was caught by tests and resolved by primary agent adding `import math`.
- [`[SIQ-ISSUE-010]`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md#siq-issue-010-uncaught-typeerror-in-get-projectsidmarket-due-to-mismatched-competitors_fordirect_onlyfalse-call-signature) (P1): **OPEN**. Production API crash: `projects.py:200` calls `competitors_for(direct_only=False)`, but `runs.py:173` does not accept `direct_only`, throwing `TypeError` and causing 500 error on `GET /projects/{id}/market`.
- [`[SIQ-ISSUE-011]`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md#siq-issue-011-circular-tautological-ground-truth-in-benchmark-suite-misrepresented-as-empirical-validation) (P2): **OPEN**. Circular validation: `test_validation_benchmarks.py` generates "ground truth" from StratIq's own output plus ±3% uniform noise, yet `docs/research/EXPERIMENTS.md` claims "Empirical Evaluation" and a 1.2% WAPE against industry baselines.
- [`[SIQ-ISSUE-012]`](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md#siq-issue-012-keyerror-in-new-e2e-dental-integration-test-due-to-key-mismatch-available_chair_minutes-vs-available_chair_hours) (P2): **VERIFIED**. Key mismatch in `test_e2e_dental.py:184` fixed by accessing property getter `dental_econ.available_chair_minutes` directly; verified passing (1/1 passed).

---

## 3. Deep-Dive Audit Across 8 Core Dimensions

### A. Scientific Validity & Parameter Foundations
- **Strengths**: Transparent parameter status tracking (`computed`, `user`, `assumed`, `simulated`, `unavailable`). Complete 615-factor lineage classification in `PARAMETER_EVIDENCE_AUDIT.csv` and `evidence_map.py`.
- **Discrete Choice Engine**: In `backend/app/engine/choice/conditional_logit.py`, the primary agent authored a McFadden Conditional Logit MLE estimator using L-BFGS-B optimization, analytical score gradients, observed Fisher information covariance matrix inversion (`pinv`), z-statistics, p-values, and McFadden pseudo-$R^2$. Parameter recovery validated across 6 unit tests in `test_choice_model.py`.
- **Architectural Disconnection**: The choice model estimator is currently an offline analytical package and is not wired into `backend/app/engine/simulate.py` or `backend/app/services/runs.py` ([SIQ-ISSUE-007]).

### B. 615-Parameter Genome
- **Distribution of Evidence Classes**:
  - `OBSERVED`: 115 (18.7%) — OpenStreetMap POIs, building footprints, WorldPop population counts.
  - `DERIVED`: 169 (27.5%) — Spatial densities, nearest-neighbor distances, network accessibility.
  - `ESTIMATED`: 38 (6.2%) — Benchmark demographic defaults and user inputs.
  - `PROXY`: 2 (0.3%) — Circuity factor (1.3) and activity proxies.
  - `UNSUPPORTED`: 291 (47.3%) — 193 reserved factor definitions + 98 heuristic parameters.
- **Verification**: `backend/app/factors/evidence_map.py` defines the canonical enum `EvidenceStatus` and maps every factor key. Exposed via `@router.get("/factors/registry")` in `backend/app/api/projects.py`. Verified by 4/4 passing unit tests in `backend/tests/test_factors.py`.

### C. Synthetic Population & Demographic Synthesis
- **Strengths**: Dasymetric OSM building-based population weighting across hexagonal cells.
- **IPF Synthesis Module**: Primary agent authored `backend/app/engine/population/` (`ipf.py`, `synthesis.py`, `validation.py`) implementing Iterative Proportional Fitting minimizing Kullback-Leibler divergence against 17 age-sex bands and zone marginals. Passes all 5 unit tests in `test_population_synthesis.py`.
- **Status**: Subsystem remains disconnected from the live simulation execution pipeline ([SIQ-ISSUE-007]).

### D. Agent-Based Model (ABM)
- **Strengths**: Added deterministic 6x6 row-stochastic cohort transition matrix (`COHORT_STATES`: `unaware`, `aware`, `considering`, `trial`, `loyal`, `churned`) in `abm.py`. Guarantees strict population conservation and non-negative counts. Returns `cohort_baseline` directly inside `run_abm`.
- **Vulnerabilities**:
  1. Asymmetric competitor capacity ([SIQ-ISSUE-004]): Capacity turn-away and congestion memory (`cong[rejected] = 14`) apply exclusively to `choice == 0` (user business). Competitors are modeled with infinite capacity.
  2. Latent traits in `abm.py` continue to be drawn independently without multivariate copula conditioning pending IPF runtime integration.

### E. Competitor Intelligence & Provider Integration
- **Strengths**: Subphrase collision in `resolver.py` is resolved ([SIQ-ISSUE-001]). 6-tier competitor classification in `competitors.py` strictly prevents spas from entering dental simulations.
- **Critical Regression ([SIQ-ISSUE-010])**: `backend/app/api/projects.py:200` calls `competitors_for(db, p, loc, radius, direct_only=False)`, but `runs.py:173` only accepts `(db, project, loc, radius_km)`, raising `TypeError` at runtime.
- **Vulnerabilities**: Symmetric competitor price/quality imputation in `model.py:177-180` and `abm.py:138-139` assigns identical values to all unpriced OSM competitors ([SIQ-ISSUE-008]). Secondary provider failover (Photon, Foursquare) remains unbuilt.

### F. Economic & Financial Models
- **Strengths**: Linear operating economics ($Revenue - Variable - Fixed = Profit$) verified. Dedicated `DentalClinicEconomics` engine in `engine/economics/dental.py` models 7 distinct clinical procedures with chair-minute capacity constraints, consumable and lab costs, and Capex payback (4/4 tests passed).
- **Vulnerabilities**: Dental model is not yet connected to `services/runs.py` ([SIQ-ISSUE-007]).

### G. Engineering Quality
- **Strengths**: Test suite grew from 27 to **76 passing offline tests** (0 failures, 9 database/network skips) across 8 test suites in 48.99s.
- **Vulnerabilities**:
  - Missing offline integration tests for API routes (`test_api.py` requires live database, allowing API call signature mismatches to escape detection).
  - Missing frontend dependencies in workspace ([SIQ-ISSUE-005]); untracked local docker compose file ([SIQ-ISSUE-006]).

### H. Research Quality & Claims Validation
- **Strengths**: Rigorous literature review in `docs/research/LITERATURE_REVIEW.md` citing foundational econometric and spatial interaction papers.
- **Critical Methodological Vulnerability ([SIQ-ISSUE-011])**:
  `docs/research/EXPERIMENTS.md` presents a benchmark evaluation against Huff gravity, Voronoi allocation, and unsegmented logit, claiming a "1.2% WAPE" and "0.0003 Brier score". However, inspection of `backend/tests/test_validation_benchmarks.py:129-132` demonstrates that the test generates ground truth by multiplying StratIq's own output by `uniform(0.97, 1.03)`. This is circular validation and must be labeled transparently as a synthetic identification check rather than empirical proof.

---

## 4. Audit Document Navigation

- [Detailed Issues Register (`docs/audit/ISSUES.md`)](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/ISSUES.md)
- [Test Execution & Verification Evidence (`docs/audit/TEST_EVIDENCE.md`)](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/TEST_EVIDENCE.md)
- [Architectural & Scientific Decisions Log (`docs/audit/DECISIONS.md`)](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/DECISIONS.md)
- [Primary Agent Activity & Limitations Log (`docs/audit/AGENT_ACTIVITY.md`)](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/AGENT_ACTIVITY.md)
- [Chronological Audit Changelog (`docs/audit/CHANGELOG.md`)](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/docs/audit/CHANGELOG.md)
- [Auditor Skill Protocol (`.agents/skills/stratiq-watch/SKILL.md`)](file:///C:/Users/Lenovo/OneDrive/Desktop/INNOTECH/StratIq/.agents/skills/stratiq-watch/SKILL.md)
