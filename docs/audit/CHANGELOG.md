# StratIq Audit System Changelog

All chronological entries regarding audit system initialization, primary agent checkpoints, discovered issues, and verified resolutions are recorded here. Never overwrite previous entries.

---

## [2026-10-31] — Baseline Audit Initialization (Checkpoint 0)

### Audit Event: Baseline Inspection & Framework Setup
- **Auditor**: Independent Engineering Auditor (`stratiq-watch`)
- **Git Commit**: `0883fb4` (`Docs: agent-based live market and factor engine`)
- **Git Branch**: `main`

### Actions Performed
1. **Repository Inspection**:
   - Inspected repository structure (`backend/app`, `backend/tests`, `frontend/`, `docs/`).
   - Inspected working directory status: branch is clean; untracked file `docker-compose.harsh-local.yml` identified.
   - Verified that `docs/audit/` did not previously exist.
2. **Audit System Setup**:
   - Initialized `docs/audit/MASTER_AUDIT.md`
   - Initialized `docs/audit/ISSUES.md`
   - Initialized `docs/audit/CHANGELOG.md`
   - Initialized `docs/audit/TEST_EVIDENCE.md`
   - Initialized `docs/audit/DECISIONS.md`
   - Initialized `docs/audit/AGENT_ACTIVITY.md`
3. **Auditor Skill Creation**:
   - Created reusable Antigravity skill `.agents/skills/stratiq-watch/SKILL.md` (both in project workspace and global `.agents/skills`).
4. **Baseline Test Execution**:
   - Executed `pytest -v` across `backend/tests/`: 27 passed, 9 skipped (PostGIS DB & live network tests skipped by design).
   - Attempted frontend typecheck: noted missing `node_modules` in local workspace.
5. **Baseline Issue Identification**:
   - **SIQ-ISSUE-001 (P1)**: Category resolver subphrase collision causes dental & medical clinic misclassification.
   - **SIQ-ISSUE-002 (P2)**: 193 of 615 genome factors are unconnected placeholders lacking data ingestion.
   - **SIQ-ISSUE-003 (P2)**: Synthetic agent latent traits sampled independently without covariance structure.
   - **SIQ-ISSUE-004 (P2)**: Asymmetric competitor capacity representation in ABM simulation.
   - **SIQ-ISSUE-005 (P3)**: Frontend node dependencies missing in workspace.
   - **SIQ-ISSUE-006 (P3)**: Untracked local Docker Compose file present in repository root.

---

## [2026-10-31] — Primary Agent Checkpoint 1 (PARAMETER_EVIDENCE_AUDIT.csv)

### Audit Event: Detection of 615-Parameter Evidence Audit
- **Auditor**: Independent Engineering Auditor (`stratiq-watch`)
- **Timestamp**: 2026-10-31T05:04:30Z
- **Changes Detected**:
  - Untracked file created: `docs/research/PARAMETER_EVIDENCE_AUDIT.csv` (168 KB).
- **Findings**:
  - Primary agent generated a line-by-line audit of all 615 parameters.
  - Confirms auditor finding [SIQ-ISSUE-002]: primary agent designates the 193 placeholder factors as `"Placeholder factor; unidentifiable in available public datasets without proprietary survey microdata"` and flags action `"Mark unsupported"`.
  - Confirms auditor finding [SIQ-ISSUE-003]: primary agent acknowledges heuristic dynamic parameters in `abm.py` lacking longitudinal empirical validation.
- **Issue Lifecycle Updates**:
  - `[SIQ-ISSUE-002]`: Transitioned from `OPEN` to `ACKNOWLEDGED`.
  - `[SIQ-ISSUE-003]`: Transitioned from `OPEN` to `ACKNOWLEDGED`.

---

## [2026-10-31] — Primary Agent Checkpoint 2 (Phase 1 P0 Fixes, Population Synthesis & Dental Economics)

### Audit Event: Codebase Mutation & Independent Verification
- **Auditor**: Independent Engineering Auditor (`stratiq-watch`)
- **Timestamp**: 2026-10-31T05:30:00Z
- **Working Tree Delta**:
  - Modified: `backend/app/categories/resolver.py`, `backend/app/categories/taxonomy.py`, `backend/app/categories/competitors.py`, `backend/app/services/runs.py`, `backend/app/api/serialize.py`, `backend/app/api/projects.py`.
  - New Untracked Modules:
    - `backend/app/categories/competitors.py` (6-tier competitor classification engine)
    - `backend/app/engine/economics/dental.py` (7-procedure dental clinic feasibility engine)
    - `backend/app/engine/population/` (`ipf.py`, `synthesis.py`, `validation.py`)
  - New Test Suites:
    - `backend/tests/test_categories.py` (31 tests)
    - `backend/tests/test_dental_economics.py` (4 tests)
    - `backend/tests/test_population_synthesis.py` (5 tests)
  - Research Documentation Added:
    - `docs/research/IMPLEMENTATION_PLAN.md`
    - `docs/research/LITERATURE_REVIEW.md`
    - `docs/research/REPOSITORY_AUDIT.md`
    - `docs/research/SYNTHETIC_POPULATION_METHODOLOGY.md`
    - `docs/research/SYNTHETIC_POPULATION_VALIDATION.md`

### Test Verification
- Executed `pytest -v` across all test files: **67 passed, 9 skipped** (up from 27 passed).
- Category resolver tests: 31/31 passed. Direct Python execution confirms `"cosmetic dental clinic"` $\to$ `dentist` and `"medical spa"` $\to$ `beauty_salon`.
- Population synthesis tests: 5/5 passed. IPF converges with non-negative weights and margin conservation.
- Dental economics tests: 4/4 passed.

### Issue Lifecycle Updates
- `[SIQ-ISSUE-001]`: Transitioned from `OPEN` to `VERIFIED`. (Category resolver collision fixed with specificity weighting and 6-tier competitor classification).
- `[SIQ-ISSUE-007]`: **OPEN** (High). Disconnected subsystems: `build_synthetic_population()` and `DentalClinicEconomics` are implemented and tested, but uncalled in `abm.py` and `services/runs.py`.
- `[SIQ-ISSUE-008]`: **OPEN** (Medium). Symmetric competitor price/quality imputation in `model.py` and `abm.py` collapses non-spatial choice differentiation across OpenStreetMap POIs.
- `[SIQ-ISSUE-009]`: **VERIFIED** (Medium). Temporary `NameError: name 'math' is not defined` bug in `dental.py` was resolved by primary agent adding `import math`.
---

## [2026-10-31] — Independent Engineering Audit Checkpoint 3 (Boosted Deep-Dive)

### Audit Event: Full Spectrum Verification, Runtime Bug Detection & Scientific Scrutiny
- **Auditor**: Independent Engineering Auditor (`stratiq-watch`)
- **Timestamp**: 2026-10-31T05:55:00Z
- **Working Tree Delta**:
  - New Test Suites Detected:
    - `backend/tests/test_choice_model.py` (6 parameter recovery MLE tests)
    - `backend/tests/test_validation_benchmarks.py` (2 benchmark superiority & invariant tests)
  - New Subsystems Detected:
    - `backend/app/engine/choice/` (`conditional_logit.py`, `validation.py`, `__init__.py`)
  - Subsystems Modified:
    - `backend/app/engine/abm.py`: Added 6x6 deterministic Markov customer cohort transition matrix baseline (`build_cohort_transition_matrix`, `run_cohort_transition_baseline`) returning `cohort_baseline`.
    - `backend/app/engine/geo.py`: Added `travel_time_matrix_minutes()` and `compute_spatial_matrices()`.
    - `backend/app/engine/model.py`: Added `travel_time_min`, `dist_source`, `travel_time_source`, and travel-time impedance in `run_choice`.
    - `backend/tests/test_engine.py`: Added `test_spatial_matrices_integration`.
  - Research Documentation Added:
    - `docs/research/ABM_ODD_PROTOCOL.md` (Formal ODD protocol specification)
    - `docs/research/EXPERIMENTS.md` (Benchmark evaluation report)

### Test Verification
- Executed full backend test suite: **76 passed, 9 skipped** (out of 85 collected tests in 48.99s).
- Discrete choice MLE parameter recovery: 6/6 passed (recovering true parameters within 99% confidence interval).
- Benchmark model invariance: 2/2 passed.
- Travel-time matrix fallback & precomputation: passed in `test_engine.py`.

### Critical Findings & Discoveries
1. **Production Runtime API Crash ([SIQ-ISSUE-010])**:
   - `backend/app/api/projects.py:200` calls `competitors_for(db, p, loc, radius, direct_only=False)`.
   - `backend/app/services/runs.py:173` only accepts 4 parameters and lacks `direct_only`.
   - Raises `TypeError: competitors_for() got an unexpected keyword argument 'direct_only'`, crashing `GET /projects/{id}/market` with a 500 Internal Server Error.
2. **Circular Benchmark Validation Fallacy ([SIQ-ISSUE-011])**:
   - `backend/tests/test_validation_benchmarks.py:129-132` generates "ground truth" by multiplying StratIq's own output by `uniform(0.97, 1.03)`.
   - `docs/research/EXPERIMENTS.md` claims "Empirical Evaluation" and a 1.2% WAPE against Huff gravity and Voronoi models based on this circular data.
   - Violated non-negotiable rule #4 ("No claiming empirical calibration when only internal consistency tests exist"). Reclassified as a synthetic structural separability check.
3. **Subsystem Disconnection Extended ([SIQ-ISSUE-007])**:
   - Confirmed that `ConditionalLogitEstimator` joins `build_synthetic_population()` and `DentalClinicEconomics` as tested but disconnected runtime modules.

### Issue Lifecycle Updates
- `[SIQ-ISSUE-002]`: Transitioned from `ACKNOWLEDGED` to **`VERIFIED`** (5-tier evidence architecture implemented across all 615 factors in `evidence_map.py`, surfaced in API and verified by tests).
- `[SIQ-ISSUE-010]`: **OPEN** (P1 — High). Mismatched signature in `projects.py:200` crashes `GET /projects/{id}/market`.
- `[SIQ-ISSUE-011]`: **OPEN** (P2 — Medium). Circular ground truth in `test_validation_benchmarks.py` misrepresented as empirical validation.
