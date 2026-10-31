# StratIq Scientific Literature Review & Theoretical Foundations

**Review Date:** October 31, 2026  
**Auditor / Reviewer:** Multidisciplinary Research Review Team (Computational Social Science, Spatial Econometrics, Discrete Choice Modelling, ABM)  

---

## 1. Synthetic Population Modelling & Spatial Microsimulation

### 1.1 Beckman, Baggerly, & McKay (1996) — Creating Synthetic Baseline Populations
- **Citation:** Beckman, R. J., Baggerly, K. A., & McKay, M. D. (1996). *Creating synthetic baseline populations*. Transportation Research Part A: Policy and Practice, 30(6), 415–429.  
- **DOI:** [10.1016/0965-8564(96)00004-3](https://doi.org/10.1016/0965-8564(96)00004-3)
- **Methodological Core:** The seminal paper introducing Iterative Proportional Fitting (IPF) to combine aggregate census marginal distributions with sample microdata (Public Use Microdata Samples - PUMS) to construct full spatial synthetic populations without violating marginal constraints.
- **StratIq Architectural Decision:** StratIq currently downscales WorldPop 100m raster grids to hexagonal spatial cells using building footprints alone without microdata conditioning. Under Beckman et al.'s formulation, StratIq must use marginal demographic constraints (age, sex, household size from Census of India / WorldPop) as target margins to re-weight baseline survey microdata (e.g. IHDS or MoSPI HCES) rather than randomly drawing personas from assumed univariate distributions.
- **Limitations:** Standard IPF can produce cell zero issues when microdata lacks representation for specific cross-tabulations, and traditional IPF works at either person level or household level, risking ecological fallacy or hierarchical inconsistency.

### 1.2 Ye, Konduri, Pendyala, Sana, & Waddell (2009) — Iterative Proportional Updating (IPU)
- **Citation:** Ye, X., Konduri, K., Pendyala, R. M., Sana, B., & Waddell, P. (2009). *A methodology to match distributions of both household and person attributes in the generation of synthetic populations*. In 88th Annual Meeting of the Transportation Research Board, Washington, DC.
- **Methodological Core:** Formulates the Iterative Proportional Updating (IPU) algorithm, which simultaneously adjusts household-level weights to satisfy both household-level constraints (e.g., household size, income category) and person-level marginal constraints (e.g., age-sex distributions).
- **StratIq Architectural Decision:** When synthesizing consumer populations for local catchments,StratIq must avoid independently drawing person-level attributes that violate household-level budget or cohabitation constraints. IPU provides the algorithmic foundation for Phase 3 population synthesis.

### 1.3 Swastik, BharatSim Team, et al. (2022) — BharatSim Agent-Based Framework for India
- **Citation:** Swastik, et al. (2022). *BharatSim: An agent-based modelling framework for India*. Ashoka University & Swastik Consortium Technical Report.
- **Methodological Core:** Develops an India-specific spatial microsimulation pipeline integrating Census of India district/ward PCA (Primary Census Abstract), NSSO consumer expenditure survey rounds, and building/amenity densities to generate realistic synthetic households.
- **StratIq Architectural Decision:** StratIq's population engine must follow BharatSim's precedent for Indian urban centers: using Census Ward boundaries and MoSPI urban consumption distributions rather than assuming Western metropolitan demographic structures.

---

## 2. Discrete Choice Modelling & Consumer Preferences

### 2.1 McFadden (1974) — Conditional Logit Analysis of Qualitative Choice Behavior
- **Citation:** McFadden, D. (1974). *Conditional logit analysis of qualitative choice behavior*. In P. Zarembka (Ed.), *Frontiers in Econometrics* (pp. 105–142). Academic Press, New York.
- **Methodological Core:** Axiomatic derivation of the Multinomial and Conditional Logit models from Random Utility Maximization (RUM). Demonstrates that if utility is $U_{ij} = V_{ij} + \epsilon_{ij}$ where $\epsilon_{ij}$ are independently and identically distributed with Type I Extreme Value (Gumbel) distributions, choice probabilities take the closed form:
  $$P_{ij} = \frac{\exp(V_{ij})}{\sum_{k \in C_i} \exp(V_{ik})}$$
- **StratIq Architectural Decision:** StratIq's static model uses this formulation, but with an ad-hoc outside utility $U_0 = 0.0$ and arbitrary weights $\beta_p = 1.0, \beta_q = 2.0$. Under McFadden's framework, coefficients must be identified and estimated via Maximum Likelihood Estimation (MLE) on choice data:
  $$\ln L(\boldsymbol{\beta}) = \sum_{n=1}^N \sum_{j \in C_n} y_{nj} \ln P_{nj}(\boldsymbol{\beta})$$
  The outside option (choosing not to patronize any local business) must be calibrated so that total captured market demand matches observed local service participation rates.
- **Key Invariant:** Independence of Irrelevant Alternatives (IIA). McFadden's conditional logit assumes odds ratios $P_{ij} / P_{ik}$ are independent of other alternatives in the choice set.

### 2.2 Train (2009) — Discrete Choice Methods with Simulation
- **Citation:** Train, K. E. (2009). *Discrete Choice Methods with Simulation* (2nd ed.). Cambridge University Press.
- **DOI:** [10.1017/CBO9780511805271](https://doi.org/10.1017/CBO9780511805271)
- **Methodological Core:** Comprehensive treatise on relaxing the IIA assumption via Mixed Logit (Random Parameters Logit). Utility coefficients vary across individuals: $\boldsymbol{\beta}_i \sim f(\boldsymbol{\beta} \mid \boldsymbol{\theta})$. Choice probabilities are evaluated via simulation-assisted likelihood integration:
  $$P_{ij} = \int \left( \frac{\exp(\boldsymbol{\beta}^\top \mathbf{x}_{ij})}{\sum_k \exp(\boldsymbol{\beta}^\top \mathbf{x}_{ik})} \right) f(\boldsymbol{\beta} \mid \boldsymbol{\theta}) d\boldsymbol{\beta}$$
- **StratIq Architectural Decision:** Heterogeneity across consumer segments (Budget, Mainstream, Premium) in StratIq is currently implemented by multiplying hardcoded weights. Train's Mixed Logit framework allows StratIq to specify continuous or discrete random coefficient distributions for price sensitivity $\beta_{p,i} \sim \text{Lognormal}(\mu_p, \sigma_p^2)$ and distance decay $\lambda_i \sim \text{Lognormal}(\mu_\lambda, \sigma_\lambda^2)$, ensuring non-negative cost disutilities and capturing realistic substitution patterns between competing clinics or shops.

---

## 3. Spatial Market Analysis & Gravity Formulations

### 3.1 Huff (1963) — A Probabilistic Analysis of Shopping Center Trade Areas
- **Citation:** Huff, D. L. (1963). *A probabilistic analysis of shopping center trade areas*. Land Economics, 39(1), 81–90.
- **DOI:** [10.2307/3144521](https://doi.org/10.2307/3144521)
- **Methodological Core:** Formulates probabilistic trade-area interaction where the probability that a consumer at origin $i$ selects shopping center $j$ is proportional to its attractiveness (retail square footage $S_j$) and inversely proportional to travel impedance ($T_{ij}^\lambda$):
  $$P_{ij} = \frac{S_j / T_{ij}^\lambda}{\sum_{k} (S_k / T_{ik}^\lambda)}$$
- **StratIq Architectural Decision:** StratIq uses an exponential distance decay $\exp(-\lambda d_{ij})$. Huff's model provides an essential baseline against which StratIq's discrete choice model must be benchmarked. Furthermore, Huff demonstrated that travel time $T_{ij}$, not Euclidean distance, governs spatial patronage. StratIq must replace constant circuity multipliers ($1.3$) with true network travel times.

### 3.2 Luo & Wang (2003) — Two-Step Floating Catchment Area (2SFCA)
- **Citation:** Luo, W., & Wang, F. (2003). *Measures of spatial accessibility to health care in a GIS environment: synthesis and a case study of the Chicago region*. Environment and Planning B: Planning and Design, 30(6), 865–884.
- **DOI:** [10.1068/b29120](https://doi.org/10.1068/b29120)
- **Methodological Core:** Measures spatial accessibility by accounting for both service capacity and competing population demand in two floating steps.
- **StratIq Architectural Decision:** Used to construct StratIq's spatial accessibility index and evaluate underserved "white space" zones where physician-to-population or clinic-to-population ratios are severely depressed.

---

## 4. Agent-Based Model Verification, Validation & Documentation

### 4.1 Grimm et al. (2006, 2010, 2020) — The ODD Protocol for Describing ABMs
- **Citation:** Grimm, V., Railsback, S. F., Vincenot, C. E., et al. (2020). *The ODD protocol for describing agent-based and other simulation models: A second update to improve clarity, replication, and structural realism*. Journal of Artificial Societies and Social Simulation (JASSS), 23(2), 7.
- **DOI:** [10.18564/jasss.4259](https://doi.org/10.18564/jasss.4259)
- **Methodological Core:** The international scientific standard for documenting Agent-Based Models across seven core sections: Overview (Purpose, Entities/State Variables, Scales, Process Overview/Scheduling), Design Concepts (Emergence, Adaptation, Objectives, Learning, Prediction, Sensing, Interaction, Stochasticity, Collectives, Observation), and Details (Initialization, Input Data, Submodels).
- **StratIq Architectural Decision:** StratIq's dynamic agent simulation in `abm.py` must be completely documented in `docs/research/ABM_ODD_PROTOCOL.md` adhering strictly to ODD requirements. Every state transition (Awareness, Consideration, Trial, Repeat, Churn) must declare its theoretical rationale, parameter sources, and verification boundaries.

### 4.2 Sargent (2013) — Verification and Validation of Simulation Models
- **Citation:** Sargent, R. G. (2013). *Verification and validation of simulation models*. Journal of Simulation, 7(1), 12–24.
- **DOI:** [10.1057/jos.2012.20](https://doi.org/10.1057/jos.2012.20)
- **Methodological Core:** Formal taxonomy distinguishing:
  1. *Conceptual Model Validity:* Checking that model assumptions and mathematical theories accurately represent the real-world domain.
  2. *Computerized Model Verification:* Software unit tests ensuring equations are computed without code errors.
  3. *Operational Validity:* Determining whether model output behavior possesses a satisfactory range of accuracy for the intended purpose against independent empirical holdout data.
- **StratIq Architectural Decision:** StratIq's current test suite (`test_engine.py`) only conducts *computerized model verification* (checking internal consistency). It conducts zero *operational validity* tests. StratIq must never claim empirical calibration or predictive accuracy until operational validation against holdout observations is executed and documented.

---

## 5. Global Sensitivity Analysis

### 5.1 Saltelli et al. (2008, 2010) — Global Sensitivity Analysis: The Primer & Variance-Based Methods
- **Citation:** Saltelli, A., Ratto, M., Andres, T., Campolongo, F., Cariboni, J., Gatelli, D., Saisana, M., & Tarantola, S. (2008). *Global Sensitivity Analysis: The Primer*. John Wiley & Sons.
- **Methodological Core:** Decomposes the total output variance $V(Y)$ into contributions from individual parameters and their interactions using Sobol sensitivity indices:
  $$S_i = \frac{V_{X_i}(E_{\mathbf{X}_{\sim i}}[Y \mid X_i])}{V(Y)}, \quad S_{Ti} = \frac{E_{\mathbf{X}_{\sim i}}[V_{X_i}(Y \mid \mathbf{X}_{\sim i})]}{V(Y)}$$
  Where $S_i$ is the first-order index (main effect) and $S_{Ti}$ is the total-order index (including all interactions involving parameter $i$).
- **StratIq Architectural Decision:** StratIq currently reports Spearman rank correlations across Monte Carlo draws and one-at-a-time (OAT) tornado sweeps. OAT fails to detect nonlinear parameter interactions (e.g. between price sensitivity and marketing half-saturation). StratIq must implement variance-based global sensitivity analysis using Sobol sequences (or Mara/Kucherenko methods for dependent parameters) to isolate which missing evidentiary parameters exert the largest influence on profitability and risk.
