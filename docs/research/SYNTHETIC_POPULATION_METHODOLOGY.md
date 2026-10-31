# Synthetic Population Synthesis Methodology

**Module:** `backend/app/engine/population/`  
**Theoretical References:**
- Beckman, R. J., Baggerly, K. A., & McKay, M. D. (1996). *Creating synthetic baseline populations*. Transportation Research Part A: Policy and Practice, 30(6), 415–429.
- Ye, X., Konduri, K., Pendyala, R. M., Sana, B., & Waddell, P. (2009). *A methodology to match distributions of both household and person attributes in the generation of synthetic populations*. TRB 88th Annual Meeting.
- BharatSim (Ashoka University & Swastik, 2022).

---

## 1. Mathematical Formulation

The synthesis engine re-engineers StratIq's population pipeline from arbitrary univariate sampling into a constrained entropy-minimization microsimulation.

### Optimization Problem:
Let $N$ be the number of synthesized consumer profiles, each initially endowed with baseline weights $w_i^{(0)} > 0$. The objective is to compute calibrated weights $w_i \ge 0$ satisfying $K$ marginal population constraints while minimizing information divergence (Kullback-Leibler distance):

$$\min_{\{w_i \ge 0\}} \sum_{i=1}^N w_i \ln\left(\frac{w_i}{w_i^{(0)}}\right)$$

Subject to:
$$\sum_{i=1}^N w_i X_{ik} = m_k \quad \forall k \in \{1, \dots, K\}$$

Where:
- $X_{ik} \in \{0, 1\}$ is an indicator variable indicating whether agent $i$ possesses demographic or spatial attribute $k$.
- $m_k$ is the target marginal total from empirical controls (WorldPop 17 age-sex bands and demand zone populations).

### Iterative Proportional Fitting Update:
For each constraint $k$ in iteration $t$:
$$w_i^{(t, k)} = w_i^{(t, k-1)} \times \left( \frac{m_k}{\sum_{j=1}^N w_j^{(t, k-1)} X_{jk}} \right)^{X_{ik}}$$

To guarantee numerical stability and eliminate extreme leverage points:
$$w_i \leftarrow \max\left(w_{\min}, \min\left(w_i, \bar{w} \times R_{\max}\right)\right)$$
Where $R_{\max} = 50.0$ and $w_{\min} = 10^{-6}$.

---

## 2. Supported Operational Modes

### Mode A: Calibrated Weighted Population (Scientific Baseline)
- Each synthetic record represents a non-negative continuous number of residents $w_i \ge 0$.
- Expected demand contributions:
  $$D_j = \sum_{i=1}^N w_i P_{ij} \times \text{frequency}_i$$
- This mode is strictly mass-conserving: $\sum_{i=1}^N w_i = \text{Catchment Population}$.

### Mode B: Exactly 10,000 Deterministic Representative Records
- For visualization, agent-based live market simulation, and individual-level simulation traces, exactly 10,000 records are generated.
- Integer weights are set to uniform resident representation:
  $$w_i = \frac{\text{Total Catchment Population}}{10,000}$$
- Agents are sampled via joint demographic-spatial probabilities derived from the calibrated matrix, preserving marginal totals with minimal discrepancy.
- Fully deterministic: identical random seed produces bit-for-bit identical coordinates, household structures, and demographics.

---

## 3. Household Structural Hierarchy

Unlike earlier versions that assigned age and sex independently without cohabitation realism:
1. **Household Sizing:** Households are synthesized first, following a shifted Poisson distribution around average household size ($\lambda = \text{avg\_household\_size} - 1.0$), bounded in $[1, 9]$ persons.
2. **Spatial Co-location:** All members of the same household share the exact same geographic centroid (within building jitter).
3. **Socio-Economic Consistency:** Household members share the same expenditure decile, preventing absurdities like an affluent parent cohabiting with a poverty-tier dependent.

---

## 4. Diagnostics & Invariants

The engine guarantees:
1. **Non-negativity:** $\forall i, w_i \ge 0$.
2. **Effective Sample Size (ESS):**
   $$\text{ESS} = \frac{\left(\sum_i w_i\right)^2}{\sum_i w_i^2}$$
   Monitored to detect weight collapse or extreme concentration.
3. **Marginal Discrepancy Reporting:** Absolute and relative errors are recorded per demographic band and spatial cell.
