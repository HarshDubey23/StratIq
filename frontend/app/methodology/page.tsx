import Link from "next/link";
import { Logo } from "@/components/brand";

function Eq({ children }: { children: React.ReactNode }) {
  return <pre className="num overflow-x-auto rounded-2xl border border-white/[0.07] bg-white/[0.025] p-3 text-[13px] leading-relaxed text-ink-100">{children}</pre>;
}

export default function Methodology() {
  return (
    <div className="min-h-screen bg-ink-950">
      <header className="border-b border-white/[0.06]">
        <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-4">
          <Logo />
          <Link href="/app" className="text-sm text-ink-300 hover:text-ink-100">Open app</Link>
        </div>
      </header>
      <article className="mx-auto max-w-4xl space-y-10 px-4 py-12 text-[15px] leading-relaxed text-ink-200">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-ink-100">Methodology and data quality</h1>
          <p className="mt-3 text-ink-300">
            StrataIQ does not know every customer or every business in a city. It combines the best available public evidence with explicit behavioural and
            financial models, so that every assumption is visible and can be changed. Results are conditional model estimates, not predictions or guarantees.
          </p>
        </div>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-ink-100">1. Open categories</h2>
          <p>
            You can describe any business. The text is matched to a catalogue of OpenStreetMap tags; if nothing matches, an optional AI step proposes tags that are validated
            against an allow-list, and the final fallback searches business names for your keyword. Each category is assigned to one of six economic model types (membership,
            dine-in, takeaway, retail, appointment, lodging). The model type decides what a sold “unit” is and how capacity works. You can always override it.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-ink-100">2. Live market evidence</h2>
          <ul className="list-disc space-y-1.5 pl-5">
            <li><b>Competitors:</b> OpenStreetMap via the Overpass API, fetched when you load a location. Each record keeps its OSM reference, last-edit time, and our retrieval time. Contributor usernames are discarded.</li>
            <li><b>Population:</b> WorldPop 100 m gridded estimates (reference year shown) summed over the catchment, then distributed across ~300 m demand zones in proportion to mapped buildings (dasymetric mapping). Where building data is thin, population is spread uniformly and flagged.</li>
            <li><b>Catchment:</b> a straight-line radius, or a travel-time area from openrouteservice when a routing key is configured. The method in use is always labelled.</li>
            <li><b>Coverage indicator:</b> computed from mapped buildings per 1,000 residents, completeness and edit recency of competitor records. It is a heuristic, not a measured recall rate.</li>
            <li>Retrieval time is not the same as the time the underlying data was last updated; both are shown.</li>
          </ul>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-ink-100">3. Customer-choice model</h2>
          <p>For demand zone z, synthetic segment s (budget, mainstream, premium) and alternative j (your business, each competitor):</p>
          <Eq>{`N_zs  = W_z · participation · share_s                     in-market people per month
F_sj  = 1 − Φ( (ln p_j − ln(m_s · p_ref)) / σ )             affordability (lognormal willingness-to-pay)
V_zsj = β_q (q_j − 0.5) − β_p k_s ln(p_j / p_ref) − (λ / t_s) d_zj + ln a_j
A_zsj = F_sj · exp(V_zsj) · 1[d_zj ≤ max_km · t_s]
P_zsj = A_zsj / ( exp(U_0) + Σ_k A_zsk )                    multinomial logit with an outside option
D_j   = Σ_zs N_zs · P_zsj · frequency                       units per month
Q_0   = min(D_0, K)                                         capacity-constrained`}</Eq>
          <p>
            W is resident-equivalents (residents, plus mapped activity points for categories that also serve visitors). d is estimated road distance (straight-line × a circuity
            factor unless routing is available). a is awareness, which rises with marketing spend along a saturating curve for your new business. p_ref is the local reference
            price: entered by you, derived from competitor prices you recorded, or, if neither exists, your baseline price (flagged as an assumption).
            The outside option means customers are never forced to pick a modeled business.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-ink-100">3a. Real-data spending power, willingness to pay and distance (India)</h2>
          <p>
            Segments are not fixed constants. Each synthetic person gets a monthly per-capita consumption (MPCE, ₹) from official data, and the
            three segments are India&apos;s bottom 40 %, middle 40 % and top 20 % by MPCE, so their shares are this area&apos;s real mix.
          </p>
          <Eq>{`F(x) = 1 − (1 + (x/b)^a)^(−q)                   Singh-Maddala curve fitted to HCES 2023-24 (MoSPI) deciles, per state × rural/urban
p_t  = population-weighted RWI rank of tile t within its state × sector      (Meta Relative Wealth Index, 2.4 km, × WorldPop)
z_i  = a · Φ⁻¹(p_t) + √(1 − a²) · ε_i,  ε_i ~ N(0,1)                         rank matching (Hruschka et al. 2015; Chi et al. 2022)
x_i  = F⁻¹(Φ(z_i))                                                           person i's MPCE; reproduces the official curve exactly
WTP_i = p_ref · (x_i / x_ref)^η_c · taste_i                                  x_ref = urban India median MPCE; η_c = income elasticity
π_local = π_India · E_local[(x/x_ref)^η] / E_India[(x/x_ref)^η]             participation anchored to a published penetration rate
d_zj = OSRM road-network distance (car), t_zj = OSRM walking time             zone → every business; straight line × circuity only if routing fails`}</Eq>
          <ul className="list-disc space-y-1 pl-5">
            <li><b>Official:</b> HCES 2023-24 Tables 3.1 and 3.4R/U (all-India fractiles; P10–P90 for 18 states, rural and urban). Fit error is reported with every run.</li>
            <li><b>Derived:</b> tile state from geoBoundaries ADM1; urban = WorldPop density above the threshold that makes 35 % of India urban (UN WUP 2018).</li>
            <li><b>Published evidence:</b> gym membership 0.8 % of India (Deloitte & HFA 2025, industry), dental visits 24 %/year (Talukdar et al. 2022), private coaching 25.5 % rural / 30.7 % urban of students (NSO CMS: Education 2025), dining out 3.7×/month (NRAI 2024, industry), health-spend income elasticity ≈ 0.25 (Dubey 2020), work-trip mode shares walk 28.3 % / two-wheeler 42.6 % (MoSPI NHTS 2025-26).</li>
            <li><b>Still assumptions</b> (labelled and varied in Monte Carlo): the between-tile loading a = 0.6, income elasticities for services, the taste spread of WTP, price and quality coefficients, distance decay. No Indian study calibrates these for local services yet.</li>
            <li>Limits: RWI tiles are 2.4 km, so a slum and the rich block next to it share a tile; RWI is CC BY-NC 4.0 (non-commercial); outside India the archetype assumptions are used.</li>
          </ul>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-ink-100">4. Economics</h2>
          <Eq>{`Revenue          = price × Q
Variable cost    = variable cost per unit × Q
Fixed cost       = rent + payroll + utilities + other fixed + marketing
Operating profit = Revenue − Variable cost − Fixed cost          (monthly)
Break-even units = Fixed cost / (price − variable cost per unit)
Payback          = startup cost / operating profit`}</Eq>
          <p>Taxes, financing, depreciation and working capital are not included and are listed as exclusions on every result.</p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-ink-100">5. Uncertainty and sensitivity</h2>
          <p>
            Each behavioural parameter has a documented low/high range. Monte Carlo draws parameters from triangular distributions over those ranges (fixed random seed, so a
            run is reproducible) and reports P10/P50/P90 profit and the modeled probability of a loss. These probabilities are conditional on the assumed ranges; they are not
            calibrated real-world probabilities. One-at-a-time sensitivity (tornado), price and marketing sweeps, stress tests and Spearman rank correlations identify which
            assumptions move the result most. These describe the model, not proven real-world causes.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-ink-100">6. Synthetic agents and the 615-parameter genome</h2>
          <p>
            The live market places 10,000 synthetic agents in proportion to real population density (WorldPop totals spread over OpenStreetMap buildings). Each agent
            carries a 615-parameter genome: 46 values measured from real geography (position, distance and travel time to every mapped business), 16 correlated latent
            traits (income, price consciousness, time poverty, digital nativity…) drawn conditionally on the agent&apos;s age and income segment, and 553 parameters
            generated from those traits plus noise (hour-by-hour availability, 40 attribute importances and minimums, 48 media-channel parameters, price psychology,
            mobility, retention, category affinities, lifestyle and constraints).
          </p>
          <Eq>{`x_k = mu_k + loadings_k · z + sd_k · eps        z ~ N(mu_z | age, income segment ; Sigma)
V_ij = price_ij + quality_j + travel_ij + hours_fit_ij + attributes_ij + expectation_gap_ij + trust_ij + lifestyle_ij
choice = argmax( V_ij + habit_ij + noise_i · Gumbel ,  outside_i + noise_i · Gumbel )`}</Eq>
          <p>
            Every one of the 615 parameters reaches a decision (choice utility, participation, outside option, awareness, word of mouth, retention or noise); the test
            suite fails if any is unused. Click an agent to see its genome and why it chose what it chose. These are documented assumptions conditioned on real
            evidence, not data about real people, and more parameters do not by themselves mean more accuracy. Before a run, demand is checked against incumbents:
            businesses that exist need customers, so if the model leaves nearby incumbents below a survival floor, participation is raised (bounded at ×2.5 and reported).
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-ink-100">7. Recommendations and AI</h2>
          <p>
            Verdicts, rankings and recommendations are produced by documented rules over the computed results. An optional language model can paraphrase the result in plain
            language; every number it writes must already exist in the result, otherwise the paraphrase is discarded. The language model never produces the numbers.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-ink-100">8. Validation status</h2>
          <p>
            The default behavioural parameters are not yet calibrated against observed sales data, and no accuracy figure is claimed. Unit and invariant tests check the
            mathematics (for example, that higher prices lower demand and that an added competitor reduces your share). The Monitoring page lets you record real outcomes and
            computes forecast error (WAPE) from them; the model is not automatically recalibrated.
          </p>
        </section>

        <section className="space-y-2 border-t border-white/[0.06] pt-6 text-sm text-ink-400">
          <p>Map data © OpenStreetMap contributors (ODbL). Population: WorldPop, University of Southampton (CC BY 4.0). Map tiles: OpenFreeMap, © OpenMapTiles. Routing: openrouteservice by HeiGIT.</p>
        </section>
      </article>
    </div>
  );
}
