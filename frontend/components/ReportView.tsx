/* eslint-disable @typescript-eslint/no-explicit-any */
import { money, num, pct, when } from "@/lib/format";
import type { CompetitorRec, Decision, Scenario, SimResult, Snapshot, Location, Archetype, Category } from "@/lib/types";

export interface ReportContent {
  generated_at: string;
  project: { name: string; objective: string; decision_goal: string; category: Category; profile: Record<string, unknown>; is_demo: boolean };
  archetype: Archetype;
  locations: { location: Location; snapshot: (Pick<Snapshot, "retrieved_at" | "status" | "catchment_method" | "population" | "coverage" | "sources" | "errors" | "catchment_geojson">) | null }[];
  competitors: CompetitorRec[];
  scenarios: { scenario: Scenario; result: Partial<SimResult> | null }[];
  decision: Decision;
  disclaimer: string;
}

function H({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <h2 className="mb-3 mt-8 flex items-baseline gap-2 border-b border-black/[0.07] pb-1.5 text-base font-semibold">
      <span className="num text-xs text-ink-400">{String(n).padStart(2, "0")}</span>
      {children}
    </h2>
  );
}

function MiniMap({ loc, snap, comps }: { loc: Location; snap: ReportContent["locations"][number]["snapshot"]; comps: CompetitorRec[] }) {
  const ring = snap?.catchment_geojson?.coordinates?.[0] || [];
  if (!ring.length) return null;
  const xs = ring.map((c) => c[0]);
  const ys = ring.map((c) => c[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const W = 260;
  const sx = (x: number) => ((x - x0) / (x1 - x0 || 1)) * W;
  const sy = (y: number) => W - ((y - y0) / (y1 - y0 || 1)) * W;
  return (
    <svg viewBox={`-10 -10 ${W + 20} ${W + 20}`} className="h-56 w-56 shrink-0 rounded border border-black/[0.07] bg-ink-900" role="img" aria-label="Catchment and competitors">
      <polygon points={ring.map((c) => `${sx(c[0])},${sy(c[1])}`).join(" ")} fill="rgba(34,211,238,0.07)" stroke="#2F49FF" strokeDasharray="4 3" />
      {comps.filter((c) => c.active).map((c) => (
        <circle key={c.id} cx={sx(c.lng)} cy={sy(c.lat)} r={4} fill={c.source === "user" ? "#C59BFF" : "#F59E0B"} stroke="#FFFFFF" />
      ))}
      <circle cx={sx(loc.lng)} cy={sy(loc.lat)} r={6} fill="#2F49FF" stroke="#FFFFFF" strokeWidth={2} />
    </svg>
  );
}

export function ReportView({ c }: { c: ReportContent }) {
  const d = c.decision;
  const prof = c.project.profile as Record<string, any>;
  const ran = c.scenarios.filter((s) => s.result);
  return (
    <article className="print-light mx-auto max-w-4xl rounded-lg border border-black/[0.07] bg-ink-950 p-6 text-sm leading-relaxed text-ink-200 md:p-10">
      {c.project.is_demo && <div className="mb-4 rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs font-medium text-amber-800">DEMO SCENARIO — Illustrative market data; not verified live conditions.</div>}
      <header>
        <div className="text-xsst text-ink-400">StrataIQ feasibility report</div>
        <h1 className="mt-1 text-2xl font-semibold text-ink-100">{c.project.name}</h1>
        <p className="mt-1 text-xs text-ink-400">Generated {when(c.generated_at)} · model {d.model_version || "—"}</p>
        <p className="mt-3 rounded border border-black/[0.07] bg-ink-900 p-3 text-xs text-ink-300">{c.disclaimer}</p>
      </header>

      <H n={1}>Business concept</H>
      <p><b>{c.project.category.label}</b> — modeled as <b>{c.archetype.label}</b> ({c.archetype.unit_label} per month).</p>
      {prof.description && <p className="mt-1">{prof.description}</p>}
      {Array.isArray(prof.positioning) && prof.positioning.length > 0 && <p className="mt-1 text-ink-300">Claimed positioning (unverified): {prof.positioning.join(", ")}.</p>}
      <p className="mt-1 text-xs text-ink-400">Competitor search tags: {c.project.category.filters.join(" OR ")} ({c.project.category.method} match)</p>

      <H n={2}>Geographic area</H>
      <div className="space-y-4">
        {c.locations.map(({ location: l, snapshot: s }) => (
          <div key={l.id} className="flex flex-col gap-4 sm:flex-row">
            <MiniMap loc={l} snap={s} comps={c.competitors} />
            <div className="space-y-1">
              <div className="font-medium text-ink-100">{l.label}</div>
              <div className="text-xs text-ink-300">{l.address}</div>
              <div className="text-xs">Catchment: {s?.catchment_method === "isochrone" ? `${l.catchment.minutes} min ${l.catchment.profile}` : `${l.catchment.radius_km} km straight-line radius`}</div>
              {s?.population?.total ? <div className="text-xs">Population: {num(s.population.total)} ({s.population.source === "worldpop" ? "WorldPop estimate" : s.population.source === "user" ? "user-entered" : s.population.source}; placement: {s.population.method})</div> : <div className="text-xs text-amber-700">Population unavailable</div>}
              {s && <div className="text-xs">Data coverage: {s.coverage.level} — {s.coverage.note}</div>}
            </div>
          </div>
        ))}
      </div>

      <H n={3}>Data sources and timestamps</H>
      <table className="w-full text-xs">
        <thead><tr className="text-left text-ink-400"><th className="py-1 font-normal">Source</th><th className="font-normal">Layer</th><th className="font-normal">Retrieved</th><th className="font-normal">Source data as of</th><th className="font-normal">License</th></tr></thead>
        <tbody>
          {c.locations.flatMap(({ location: l, snapshot: s }) => (s?.sources || []).map((src, i) => (
            <tr key={`${l.id}-${i}`} className="border-t border-black/[0.06]">
              <td className="py-1">{src.name}</td><td>{src.layer}</td><td>{when(src.retrieved_at)}</td><td>{src.source_updated_at || "not reported"}</td><td>{src.license}</td>
            </tr>
          )))}
        </tbody>
      </table>
      {c.locations.some((l) => l.snapshot?.errors?.length) && <p className="mt-2 text-xs text-amber-700">Some sources failed: {c.locations.flatMap((l) => l.snapshot?.errors || []).map((e) => `${e.source} (${e.message})`).join("; ")}</p>}

      <H n={4}>Competitor overview</H>
      <p className="mb-2 text-xs text-ink-400">{c.competitors.filter((x) => x.active).length} active competitors ({c.competitors.filter((x) => x.source === "user").length} user-entered, {c.competitors.filter((x) => x.is_hypothetical).length} hypothetical). Prices are unknown unless recorded by the user.</p>
      <table className="w-full text-xs">
        <thead><tr className="text-left text-ink-400"><th className="py-1 font-normal">Name</th><th className="font-normal">Source</th><th className="text-right font-normal">Price</th><th className="text-right font-normal">Last edited</th></tr></thead>
        <tbody>
          {c.competitors.slice(0, 30).map((x) => (
            <tr key={x.id} className="border-t border-black/[0.06]"><td className="py-1">{x.name}{!x.active && " (excluded)"}</td><td>{x.source === "osm" ? "OpenStreetMap" : x.source === "foursquare" ? "Foursquare Places" : x.source === "user" ? (x.is_hypothetical ? "Hypothetical" : "User-observed") : "Demo"}</td><td className="text-right">{x.price ? money(x.price) : "unknown"}</td><td className="text-right">{x.source_updated_at ? when(x.source_updated_at).split(",")[0] : "—"}</td></tr>
          ))}
        </tbody>
      </table>

      <H n={5}>Catchment and accessibility</H>
      <p>Distances in the model are {c.locations.some((l) => l.snapshot?.catchment_method === "isochrone") ? "travel-time catchments from a routing engine where configured, otherwise" : ""} straight-line distances multiplied by a road-circuity factor (assumption). Customers beyond the category’s consideration radius do not consider the business.</p>

      <H n={6}>Main modeling assumptions</H>
      {ran[0]?.result?.parameters && (
        <table className="w-full text-xs">
          <tbody>
            {Object.entries(ran[0].result.parameters).map(([k, v]) => (
              <tr key={k} className="border-t border-black/[0.06]"><td className="py-1">{v.label}</td><td className="num text-right">{num(v.value, 4)}</td><td className="text-right text-ink-400">[{num(v.low, 3)} – {num(v.high, 3)}]</td><td className="text-right">{v.status}</td></tr>
            ))}
          </tbody>
        </table>
      )}

      <H n={7}>Estimated demand and financial results</H>
      {ran.map(({ scenario: s, result: r }) => r?.summary && r.finance && (
        <div key={s.id} className="mb-3">
          <div className="font-medium text-ink-100">{s.name}{s.is_baseline && " (baseline)"}</div>
          <p className="text-xs">Price {money(r.summary.price)} · modeled demand {num(r.summary.modeled_demand_units)} {r.unit_label ?? c.archetype.unit_label}/month (capacity {num(r.summary.capacity_units)}) · revenue {money(r.finance.revenue)} · operating cost {money((r.finance.fixed_cost || 0) + (r.finance.variable_cost || 0))} · <b>operating profit {money(r.finance.operating_profit)}</b> · break-even {num(r.finance.break_even_units)} units · payback {r.finance.payback_months ? `${num(r.finance.payback_months, 1)} months` : "not reached"}.</p>
          {r.monte_carlo && <p className="text-xs text-ink-400">Monte Carlo ({r.monte_carlo.draws} draws): profit P10 {money(r.monte_carlo.profit.p10)}, P50 {money(r.monte_carlo.profit.p50)}, P90 {money(r.monte_carlo.profit.p90)}; modeled probability of loss {pct(r.monte_carlo.prob_loss)}.</p>}
        </div>
      ))}

      <H n={8}>Scenario comparison</H>
      <table className="w-full text-xs">
        <thead><tr className="text-left text-ink-400"><th className="py-1 font-normal">Rank</th><th className="font-normal">Scenario</th><th className="text-right font-normal">Units</th><th className="text-right font-normal">Profit / mo</th><th className="text-right font-normal">P(loss)</th></tr></thead>
        <tbody>{d.ranking.map((r) => <tr key={r.scenario_id} className="border-t border-black/[0.06]"><td className="py-1">{r.rank}</td><td>{r.name}</td><td className="text-right">{num(r.units)}</td><td className="text-right">{money(r.profit)}</td><td className="text-right">{pct(r.prob_loss)}</td></tr>)}</tbody>
      </table>
      <p className="mt-2"><b>Result:</b> {d.headline}</p>

      <H n={9}>Downside risks</H>
      <ul className="list-disc space-y-1 pl-5">{d.risks.filter((r) => r.factor !== "Data gap").map((r, i) => <li key={i}>{r.text}</li>)}</ul>

      <H n={10}>Major unknowns</H>
      <ul className="list-disc space-y-1 pl-5">{(d.gaps || []).map((g) => <li key={g.key}>{g.text}</li>)}{!(d.gaps || []).length && <li>No critical data gaps were flagged by the rules; local verification is still recommended.</li>}</ul>

      <H n={11}>Recommended next actions</H>
      <ol className="list-decimal space-y-1 pl-5">{d.next_actions.map((a, i) => <li key={i}>{a.action} <span className="text-ink-400">— {a.why}</span></li>)}</ol>
      {d.recommendations.length > 0 && (
        <ul className="mt-3 space-y-2">
          {d.recommendations.map((r, i) => <li key={i} className="rounded border border-black/[0.07] p-2 text-xs"><b>{r.action}</b> {r.reason} Reconsider if: {r.reconsider_if}</li>)}
        </ul>
      )}

      <H n={12}>Methodology and limitations</H>
      <p>Demand is estimated with a multinomial-logit customer-choice model over synthetic customer segments placed on a population grid, with an outside option, lognormal affordability, distance decay and capacity limits. Uncertainty is propagated by Monte Carlo over documented parameter ranges. Default behaviour parameters are not calibrated against observed sales; no accuracy figure is claimed. See /methodology for formulas.</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-ink-300">{(ran[0]?.result?.limitations || []).map((l) => <li key={l}>{l}</li>)}</ul>
      <p className="mt-6 text-[11px] text-ink-500">Map data © OpenStreetMap contributors (ODbL). Population © WorldPop (CC BY 4.0).</p>
    </article>
  );
}
