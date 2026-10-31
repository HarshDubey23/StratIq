# StratIq Agent-Based Market Simulation: ODD Protocol Specification

**Standard:** Grimm, V., Railsback, S. F., Vincenot, C. E., Berger, U., Gallagher, C., DeAngelis, D. L., Edmonds, B., Ge, J., Giske, J., Groeneveld, J., Johnston, A. S. A., Milles, A., Müller, M. S., Norman, W. C., Pe’er, G., Radchuk, V., Thorngate, P. W., Wynne, F., & Ayllón, D. (2020). *The ODD protocol for describing agent-based and other simulation models: A review and first update*. Ecological Modelling, 438, 109347.

**Module:** `backend/app/engine/abm.py`  
**Model Version:** `siq-abm-2.0`  
**Auditor Reference:** StratIq Scientific Transformation Phase 7

---

## 1. Overview

### 1.1 Purpose and Patterns
The StratIq Agent-Based Model (ABM) simulates the dynamic emergence of local retail and service demand over time ($t \in [1, 84]$ days). While the static discrete choice engine (`siq-choice-1.1`) evaluates equilibrium market share under stationary conditions, the ABM captures:
1. **Dynamic Customer Acquisition & Awareness Diffusion:** Word-of-mouth (WOM), localized storefront foot-traffic signage, and saturating digital paid reach.
2. **Habit Formation & Switching Inertia:** Asymmetric repeat probability and customer lock-in.
3. **Capacity Constraints & Congestion Scars:** Turning away customers due to clinical chair / appointment or facility capacity limits, producing long-lasting negative utility memory.
4. **Cohort Lifecycle Dynamics:** Clear tracking of agents across Unaware, Aware, Considering, Trial, Loyal, and Churned states.
5. **Deterministic Cohort Transition Baseline:** An exact analytical expected-value Markov baseline $\mathbf{n}_{t+1} = \mathbf{n}_t \mathbf{T}_t$ completely decoupled from pseudo-random number generator variance.

### 1.2 Entities, State Variables, and Scales
The model comprises three primary entities:
- **Spatial Demand Zones ($z \in \{1, \dots, Z\}$):** Centroids endowed with residential population $W_z$, activity points, geographic coordinates $(\text{lat}_z, \text{lng}_z)$, and cumulative resident customer counts.
- **Competitors & Focal Business ($j \in \{0, \dots, J\}$):**
  - $j=0$: The user's focal enterprise.
  - $j \in \{1, \dots, J\}$: Identified direct and partial local competitors within catchment reach.
  - State variables: Coordinates $(\text{lat}_j, \text{lng}_j)$, unit price $p_j$, quality index $q_j \in [0, 1]$, and throughput capacity $K$.
- **Synthetic Consumer Agents ($i \in \{1, \dots, N\}$):**
  - Static attributes: Lat/Lng coordinate $(x_i, y_i)$, demographic age band, sex, socio-economic segment $s \in \{0, 1, 2\}$, travel mode $m$, willingness to pay $\text{WTP}_i$, price sensitivity $\beta_{p, i}$, quality sensitivity $\beta_{q, i}$, digital responsiveness, social connectivity, and purchase frequency.
  - Dynamic state variables:
    - $\text{aware}_i(t) \in \{0, 1\}$: Binary awareness indicator for focal business $j=0$.
    - $\text{channel}_i \in \{\text{paid}, \text{signage}, \text{wom}\}$: Discovery attribution channel.
    - $\text{habit}_{ij}(t) \in [0, \text{habit\_cap}]$: Accumulated loyalty utility toward alternative $j$.
    - $\text{congestion}_i(t) \in \mathbb{N}_{\ge 0}$: Days of negative congestion memory remaining from capacity turn-aways.
    - $\text{member\_of}_i(t) \in \{-1, 0, \dots, J\}$: Current membership / subscription commitment.
    - $\text{purchases}_{i, 0}$: Cumulative visits / transactions completed at focal business.

**Temporal & Spatial Scales:**
- Time step: Discrete 1 day ($\Delta t = 1$ day), simulated over a default horizon of 84 days (12 weeks).
- Spatial extent: Urban catchment area (typically 1.5 km to 5.0 km radius).
- Agent scale: Each simulated agent represents $s = \frac{\sum_z W_z}{N}$ real-world residents.

### 1.3 Process Overview and Scheduling
Within each day $t \in \{1, \dots, T\}$, sub-processes execute in strict synchronous order:
1. **Awareness Propagation:**
   - Unaware agents evaluate hazard from digital paid marketing, neighborhood word-of-mouth pressure, and proximate signage exposure.
2. **Congestion Memory Decay:**
   - Memory of past turn-aways decays: $\text{congestion}_i(t) \leftarrow \max(0, \text{congestion}_i(t-1) - 1)$.
3. **Market Activation & Decision Set Identification:**
   - In-market agents draw stochastic arrival based on purchase frequency $\lambda_i / 30$.
4. **Random Utility Choice:**
   - Active agents compute random utilities across reachable known alternatives and outside option $U_0$.
5. **Capacity Evaluation & Rejection:**
   - Real-time queuing against daily operational throughput limit $K / 30$. Excess arrivals are turned away and accumulate congestion penalties.
6. **Habit Update & Churn Tracking:**
   - Successful transactions reinforce habit: $\text{habit}_{ij} \leftarrow \min(\text{habit}_{ij} + \Delta h, h_{\max})$.
7. **Deterministic Cohort Transition Baseline Step:**
   - Analytical matrix multiplication $\mathbf{n}_{t+1} = \mathbf{n}_t \mathbf{T}_t$ is computed for benchmark validation.

---

## 2. Design Concepts

### 2.1 Basic Principles
The model integrates:
- McFadden Random Utility Maximization (RUM) under extreme value (Gumbel) taste disturbances.
- Bass (1969) innovation and imitation diffusion dynamics for word-of-mouth propagation.
- Discrete-time Markov chain cohort transitions for analytical tractability.

### 2.2 Emergence
Market share ramp-up curves, word-of-mouth geographic clustering, and capacity bottlenecks emerge endogenously from interactions between agent locations, travel tolerances, and firm operational constraints.

### 2.3 Adaptation
Agents adapt their choice behavior based on:
- Experiential habit: Repeated positive visits increase stickiness.
- Service denial: Being turned away induces a temporary utility penalty ($\Delta U_{\text{cong}} = -1.0$) lasting 14 days, driving agents to competitors or outside options.

### 2.4 Objectives
Agents maximize immediate perceived random utility $U_{ij} = V_{ij} + \epsilon_{ij}$.

### 2.5 Learning
Agents remember past interactions:
- Cumulative visit count increments with each purchase.
- Rejection memory persists for `congestion_memory` days.

### 2.6 Prediction
Agents do not engage in multi-period forward planning; choice is myopic given current information, awareness, and habit states.

### 2.7 Sensing
Agents possess complete knowledge of prices, distances, and qualities of all competitors within their travel tolerance, but become aware of the focal firm only when reached by marketing, proximity, or social peers.

### 2.8 Interaction
- Indirect interaction via firm capacity limits (congestion).
- Direct peer interaction via zone-level customer density driving word-of-mouth adoption.

### 2.9 Stochasticity
Stochasticity is employed in agent spatial coordinates (within-hex jitter), demographic attributes (beta/gamma draws), choice arrivals (Poisson/Bernoulli draws), and Gumbel taste noise.
*Crucial addition:* The deterministic cohort transition baseline eliminates stochasticity entirely to allow exact replication and scientific auditing.

### 2.10 Collectives
Agents belong to socio-economic segments (Budget, Mainstream, Premium) and spatial demand zone aggregates.

### 2.11 Observation
Daily metrics recorded:
- Daily visits to focal business, competitors, and outside option.
- Cumulative unique customer reach and trial rate.
- Daily turn-away count and capacity binding frequency.
- Final market share, demographic composition, and average trip length.

---

## 3. Details

### 3.1 Initialization
- Total agents $N$ (default 6,000) are placed proportionally to zone weights $W_z$.
- Initial awareness of focal firm: 0% ($\text{aware}_i(0) = 0$).
- Competitor awareness: 100% for reachable alternatives within $\text{max\_km} \times \text{tol}_i$.
- Initial habit: $\text{habit}_{ij}(0) = 0$.

### 3.2 Input Data
- Census / WorldPop age-sex distribution (17 five-year cohorts).
- OpenStreetMap building footprints and amenity locations.
- User operational inputs: price, quality, capacity parameters, fixed costs.

### 3.3 Submodels

#### 3.3.1 Awareness Spread Submodel
Daily awareness probability for unaware agent $i$ residing in zone $z$:
$$P(\text{aware}_i(t)) = 1 - (1 - p_{\text{paid}})(1 - p_{\text{wom}})(1 - p_{\text{sign}})$$
Where:
- $p_{\text{paid}} = 1 - \exp\left(-\frac{\text{daily\_paid} \times \text{digital}_i}{\overline{\text{digital}}}\right)$
- $p_{\text{wom}} = \text{clip}\left(\text{wom\_rate} \times \text{social}_i \times \frac{\text{Customers}_z(t)}{N_z} \times 30, 0, 0.5\right)$
- $p_{\text{sign}} = \begin{cases} \text{signage\_daily} & \text{if } d_{i, 0} \le \text{signage\_radius} \\ 0 & \text{otherwise} \end{cases}$

#### 3.3.2 Discrete Choice & Utility Submodel
Perceived utility for alternative $j \in \{0, \dots, J\}$:
$$U_{ij}(t) = V_{ij}^{\text{static}} + \text{habit}_{ij}(t) - \mathbf{1}_{\{j=0, \text{cong}_i > 0\}} \cdot \text{pen}_{\text{cong}} + \epsilon_{ij}$$
With outside option utility:
$$U_{i, \text{none}} = U_0 + \epsilon_{i, 0}$$
Where $\epsilon \sim \text{Gumbel}(0, \sigma_{\text{noise}})$.

#### 3.3.3 Deterministic Cohort Transition Matrix Submodel
Let state vector $\mathbf{n}_t = [n_U, n_A, n_C, n_T, n_R, n_L]_t$.
The deterministic cohort update is:
$$\mathbf{n}_{t+1} = \mathbf{n}_t \mathbf{T}_t$$

Where transition matrix $\mathbf{T}_t$ is structured as:
$$\mathbf{T}_t = \begin{bmatrix}
1 - p_{\text{aware}} & p_{\text{aware}} & 0 & 0 & 0 & 0 \\
0 & 1 - p_{\text{in}} & p_{\text{in}} & 0 & 0 & 0 \\
0 & 1 - P_{\text{user}} & 0 & P_{\text{user}} & 0 & 0 \\
0 & 0 & 0 & 1 - p_{\text{loyal}} - p_{\text{churn}} & p_{\text{loyal}} & p_{\text{churn}} \\
0 & 0 & 0 & 0 & 1 - p_{\text{churn}} & p_{\text{churn}} \\
0 & 0 & p_{\text{winback}} & 0 & 0 & 1 - p_{\text{winback}}
\end{bmatrix}$$

**Mathematical Invariant:**
$$\forall i, \sum_{j=1}^6 T_{ij} = 1.0 \quad \text{and} \quad \sum_{j=1}^6 n_j(t) = \text{Total Catchment Population}$$

This guarantees strict mass balance and provides an infallible benchmark for stochastic simulation auditing.
