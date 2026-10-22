import { ArrowRight, BarChart3, Compass, GitCompareArrows, MapPinned, Scale, ShieldCheck, Store, TrendingUp } from "lucide-react";
import Link from "next/link";
import { Logo } from "@/components/brand";
import { MarketPreview } from "@/components/MarketPreview";

const steps = [
  { n: "01", t: "Define", d: "Describe any business in your own words, plus its pricing, capacity and costs." },
  { n: "02", t: "Discover", d: "Search any place. Competitors, buildings and population are pulled live, with sources and timestamps." },
  { n: "03", t: "Simulate", d: "10,000 synthetic customers, placed by real population density and each carrying a 615-parameter genome, choose day by day between you, competitors and not buying." },
  { n: "04", t: "X-ray", d: "Click any customer to see why they chose a competitor — price, travel, opening hours, trust — down to the individual parameter." },
  { n: "05", t: "Decide & verify", d: "Compare scenarios, see downside risk, and get a field survey that measures the assumptions your result depends on." },
];

const uses = [
  { i: Store, t: "Starting a business", d: "Test whether a location can support a gym, café, pharmacy or any other local business before signing a lease." },
  { i: MapPinned, t: "Finding the right location", d: "Compare up to five candidate sites on the same model: catchment, competition, affordability and economics." },
  { i: TrendingUp, t: "Growing an existing business", d: "Enter your actual figures and probe hypotheses: pricing mismatch, competitive pressure or a weak catchment." },
  { i: BarChart3, t: "Optimising price and marketing", d: "Price and marketing sweeps show where modeled profit peaks, and how sure you can be." },
  { i: GitCompareArrows, t: "Comparing strategies", d: "Rank scenarios by your goal: expected profit, lowest risk of loss, fastest payback or most customers." },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-ink-950">
      <header className="sticky top-0 z-40 border-b border-ink-800/80 bg-ink-950/85 backdrop-blur">
        <nav className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <Logo />
          <div className="hidden items-center gap-6 text-sm text-ink-300 md:flex">
            <a href="#product" className="hover:text-ink-100">Product</a>
            <a href="#how" className="hover:text-ink-100">How it works</a>
            <a href="#uses" className="hover:text-ink-100">Use cases</a>
            <Link href="/methodology" className="hover:text-ink-100">Methodology</Link>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/sign-in" className="px-3 py-1.5 text-sm text-ink-200 hover:text-ink-100">Sign in</Link>
            <Link href="/sign-up" className="inline-flex h-9 items-center gap-1.5 rounded-md bg-accent px-4 text-sm font-medium text-ink-950 hover:bg-cyan-300">
              Simulate your business
            </Link>
          </div>
        </nav>
      </header>

      <section className="grid-bg relative border-b border-ink-800">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 md:py-24 lg:grid-cols-[1fr_1.15fr]">
          <div>
            <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-ink-600 bg-ink-900 px-3 py-1 text-xs text-ink-300">
              <span className="h-1.5 w-1.5 rounded-full bg-accent" /> Market simulation for small businesses
            </p>
            <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight text-ink-100 md:text-5xl">
              Test your business before you risk your money.
            </h1>
            <p className="mt-5 max-w-xl text-[17px] leading-relaxed text-ink-300">
              Explore real-world market evidence, simulate customer decisions, compare locations and evaluate strategies before you commit to your next move.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/sign-up" className="inline-flex h-11 items-center gap-2 rounded-md bg-accent px-5 text-[15px] font-medium text-ink-950 hover:bg-cyan-300">
                Simulate your business <ArrowRight className="h-4 w-4" />
              </Link>
              <Link href="/sign-up?demo=1" className="inline-flex h-11 items-center gap-2 rounded-md border border-ink-600 bg-ink-900 px-5 text-[15px] text-ink-100 hover:bg-ink-800">
                Explore a demo
              </Link>
            </div>
            <div className="mt-8 grid max-w-lg grid-cols-3 gap-3">
              {[["10,000", "synthetic agents per run, at real population density"], ["615", "parameters in every agent's genome"], ["6.15M", "parameters simulated over 84 days"]].map(([n, l]) => (
                <div key={l} className="rounded-md border border-ink-700 bg-ink-900/70 p-3">
                  <div className="num text-xl font-semibold text-accent">{n}</div>
                  <div className="mt-0.5 text-[11px] leading-snug text-ink-400">{l}</div>
                </div>
              ))}
            </div>
            <p className="mt-6 text-xs text-ink-400">Works for any business type and any searchable place. Estimates, not guarantees.</p>
          </div>
          <div id="product">
            <MarketPreview />
          </div>
        </div>
      </section>

      <section className="border-b border-ink-800">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-20 md:grid-cols-[1fr_1.4fr]">
          <h2 className="text-3xl font-semibold tracking-tight">A business decision is more than a guess.</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              { t: "A map", d: "shows some nearby competitors, but not whether customers can afford you, or will choose you." },
              { t: "A spreadsheet", d: "calculates margins, but the customer numbers in it are whatever you typed." },
              { t: "A chatbot", d: "gives generic advice that is not tied to your street, your prices or your costs." },
            ].map((x) => (
              <div key={x.t} className="rounded-lg border border-ink-700 bg-ink-900 p-4">
                <div className="text-sm font-semibold text-ink-100">{x.t}</div>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-300">{x.d}</p>
              </div>
            ))}
            <div className="rounded-lg border border-accent/30 bg-accent/5 p-4 sm:col-span-3">
              <p className="text-sm leading-relaxed text-ink-200">
                <span className="font-semibold text-accent">StrataIQ connects them.</span> Live geographic evidence feeds a customer-choice model, and the model feeds
                your monthly economics. When you change a price, a location or a competitor, the whole chain re-runs.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section id="how" className="border-b border-ink-800">
        <div className="mx-auto max-w-6xl px-4 py-20">
          <h2 className="text-3xl font-semibold tracking-tight">How it works</h2>
          <div className="mt-10 grid gap-px overflow-hidden rounded-lg border border-ink-700 bg-ink-700 md:grid-cols-5">
            {steps.map((s) => (
              <div key={s.n} className="bg-ink-900 p-6">
                <div className="num text-xs text-accent">{s.n}</div>
                <div className="mt-3 text-lg font-semibold">{s.t}</div>
                <p className="mt-2 text-sm leading-relaxed text-ink-300">{s.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="uses" className="border-b border-ink-800">
        <div className="mx-auto max-w-6xl px-4 py-20">
          <h2 className="text-3xl font-semibold tracking-tight">Use cases</h2>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {uses.map(({ i: I, t, d }) => (
              <div key={t} className="rounded-lg border border-ink-700 bg-ink-900 p-5">
                <I className="h-5 w-5 text-accent" />
                <div className="mt-3 font-semibold">{t}</div>
                <p className="mt-1.5 text-sm leading-relaxed text-ink-300">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-ink-800">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-20 md:grid-cols-2">
          <div>
            <ShieldCheck className="h-6 w-6 text-model" />
            <h2 className="mt-4 text-3xl font-semibold tracking-tight">Know what is known, what is estimated, and what is missing.</h2>
            <p className="mt-4 text-[15px] leading-relaxed text-ink-300">
              Every figure carries a label. Observed map data, official population estimates, your own inputs, model assumptions and simulated outcomes are never shown as equally certain.
              When local data is thin, StrataIQ says so, and tells you what to check.
            </p>
            <Link href="/methodology" className="mt-6 inline-flex items-center gap-1.5 text-sm text-accent hover:underline">
              Read the methodology <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
          <div className="space-y-2.5">
            {[
              ["Observed", "Competitor locations and buildings from OpenStreetMap, with retrieval and last-edit times", "text-observed border-observed/40"],
              ["Official estimate", "Gridded population from WorldPop (fixed reference year)", "text-sky-300 border-sky-400/40"],
              ["User-entered", "Your prices, costs, capacity, and competitors you saw on the ground", "text-userdata border-userdata/40"],
              ["Assumption", "Behaviour parameters with documented ranges you can change", "text-ink-200 border-ink-500"],
              ["Model estimate", "Demand, revenue, profit and risk computed by the simulation", "text-model border-model/40"],
            ].map(([k, d, c]) => (
              <div key={k} className="flex items-start gap-3 rounded-md border border-ink-700 bg-ink-900 p-3">
                <span className={`mt-0.5 shrink-0 rounded border px-1.5 py-px text-[10px] font-medium uppercase tracking-wide ${c}`}>{k}</span>
                <span className="text-sm text-ink-300">{d}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-6xl px-4 py-24 text-center">
          <Scale className="mx-auto h-6 w-6 text-accent" />
          <h2 className="mt-4 text-3xl font-semibold tracking-tight md:text-4xl">Make the next move with evidence.</h2>
          <Link href="/sign-up" className="mt-8 inline-flex h-11 items-center gap-2 rounded-md bg-accent px-6 text-[15px] font-medium text-ink-950 hover:bg-cyan-300">
            Build your first market simulation <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      <footer className="border-t border-ink-800">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-4 px-4 py-8 text-xs text-ink-400 md:flex-row md:items-center">
          <div className="flex items-center gap-3">
            <Compass className="h-4 w-4" /> StrataIQ. Model outputs are estimates under stated assumptions, not financial advice or guarantees.
          </div>
          <div>Map data © OpenStreetMap contributors · Population © WorldPop (CC BY 4.0) · Tiles © OpenFreeMap / OpenMapTiles</div>
        </div>
      </footer>
    </div>
  );
}
