"use client";

import { ExternalLink, Landmark, Route, Wallet } from "lucide-react";
import { Evidence, cn, statusToKind } from "@/components/ui";
import { money, pct } from "@/lib/format";
import type { IncomeEvidence, SimResult } from "@/lib/types";

/* Real-data panels: who lives here (income mix from official data) and where every model parameter came from. */

const CLASS_COLOR = ["#fb7185", "#fbbf24", "#C59BFF"];
const METHOD_LABEL: Record<IncomeEvidence["method"], string> = {
  rwi_rank: "Local wealth tiles (Meta RWI, 2.4 km) ranked on India's official consumption curve",
  state_curve: "State consumption curve (no local wealth tile here)",
  national_sector_curve: "All-India rural/urban curve (no state curve available)",
};

function rupees(x: number) {
  return "₹" + Math.round(x).toLocaleString("en-IN");
}

export function IncomeMix({ income, price, className }: { income: IncomeEvidence; price?: number; className?: string }) {
  const maxShare = Math.max(...income.histogram.map((h) => h.share), ...income.national_histogram.map((h) => h.share), 0.01);
  const ratio = income.median_mpce / income.india_median_mpce;
  return (
    <section className={cn("rounded-2xl border border-white/[0.07] bg-white/[0.025] p-3 text-xs", className)} aria-label="Who lives here">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <Wallet className="h-4 w-4 text-accent" />
          <div>
            <div className="font-medium text-ink-100">Who lives here — spending power</div>
            <div className="text-[10.5px] text-ink-400">Monthly spend per person, from official survey data</div>
          </div>
        </div>
        <Evidence kind="official" label="HCES 2023-24" />
      </div>

      <div className="mb-3 grid grid-cols-3 gap-2">
        <div className="rounded-xl bg-ink-900/70 p-2">
          <div className="text-[10px] text-ink-400">Median here</div>
          <div className="num text-sm font-semibold text-ink-100">{rupees(income.median_mpce)}</div>
        </div>
        <div className="rounded-xl bg-ink-900/70 p-2">
          <div className="text-[10px] text-ink-400">India median</div>
          <div className="num text-sm font-semibold text-ink-300">{rupees(income.india_median_mpce)}</div>
        </div>
        <div className="rounded-xl bg-ink-900/70 p-2">
          <div className="text-[10px] text-ink-400">vs India</div>
          <div className={cn("num text-sm font-semibold", ratio >= 1 ? "text-ok" : "text-warn")}>{ratio.toFixed(2)}×</div>
        </div>
      </div>

      {/* class mix: here vs India */}
      <div className="space-y-1.5">
        {income.classes.map((c, i) => (
          <div key={c.key}>
            <div className="flex items-baseline justify-between">
              <span className="flex items-center gap-1.5 text-ink-200">
                <span className="h-2 w-2 rounded-full" style={{ background: CLASS_COLOR[i] }} />
                {c.label}
                <span className="text-[10px] text-ink-500">{i === 2 ? `> ${rupees(c.mpce_range[0])}` : `${rupees(c.mpce_range[0])}–${rupees(c.mpce_range[1])}`}</span>
              </span>
              <span className="num font-semibold text-ink-100">{pct(c.share)}</span>
            </div>
            <div className="relative mt-0.5 h-1.5 rounded bg-ink-800">
              <div className="h-1.5 rounded" style={{ width: `${c.share * 100}%`, background: CLASS_COLOR[i] }} />
              <div className="absolute top-[-2px] h-[10px] w-[2px] rounded bg-ink-100/70" style={{ left: `${c.india_share * 100}%` }} title={`India: ${pct(c.india_share)}`} />
            </div>
          </div>
        ))}
        <div className="text-[10px] text-ink-500">White tick = India average share. Classes are India&apos;s bottom 40 %, middle 40 % and top 20 % by monthly spend.</div>
      </div>

      {/* distribution */}
      <div className="mt-3">
        <div className="mb-1 flex items-center justify-between text-[10px] text-ink-400">
          <span>Distribution of monthly spend per person</span>
          <span className="flex items-center gap-2"><span className="inline-block h-2 w-2 rounded-sm bg-accent" />here <span className="inline-block h-2 w-2 rounded-sm bg-ink-500" />India</span>
        </div>
        <div className="flex h-16 items-end gap-[3px]" role="img" aria-label="Spending distribution here versus India">
          {income.histogram.map((h, i) => {
            const n = income.national_histogram[i]?.share || 0;
            const isPrice = price !== undefined && price >= h.lo && (h.hi === null || price < h.hi);
            return (
              <div key={h.lo} className="relative flex h-full flex-1 items-end gap-[1px]" title={`${rupees(h.lo)}${h.hi ? "–" + rupees(h.hi) : "+"}: here ${pct(h.share)}, India ${pct(n)}`}>
                <div className="w-1/2 rounded-t-sm bg-accent/85" style={{ height: `${(h.share / maxShare) * 100}%` }} />
                <div className="w-1/2 rounded-t-sm bg-ink-500/70" style={{ height: `${(n / maxShare) * 100}%` }} />
                {isPrice && <div className="absolute -top-1 left-0 right-0 h-0.5 bg-danger" />}
              </div>
            );
          })}
        </div>
        <div className="mt-0.5 flex justify-between text-[9.5px] text-ink-500 num">
          <span>₹0</span><span>₹5k</span><span>₹15k+</span>
        </div>
      </div>

      <div className="mt-3 rounded-xl border border-white/[0.06] bg-ink-900/50 p-2 text-[10.5px] leading-relaxed text-ink-300">
        <span className="text-ink-100">How agents pay:</span> each synthetic person&apos;s willingness to pay = local price × (their spend ÷ {rupees(income.x_ref)})
        <sup>{income.elasticity.value}</sup>. Richer residents value you more, poorer ones less — in exactly this area&apos;s mix.
        WTP multipliers by class: {income.classes.map((c, i) => <span key={c.key} className="num" style={{ color: CLASS_COLOR[i] }}>{i ? " · " : " "}{c.wtp_multiplier.toFixed(2)}×</span>)}.
        {income.participation_lift !== 1 && <> Category participation here is <span className="num text-ink-100">{income.participation_lift.toFixed(2)}×</span> India&apos;s, from this income mix.</>}
      </div>

      <div className="mt-2 space-y-1">
        <div className="text-[10.5px] text-ink-400">{METHOD_LABEL[income.method]}{income.state ? ` · ${income.state}` : ""}</div>
        {income.provenance.map((s) => (
          <a key={s.source} href={s.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-[10.5px] text-ink-400 hover:text-accent">
            <ExternalLink className="h-3 w-3" /> {s.name}{s.license ? ` · ${s.license}` : ""}
          </a>
        ))}
        <div className="text-[10px] text-ink-500">
          Income elasticity {income.elasticity.value} ({income.elasticity.status}): {income.elasticity.source}. Curve fit error ≤ {pct(income.curve_fit_error, 1)}. Agents are synthetic — no real person&apos;s data is used.
        </div>
      </div>
    </section>
  );
}

const STATUS_ORDER = ["official", "industry", "literature", "derived", "user", "assumption"];
const STATUS_LABEL: Record<string, string> = {
  official: "Official statistic", industry: "Industry report", literature: "Published research", derived: "Derived from data",
  user: "Entered by you", assumption: "Assumption (varied in Monte Carlo)",
};

/** Where each model parameter came from: counts by status, routed distance share, and the evidence parameters with their sources. */
export function DataLineage({ res, className }: { res: SimResult; className?: string }) {
  const status = res.parameter_status || {};
  const counts: Record<string, number> = {};
  Object.values(status).forEach((s) => {
    const k = STATUS_ORDER.includes(s) ? s : s?.startsWith("derived") ? "derived" : "assumption";
    counts[k] = (counts[k] || 0) + 1;
  });
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  const sources = res.parameter_sources || {};
  const g = res.abm?.genome;
  return (
    <section className={cn("rounded-2xl border border-white/[0.07] bg-white/[0.025] p-3 text-xs", className)} aria-label="Data lineage">
      <div className="mb-2 flex items-center gap-2">
        <Landmark className="h-4 w-4 text-model" />
        <div className="font-medium text-ink-100">Data lineage — what is real, what is assumed</div>
      </div>
      <div className="mb-2 flex h-2 overflow-hidden rounded-full bg-ink-800">
        {STATUS_ORDER.filter((k) => counts[k]).map((k) => (
          <div key={k} title={`${STATUS_LABEL[k]}: ${counts[k]}`} style={{ width: `${(counts[k] / total) * 100}%` }}
            className={{ official: "bg-ok", industry: "bg-observed", literature: "bg-userdata", derived: "bg-model/70", user: "bg-accent", assumption: "bg-assumption/60" }[k]} />
        ))}
      </div>
      <div className="mb-2 grid grid-cols-2 gap-x-3 gap-y-0.5">
        {STATUS_ORDER.filter((k) => counts[k]).map((k) => (
          <div key={k} className="flex justify-between"><span className="text-ink-400">{STATUS_LABEL[k]}</span><span className="num text-ink-200">{counts[k]}</span></div>
        ))}
      </div>
      {Object.keys(sources).length > 0 && (
        <div className="space-y-1.5 border-t border-white/[0.06] pt-2">
          {Object.entries(sources).map(([k, src]) => (
            <div key={k}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-ink-200">{res.parameters?.[k]?.label || k.replace(/_/g, " ")}</span>
                <span className="flex items-center gap-1.5">
                  <span className="num text-ink-100">{fmtParam(k, res.parameters?.[k]?.value)}</span>
                  <Evidence kind={statusToKind(status[k])} label={status[k]} />
                </span>
              </div>
              <div className="text-[10px] leading-snug text-ink-500">{src}</div>
            </div>
          ))}
        </div>
      )}
      {res.routing && (
        <div className="mt-2 flex items-start gap-1.5 border-t border-white/[0.06] pt-2 text-[10.5px] text-ink-300">
          <Route className="mt-0.5 h-3.5 w-3.5 shrink-0 text-observed" />
          <span>
            {res.routing.share_routed > 0 ? <><span className="num text-ink-100">{pct(res.routing.share_routed)}</span> of home→business distances are real road routes (OSRM on OpenStreetMap roads, walking and driving). </> : null}
            {res.routing.note}.
          </span>
        </div>
      )}
      {g && (
        <div className="mt-2 border-t border-white/[0.06] pt-2 text-[10.5px] text-ink-400">
          Each agent carries {g.per_agent} parameters. Placement, age–sex, travel distance and spending power come from data; behavioural traits are generated from documented, correlated assumptions and are labelled as such in every agent&apos;s X-ray.
        </div>
      )}
    </section>
  );
}

function fmtParam(k: string, v: number | undefined) {
  if (v === undefined || v === null) return "—";
  if (k === "participation") return pct(v, 2);
  if (k === "frequency") return `${v.toFixed(1)}/mo`;
  if (k.includes("price") && v > 50) return money(v);
  return v.toFixed(2);
}
