"use client";

/**
 * Strategy lab for the live market: change a lever, the same 10,000 agents re-decide, the map replays,
 * and the result is compared with the run you started from. Also: Strata's read of the run (insights with a
 * one-click test) and a plain-language "how an agent decides" card filled with this run's numbers.
 */
import { ArrowDownRight, ArrowUpRight, Brain, ChevronDown, FlaskConical, Lightbulb, Minus, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import type { Abm, Archetype, Scenario } from "@/lib/types";
import { Button, cn, Segmented, Select } from "@/components/ui";

export interface RunView {
  price: number | null;
  month3_units: number | null;
  month3_profit: number | null;
  agent_month_units: number[];
  agent_month_profit: number[];
  orders_per_day_last4w: number;
  demand_per_day_last4w: number | null;
  turned_away_per_day_last4w: number;
  capacity_per_day: number | null;
  awareness_week12: number | null;
  trial_rate: number | null;
  repeat_share: number | null;
  customers_total: number | null;
  afford_share: number | null;
  daily_units: number[];
  static_profit_per_month: number | null;
  probability_of_loss: number | null;
}

export interface StrategyOut {
  scenario: { id: string; name: string };
  from: { id: string; name: string; run_id: string };
  run_id: string;
  before: RunView;
  after: RunView;
  comparison: { delta_units_month3: number | null; delta_profit_month3: number | null; grows: boolean; verdict: string; spoken: string };
  spoken: string;
}

export interface Insight {
  key: string;
  title: string;
  detail: string;
  action: { label: string; changes: Record<string, number> } | null;
}

export type Changes = Partial<Record<"price" | "marketing_spend" | "quality" | "capacity_scale" | "open_hour" | "close_hour", number>>;

export async function runStrategy(projectId: string, fromScenarioId: string, changes: Changes): Promise<StrategyOut> {
  return api<StrategyOut>(`/projects/${projectId}/strategy`, { method: "POST", json: { ...changes, from_scenario_id: fromScenarioId } });
}

const HOURS = Array.from({ length: 25 }, (_, h) => h);
const hh = (h: number) => (h === 0 || h === 24 ? "12 am" : h < 12 ? `${h} am` : h === 12 ? "12 pm" : `${h - 12} pm`);

export function StrategyLab({ projectId, scenario, arch, unit, busy, onRun }: {
  projectId: string;
  scenario: Scenario;
  arch: Archetype;
  unit: string;
  busy: boolean;
  onRun: (changes: Changes) => void;
}) {
  const inp = scenario.inputs;
  const [price, setPrice] = useState(inp.price);
  const [mkt, setMkt] = useState(inp.marketing_spend || 0);
  const [quality, setQuality] = useState(Math.round((inp.quality ?? 0.55) * 100));
  const [cap, setCap] = useState("1");
  const [open, setOpen] = useState<number | "">(inp.offer?.open_hour ?? "");
  const [close, setClose] = useState<number | "">(inp.offer?.close_hour ?? "");
  useEffect(() => {
    setPrice(inp.price);
    setMkt(inp.marketing_spend || 0);
    setQuality(Math.round((inp.quality ?? 0.55) * 100));
    setCap("1");
    setOpen(inp.offer?.open_hour ?? "");
    setClose(inp.offer?.close_hour ?? "");
  }, [scenario.id, inp]);

  const changes: Changes = {};
  if (Math.abs(price - inp.price) > 0.5) changes.price = price;
  if (Math.abs(mkt - (inp.marketing_spend || 0)) > 1) changes.marketing_spend = mkt;
  if (quality !== Math.round((inp.quality ?? 0.55) * 100)) changes.quality = quality / 100;
  if (cap !== "1") changes.capacity_scale = Number(cap);
  if (open !== "" && open !== (inp.offer?.open_hour ?? "")) changes.open_hour = Number(open);
  if (close !== "" && close !== (inp.offer?.close_hour ?? "")) changes.close_hour = Number(close);
  const n = Object.keys(changes).length;
  const pMax = Math.max(inp.price * 2, 100);
  const mMax = Math.max(200000, (inp.marketing_spend || 0) * 4);
  void projectId;

  return (
    <div className="rounded-2xl border border-accent/30 bg-accent/[0.04] p-3 text-xs">
      <div className="mb-2 flex items-center gap-2">
        <FlaskConical className="h-3.5 w-3.5 text-accent" />
        <span className="font-medium text-ink-100">Change your strategy</span>
        <span className="ml-auto text-[10px] text-ink-400">from: {scenario.name}</span>
      </div>
      <Row label={arch.price_label} value={money(price)} changed={changes.price !== undefined}>
        <input type="range" min={Math.round(inp.price * 0.4)} max={Math.round(pMax)} step={Math.max(1, Math.round(inp.price / 100))} value={price} onChange={(e) => setPrice(Number(e.target.value))} className="w-full" aria-label="Price" />
      </Row>
      <Row label="Marketing / month" value={money(mkt)} changed={changes.marketing_spend !== undefined}>
        <input type="range" min={0} max={mMax} step={1000} value={mkt} onChange={(e) => setMkt(Number(e.target.value))} className="w-full" aria-label="Marketing spend per month" />
      </Row>
      <Row label="Quality (vs local average)" value={`${quality}/100`} changed={changes.quality !== undefined}>
        <input type="range" min={10} max={100} step={1} value={quality} onChange={(e) => setQuality(Number(e.target.value))} className="w-full" aria-label="Quality" />
      </Row>
      <Row label="Capacity" value={cap === "1" ? "as now" : `×${cap}`} changed={changes.capacity_scale !== undefined}>
        <Segmented value={cap} onChange={setCap} options={[{ value: "1", label: "Now" }, { value: "1.25", label: "+25%" }, { value: "1.5", label: "+50%" }, { value: "2", label: "×2" }]} />
      </Row>
      <Row label="Opening hours" value={open === "" && close === "" ? "default" : `${open === "" ? "…" : hh(Number(open))} – ${close === "" ? "…" : hh(Number(close))}`} changed={changes.open_hour !== undefined || changes.close_hour !== undefined}>
        <div className="flex gap-2">
          <Select aria-label="Opening time" className="h-8 text-xs" value={open} onChange={(e) => setOpen(e.target.value === "" ? "" : Number(e.target.value))}>
            <option value="">Open (default)</option>
            {HOURS.slice(0, 24).map((h) => <option key={h} value={h}>{hh(h)}</option>)}
          </Select>
          <Select aria-label="Closing time" className="h-8 text-xs" value={close} onChange={(e) => setClose(e.target.value === "" ? "" : Number(e.target.value))}>
            <option value="">Close (default)</option>
            {HOURS.slice(1).map((h) => <option key={h} value={h}>{hh(h)}</option>)}
          </Select>
        </div>
      </Row>
      <Button variant="primary" size="sm" className="mt-2 w-full" disabled={!n} loading={busy} onClick={() => onRun(changes)}>
        {busy ? "10,000 agents are re-deciding…" : n ? `Run ${n} change${n > 1 ? "s" : ""} on the map` : "Move a slider to test a strategy"}
      </Button>
      <p className="mt-1.5 text-[10px] text-ink-500">Same people, same seed — only your {unit === "orders" ? "offer" : "strategy"} changes, so any difference comes from the change itself.</p>
    </div>
  );
}

function Row({ label, value, changed, children }: { label: string; value: string; changed: boolean; children: React.ReactNode }) {
  return (
    <div className="mb-2">
      <div className="mb-1 flex justify-between">
        <span className="text-ink-300">{label}</span>
        <span className={cn("num font-medium", changed ? "text-accent" : "text-ink-200")}>{value}</span>
      </div>
      {children}
    </div>
  );
}

export function CompareCard({ out, unit }: { out: StrategyOut; unit: string }) {
  const { before: b, after: a, comparison: c } = out;
  const rows: [string, number | null, number | null, (x: number | null) => string, boolean][] = [
    [`Month 3 ${unit}`, b.month3_units, a.month3_units, (x) => num(x), true],
    ["Month 3 profit", b.month3_profit, a.month3_profit, (x) => money(x, { compact: true }), true],
    ["Awareness wk 12", b.awareness_week12, a.awareness_week12, (x) => pct(x), true],
    ["Customers (12 wk)", b.customers_total, a.customers_total, (x) => num(x), true],
    [`Turned away / day`, b.turned_away_per_day_last4w, a.turned_away_per_day_last4w, (x) => num(x), false],
  ];
  const good = c.verdict === "better";
  return (
    <div className={cn("rounded-2xl border p-3 text-xs", good ? "border-model/40 bg-model/[0.06]" : "border-danger/40 bg-danger/[0.06]")}>
      <div className="mb-1 flex items-center gap-2">
        {good ? <ArrowUpRight className="h-4 w-4 text-model" /> : <ArrowDownRight className="h-4 w-4 text-danger" />}
        <span className="font-medium text-ink-100">{c.grows && good ? "Growing — this strategy works" : good ? "More profit, similar volume" : c.grows ? "More sales, less profit" : "Not better"}</span>
      </div>
      <div className="mb-2 text-[10.5px] text-ink-400">{out.scenario.name.replace("Strategy: ", "")} vs {out.from.name}</div>
      <table className="w-full">
        <thead><tr className="text-[10px] text-ink-500"><th className="text-left font-normal" /><th className="text-right font-normal">Before</th><th className="text-right font-normal">After</th><th className="text-right font-normal">Change</th></tr></thead>
        <tbody>
          {rows.map(([l, x, y, f, upGood]) => {
            const d = x === null || y === null ? null : y - x;
            const up = (d ?? 0) > 0;
            const tone = d === null || Math.abs(d) < 1e-9 ? "text-ink-400" : up === upGood ? "text-model" : "text-danger";
            return (
              <tr key={l} className="border-t border-white/[0.05]">
                <td className="py-1 text-ink-300">{l}</td>
                <td className="num py-1 text-right text-ink-400">{f(x)}</td>
                <td className="num py-1 text-right text-ink-100">{f(y)}</td>
                <td className={cn("num py-1 text-right", tone)}>{d === null ? "—" : Math.abs(d) < 1e-9 ? <Minus className="ml-auto h-3 w-3" /> : (up ? "+" : "−") + f(Math.abs(d)).replace("−", "")}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-300">{c.spoken}</p>
    </div>
  );
}

export function StrataRead({ projectId, scenarioId, runId, busy, onTest }: { projectId: string; scenarioId: string; runId: string | null; busy: boolean; onTest: (c: Changes) => void }) {
  const [items, setItems] = useState<Insight[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!runId) return;
    let live = true;
    setItems(null);
    setErr(null);
    api<{ insights: Insight[] }>(`/projects/${projectId}/insights?scenario_id=${scenarioId}`)
      .then((r) => live && setItems(r.insights))
      .catch((e) => live && setErr(e instanceof ApiError ? e.message : "Could not read this run"));
    return () => {
      live = false;
    };
  }, [projectId, scenarioId, runId]);
  if (!runId) return null;
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-3 text-xs">
      <div className="mb-2 flex items-center gap-2"><Lightbulb className="h-3.5 w-3.5 text-warn" /><span className="font-medium text-ink-100">Strata&apos;s read of this run</span></div>
      {err && <p className="text-ink-400">{err}</p>}
      {!items && !err && <p className="text-ink-500">Reading the simulation…</p>}
      <div className="space-y-2.5">
        {items?.slice(0, 5).map((i) => (
          <div key={i.key}>
            <div className="font-medium text-ink-200">{i.title}</div>
            <p className="mt-0.5 leading-relaxed text-ink-400">{i.detail}</p>
            {i.action && (
              <button disabled={busy} onClick={() => onTest(i.action!.changes as Changes)} className="mt-1 inline-flex items-center gap-1 rounded-full border border-accent/40 px-2.5 py-0.5 text-[11px] text-accent hover:bg-accent/10 disabled:opacity-50">
                <Sparkles className="h-3 w-3" /> {i.action.label}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function HowAgentsDecide({ abm, price }: { abm: Abm; price: number | undefined }) {
  const [open, setOpen] = useState(false);
  const m = abm.metrics;
  const steps = useMemo(
    () => [
      ["Placed where people really live", `${num(abm.n_agents)} agents spread by WorldPop density; each stands for about ${num(abm.scale)} residents. Age and sex follow the local census grid.`],
      ["615 personal parameters", "Income, budget and willingness to pay, travel mode and speed, free hours for every hour of the week, 40 things they care about and the minimum they accept on each, reaction to 16 media channels, habits, loyalty, household."],
      ["Must need it and know you", `Only people in the market today (${num(abm.in_market_agents)} agents) decide. They learn about you through ads, word of mouth from neighbours who bought, or your signboard — ${pct(m.aware_final)} knew you by week 12.`],
      ["Scores every option it can reach", `You, each competitor, or buying nothing. Price vs its own budget (${pct(m.afford_share)} can afford ${price ? money(price) : "you"}), travel time, opening hours, quality, its 40 tastes, minus disappointment where you fall below its minimums, plus a little personal randomness.`],
      ["Picks the best, and remembers", `Habits build with each visit (${pct(m.repeat_share)} of your customers came back); being turned away when you're full is remembered and pushes them to a rival.`],
      ["Counted in real units", "Daily orders = every agent's chance of choosing you × how often it buys × residents it stands for, then real-day randomness and your capacity. The dots are individual decisions."],
    ],
    [abm, m, price],
  );
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-3 text-xs">
      <button onClick={() => setOpen((x) => !x)} className="flex w-full items-center gap-2 text-left">
        <Brain className="h-3.5 w-3.5 text-agent" />
        <span className="font-medium text-ink-100">How an agent decides</span>
        <ChevronDown className={cn("ml-auto h-3.5 w-3.5 text-ink-400 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ol className="mt-2 space-y-2">
          {steps.map(([t, d], i) => (
            <li key={t} className="flex gap-2">
              <span className="num mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-agent/20 text-[9px] text-agent">{i + 1}</span>
              <span><span className="font-medium text-ink-200">{t}.</span> <span className="text-ink-400">{d}</span></span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
