"use client";

/**
 * Strategy optimizer: every combination of price, marketing and capacity through the choice model (with capacity
 * costs), shown as an interactive profit map. Pick a cell to see its numbers; verify any of them with the
 * 10,000-agent simulation on the map.
 */
import { Star, Target, Wand2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Changes } from "@/components/StrategyLab";
import { Button, cn, Notice } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money, num, pct } from "@/lib/format";

interface Combo {
  price: number;
  marketing_spend: number;
  capacity_scale: number;
  demand: number;
  units: number;
  capacity: number;
  profit: number;
  revenue: number;
  payback_months: number | null;
  risk?: { prob_loss: number; profit_p10: number; profit_p90: number };
}

interface OptOut {
  current: Combo;
  best: Combo;
  best_without_new_capacity: Combo;
  surface: { price: number; marketing_spend: number; profit: number; units: number }[];
  prices: number[];
  spends: number[];
  evaluated: number;
  cost_note: string;
  unit: string;
  price_label: string;
}

function changesFor(c: { price: number; marketing_spend: number; capacity_scale?: number }, cur: Combo): Changes {
  const ch: Changes = {};
  if (c.price !== cur.price) ch.price = c.price;
  if (c.marketing_spend !== cur.marketing_spend) ch.marketing_spend = c.marketing_spend;
  if (c.capacity_scale && c.capacity_scale !== 1) ch.capacity_scale = c.capacity_scale;
  return ch;
}

export function BestStrategy({ projectId, scenarioId, busy, onVerify, autoKey }: { projectId: string; scenarioId: string; busy: boolean; onVerify: (c: Changes) => void; autoKey?: number }) {
  const [data, setData] = useState<OptOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pick, setPick] = useState<{ price: number; marketing_spend: number } | null>(null);

  async function run() {
    setLoading(true);
    setErr(null);
    try {
      const d = await api<OptOut>(`/projects/${projectId}/optimize?scenario_id=${scenarioId}`);
      setData(d);
      setPick({ price: d.best.price, marketing_spend: d.best.marketing_spend });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Optimizer failed");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    setData(null);
    setPick(null);
  }, [scenarioId]);
  useEffect(() => {
    if (autoKey) void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoKey]);

  const grid = useMemo(() => {
    if (!data) return null;
    const by = new Map(data.surface.map((s) => [`${s.price}|${s.marketing_spend}`, s]));
    const vals = data.surface.map((s) => s.profit);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    return { by, lo, hi };
  }, [data]);

  if (!data) {
    return (
      <div className="rounded-2xl border border-userdata/40 bg-userdata/[0.05] p-3 text-xs">
        <div className="mb-1 flex items-center gap-1.5 font-medium text-ink-100"><Wand2 className="h-3.5 w-3.5 text-userdata" /> Find my best strategy</div>
        <p className="mb-2 leading-relaxed text-ink-400">Tests hundreds of combinations of price, marketing and capacity (extra staff and rent included) and shows where profit peaks.</p>
        {err && <Notice tone="warn">{err}</Notice>}
        <Button size="sm" className="w-full" loading={loading} onClick={run}><Target className="h-3.5 w-3.5" /> {loading ? "Searching…" : "Find the best combination"}</Button>
      </div>
    );
  }
  const { current: cur, best } = data;
  const sel = pick && grid ? grid.by.get(`${pick.price}|${pick.marketing_spend}`) : null;
  const color = (p: number) => {
    if (!grid) return "transparent";
    if (p < 0) return `rgba(255,106,106,${0.18 + 0.5 * Math.min(1, -p / Math.max(1, -grid.lo))})`;
    const t = grid.hi > 0 ? p / grid.hi : 0;
    return `rgba(69,224,168,${0.08 + 0.72 * t})`;
  };
  const spendsDesc = [...data.spends].sort((a, b) => b - a);
  const gain = best.profit - cur.profit;
  return (
    <div className="rounded-2xl border border-userdata/40 bg-userdata/[0.05] p-3 text-xs">
      <div className="mb-1 flex items-center gap-1.5 font-medium text-ink-100"><Wand2 className="h-3.5 w-3.5 text-userdata" /> Best strategy found</div>
      <p className="leading-relaxed text-ink-300">
        {gain > 0 ? (
          <>Tested {num(data.evaluated)} options. Best: <b>{money(best.price)}</b>, <b>{money(best.marketing_spend)}</b>/mo marketing{best.capacity_scale !== 1 ? <>, capacity <b>×{best.capacity_scale}</b></> : null} →{" "}
            <b className="text-model">{money(best.profit, { compact: true })}/mo</b> vs {money(cur.profit, { compact: true })} now
            {best.risk && cur.risk ? <> · loss chance {pct(cur.risk.prob_loss)} → {pct(best.risk.prob_loss)}</> : null}.</>
        ) : <>Your current plan is already the most profitable of {num(data.evaluated)} options tested.</>}
      </p>
      {grid && (
        <div className="mt-2">
          <div className="mb-1 flex justify-between text-[10px] text-ink-500"><span>Monthly profit by price (→) and marketing (↓){best.capacity_scale !== 1 ? ` at capacity ×${best.capacity_scale}` : ""}</span></div>
          <div className="grid gap-px" style={{ gridTemplateColumns: `52px repeat(${data.prices.length}, minmax(0,1fr))` }}>
            {spendsDesc.map((sp) => (
              <div key={sp} className="contents">
                <div className="num truncate pr-1 text-right text-[9.5px] leading-5 text-ink-500">{money(sp, { compact: true })}</div>
                {data.prices.map((pr) => {
                  const c = grid.by.get(`${pr}|${sp}`);
                  const isBest = pr === best.price && sp === best.marketing_spend;
                  const isCur = pr === cur.price && sp === cur.marketing_spend;
                  const isSel = pick?.price === pr && pick?.marketing_spend === sp;
                  return (
                    <button key={pr} onClick={() => setPick({ price: pr, marketing_spend: sp })} title={c ? `${money(pr)} · ${money(sp)} ads → ${money(c.profit, { compact: true })}/mo` : ""}
                      className={cn("relative h-5 rounded-[3px] outline-none transition-transform hover:scale-110", isSel && "ring-1 ring-ink-100", isCur && "ring-1 ring-accent")}
                      style={{ background: c ? color(c.profit) : "transparent" }}>
                      {isBest && <Star className="absolute inset-0 m-auto h-3 w-3 fill-ink-100 text-ink-100" />}
                    </button>
                  );
                })}
              </div>
            ))}
            <div />
            {data.prices.map((pr) => <div key={pr} className="num truncate pt-0.5 text-center text-[9px] text-ink-500">{pr}</div>)}
          </div>
          <div className="mt-1 flex gap-3 text-[10px] text-ink-500"><span className="flex items-center gap-1"><Star className="h-2.5 w-2.5 fill-ink-100" /> best</span><span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm ring-1 ring-accent" /> your plan now</span><span>red = loss</span></div>
        </div>
      )}
      {sel && pick && (
        <div className="mt-2 rounded-xl border border-white/[0.07] bg-ink-900/60 p-2">
          <div className="text-ink-300">{money(pick.price)} · {money(pick.marketing_spend)}/mo ads{best.capacity_scale !== 1 ? ` · capacity ×${best.capacity_scale}` : ""}</div>
          <div className="num mt-0.5 text-ink-100">{num(sel.units)} {data.unit}/mo · profit <b className={sel.profit >= 0 ? "text-model" : "text-danger"}>{money(sel.profit, { compact: true })}</b></div>
          <Button size="sm" variant="primary" className="mt-2 w-full" loading={busy} onClick={() => onVerify(changesFor({ ...pick, capacity_scale: best.capacity_scale }, cur))}
            disabled={!Object.keys(changesFor({ ...pick, capacity_scale: best.capacity_scale }, cur)).length}>
            Verify with 10,000 agents on the map
          </Button>
        </div>
      )}
      {data.best_without_new_capacity.profit > cur.profit && best.capacity_scale !== 1 && (
        <button className="mt-2 w-full text-left text-[11px] text-ink-400 hover:text-ink-100" onClick={() => onVerify(changesFor(data.best_without_new_capacity, cur))}>
          No money to expand? Best without new capacity: {money(data.best_without_new_capacity.price)}, {money(data.best_without_new_capacity.marketing_spend)} ads → {money(data.best_without_new_capacity.profit, { compact: true })}/mo. <span className="text-userdata">Verify →</span>
        </button>
      )}
      <p className="mt-2 text-[10px] leading-snug text-ink-500">{data.cost_note}</p>
    </div>
  );
}
