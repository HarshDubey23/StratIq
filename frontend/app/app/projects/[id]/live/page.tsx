"use client";

import { Activity, Dna, Pause, Play, RotateCcw, Users } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import AgentXray from "@/components/AgentXray";
import { useProject } from "@/components/ProjectContext";
import { Badge, Button, EmptyState, ErrorState, Evidence, Notice, Segmented, Select, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import type { MarketData, Run, SimResult } from "@/lib/types";

const LiveMap = dynamic(() => import("@/components/LiveMap"), { ssr: false, loading: () => <div className="absolute inset-0 flex items-center justify-center bg-ink-950 text-sm text-ink-400">Loading live market…</div> });

const MODE_LABEL: Record<string, string> = { walk: "Walk", two_wheeler: "Two-wheeler", car: "Car", auto: "Auto", bus: "Bus", metro: "Metro / rail", cycle: "Cycle" };
const TT = { contentStyle: { background: "#131a24", border: "1px solid #263243", borderRadius: 6, fontSize: 12 } };

export default function LiveMarket() {
  const { project: p, reload } = useProject();
  const scenarios = useMemo(() => p.scenarios || [], [p.scenarios]);
  const [sid, setSid] = useState(scenarios.find((s) => s.is_baseline)?.id || scenarios[0]?.id);
  const sc = scenarios.find((s) => s.id === sid);
  const [res, setRes] = useState<SimResult | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [market, setMarket] = useState<MarketData | null>(null);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [agent, setAgent] = useState<number | null>(null);
  const [heat, setHeat] = useState(true);
  const [trails, setTrails] = useState(true);
  const [colorMode, setColorMode] = useState<"choice" | "segment" | "mode" | "age">("choice");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!sc) return;
    setLoading(true);
    setError(null);
    try {
      const [m, r] = await Promise.all([
        api<MarketData>(`/projects/${p.id}/market?location_id=${sc.location_id}`),
        sc.latest_run ? api<Run>(`/simulation-runs/${sc.latest_run.id}/results`) : Promise.resolve(null),
      ]);
      setMarket(m);
      setRes(r?.results || null);
      setRunId(r?.id || null);
      setFrame(0);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load");
    } finally {
      setLoading(false);
    }
  }, [p.id, sc]);
  useEffect(() => {
    load();
  }, [load]);

  async function run() {
    if (!sc) return;
    setRunning(true);
    setError(null);
    try {
      const r = await api<Run>(`/scenarios/${sc.id}/runs`, { method: "POST" });
      setRes(r.results || null);
      setRunId(r.id);
      setAgent(null);
      setFrame(0);
      setPlaying(true);
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Simulation failed");
    } finally {
      setRunning(false);
    }
  }

  const abm = res?.abm;
  const day = abm ? abm.frames[frame]?.day ?? 0 : 0;
  const unit = res?.unit_label || "units";
  const membership = res?.archetype === "membership";
  const dailyChart = useMemo(
    () => (abm ? abm.daily.units_you.map((u, d) => ({ d: d + 1, you: u, aware: Math.round(abm.daily.aware_share[d] * 100), cust: abm.daily.customers_you[d] })) : []),
    [abm],
  );

  if (!sc) return <div className="p-6"><EmptyState title="No scenario" /></div>;

  return (
    <div className="relative flex min-h-0 flex-1 flex-col lg:flex-row">
      <section className="relative h-[70vh] flex-1 lg:h-auto lg:min-h-[calc(100vh-112px)]">
        {abm && market?.snapshot ? (
          <LiveMap
            center={[market.location.lng, market.location.lat]}
            catchment={market.snapshot.catchment_geojson}
            zones={market.snapshot.zones}
            abm={abm}
            frameIdx={frame}
            playing={playing}
            speed={speed}
            onFrame={setFrame}
            onAgent={(i) => setAgent(i)}
            selectedAgent={agent}
            showHeat={heat}
            showTrails={trails}
            colorMode={colorMode}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center bg-ink-950 p-6">
            {loading ? (
              <Spinner label="Loading…" />
            ) : !market?.snapshot ? (
              <EmptyState title="No market data for this location" body="Load live market evidence first." action={<Link className="text-accent underline" href={`/app/projects/${p.id}/market`}>Open market map</Link>} />
            ) : (
              <EmptyState
                icon={<Users className="h-6 w-6" />}
                title="Run the live market"
                body="10,000 synthetic people are placed by real population density, each carrying a 615-parameter genome, and the market is simulated day by day."
                action={<Button variant="primary" onClick={run} loading={running}><Play className="h-4 w-4" /> Simulate 12 weeks</Button>}
              />
            )}
          </div>
        )}

        {abm && (
          <>
            {/* top HUD */}
            <div className="pointer-events-none absolute left-3 right-14 top-3 z-10 flex flex-wrap items-start gap-2">
              <div className="pointer-events-auto rounded-lg border border-ink-700 bg-ink-950/90 px-4 py-2.5 backdrop-blur">
                <div className="flex items-center gap-2 text-[11px] uppercase tracking-widest text-ink-400"><Activity className="h-3 w-3 text-accent" /> Live market simulation</div>
                <div className="num mt-0.5 text-2xl font-semibold text-ink-100">Day {day + 1}<span className="ml-2 text-sm text-ink-400">week {Math.floor(day / 7) + 1} of {Math.ceil(abm.days / 7)}</span></div>
              </div>
              {[
                [membership ? "Your members" : `Your ${unit} today`, num(membership ? abm.daily.units_you[day] : abm.daily.units_you[day])],
                ["Customers so far", num(abm.daily.customers_you[day])],
                ["Aware of you", pct(abm.daily.aware_share[day])],
                [membership ? "Competitor members" : "Competitor sales today", num(abm.daily.units_comp[day])],
              ].map(([l, v]) => (
                <div key={l} className="pointer-events-auto rounded-lg border border-ink-700 bg-ink-950/90 px-3 py-2 backdrop-blur">
                  <div className="text-[10px] uppercase tracking-wide text-ink-400">{l}</div>
                  <div className="num text-lg font-semibold text-ink-100">{v}</div>
                </div>
              ))}
              {abm.genome && (
                <Link href={`/app/projects/${p.id}/genome`} className="pointer-events-auto rounded-lg border border-agent/40 bg-ink-950/90 px-3 py-2 backdrop-blur hover:border-agent">
                  <div className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-agent"><Dna className="h-3 w-3" /> Agent genome</div>
                  <div className="num text-lg font-semibold text-ink-100">{num(abm.n_agents)} × {abm.genome.per_agent}<span className="ml-1.5 text-xs font-normal text-ink-400">= {num(abm.genome.total_parameters)} params</span></div>
                </Link>
              )}
            </div>
            {agent !== null && runId && abm.genome && (
              <AgentXray runId={runId} agent={agent} price={res?.summary.price} onClose={() => setAgent(null)} className="absolute bottom-24 right-14 top-24 z-20 w-[min(560px,calc(100%-5rem))]" />
            )}
            {agent !== null && abm && !abm.genome && (
              <div className="absolute right-14 top-24 z-20 max-w-sm"><Notice tone="warn">This run was made before the Agent Genome. Re-run to X-ray agents.</Notice></div>
            )}

            {/* controls */}
            <div className="absolute bottom-6 left-3 right-14 z-10 flex flex-wrap items-center gap-2 rounded-lg border border-ink-700 bg-ink-950/90 p-2 backdrop-blur">
              <Button size="sm" variant="primary" onClick={() => setPlaying((x) => !x)} aria-label={playing ? "Pause" : "Play"}>
                {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
              </Button>
              <Button size="sm" onClick={() => setFrame(0)} aria-label="Restart"><RotateCcw className="h-3.5 w-3.5" /></Button>
              <input
                type="range"
                min={0}
                max={abm.frames.length - 1}
                value={frame}
                onChange={(e) => setFrame(Number(e.target.value))}
                className="min-w-40 flex-1"
                aria-label="Simulation day"
              />
              <Segmented value={String(speed)} onChange={(v) => setSpeed(Number(v))} options={[{ value: "0.5", label: "½×" }, { value: "1", label: "1×" }, { value: "2", label: "2×" }, { value: "4", label: "4×" }]} />
              <Select value={colorMode} onChange={(e) => setColorMode(e.target.value as typeof colorMode)} className="h-8 w-auto text-xs" aria-label="Colour agents by">
                <option value="choice">Colour: customer status</option>
                <option value="segment">Colour: income segment</option>
                <option value="mode">Colour: travel mode</option>
                <option value="age">Colour: age group</option>
              </Select>
              <label className="flex items-center gap-1.5 text-xs text-ink-300"><input type="checkbox" checked={heat} onChange={(e) => setHeat(e.target.checked)} /> Density</label>
              <label className="flex items-center gap-1.5 text-xs text-ink-300"><input type="checkbox" checked={trails} onChange={(e) => setTrails(e.target.checked)} /> Trips</label>
            </div>

            {/* legend */}
            <div className="absolute bottom-24 left-3 z-10 max-w-xs rounded-lg border border-ink-700 bg-ink-950/90 p-3 text-[11px] text-ink-300 backdrop-blur">
              {colorMode === "choice" && (
                <div className="space-y-1">
                  <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-agent" /> In-market person (not yet your customer)</div>
                  <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-accent" /> Your customer</div>
                  <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-red-950" /> Not in this market</div>
                  <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-amber-300" /> Travelling to a competitor</div>
                </div>
              )}
              {colorMode === "segment" && abm.agents.segments.map((s, i) => <div key={s} className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: ["#fb7185", "#fbbf24", "#a78bfa"][i] }} /> {s}</div>)}
              {colorMode === "mode" && abm.agents.modes.map((s, i) => <div key={s} className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: ["#4ade80", "#38bdf8", "#f472b6", "#facc15", "#fb923c", "#c084fc", "#a3e635"][i] }} /> {MODE_LABEL[s] || s}</div>)}
              {colorMode === "age" && [["#93c5fd", "0–14"], ["#22d3ee", "15–29"], ["#fbbf24", "30–49"], ["#f87171", "50+"]].map(([c, l]) => <div key={l} className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: c }} /> {l}</div>)}
              <div className="mt-1.5 border-t border-ink-700 pt-1.5 text-ink-500">
                {num(abm.n_agents)} synthetic agents · each ≈ {num(abm.scale)} residents · {abm.genome ? `${abm.genome.per_agent} parameters each` : "profile per agent"}. Placed by {market?.snapshot?.population.source === "worldpop" ? "WorldPop" : "estimated"} density. Click any dot to X-ray its decision.
              </div>
            </div>
          </>
        )}
      </section>

      {/* right panel */}
      <aside className="w-full space-y-4 overflow-y-auto border-l border-ink-800 bg-ink-950 p-4 lg:max-h-[calc(100vh-112px)] lg:w-[380px]">
        <div className="flex items-center gap-2">
          <Select value={sid} onChange={(e) => { setSid(e.target.value); setAgent(null); }} aria-label="Scenario">
            {scenarios.map((s) => <option key={s.id} value={s.id}>{s.name}{s.is_baseline ? " (baseline)" : ""}</option>)}
          </Select>
          <Button size="sm" onClick={run} loading={running}>Re-run</Button>
        </div>
        {error && <ErrorState message={error} />}
        {sc.latest_run?.stale && <Notice tone="warn">Inputs changed since this run. Re-run to update the live market.</Notice>}
        {res?.evidence?.failed_layers?.includes("competitors") && (res?.competitors?.length || 0) === 0 && (
          <Notice tone="warn">Competitor data failed to load for this location, so this run has no competitors and is optimistic. Refresh live data on the Market map, then re-run.</Notice>
        )}

        {abm && res && (
          <>
            <div className="grid grid-cols-2 gap-2 text-xs">
              {[
                ["Month 3 " + unit, num(abm.monthly_units[abm.monthly_units.length - 1])],
                ["Static model " + unit, num(res.summary.units_sold)],
                ["Awareness (wk 12)", pct(abm.metrics.aware_final)],
                ["Trial rate", pct(abm.metrics.trial_rate)],
                ["Repeat share", pct(abm.metrics.repeat_share)],
                ["Mean trip", `${num(abm.metrics.mean_trip_km, 2)} km`],
                ["Can afford you", pct(abm.metrics.afford_share)],
                ["Ramp-up", abm.ramp_up_week ? `${abm.ramp_up_week} wk` : "—"],
              ].map(([l, v]) => (
                <div key={l} className="rounded-md border border-ink-700 bg-ink-900 p-2">
                  <div className="text-[10px] text-ink-400">{l}</div>
                  <div className="num text-sm font-semibold">{v}</div>
                </div>
              ))}
            </div>
            <div className="rounded-md border border-ink-700 bg-ink-900 p-2">
              <div className="mb-1 flex items-center justify-between text-xs"><span className="font-medium text-ink-200">{membership ? "Members" : `Daily ${unit}`} — you</span><Evidence kind="model" label="Simulated" /></div>
              <ResponsiveContainer width="100%" height={120}>
                <AreaChart data={dailyChart} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke="#1b2431" vertical={false} />
                  <XAxis dataKey="d" stroke="#5d6b80" fontSize={10} />
                  <YAxis stroke="#5d6b80" fontSize={10} width={36} />
                  <Tooltip {...TT} />
                  <ReferenceLine x={day + 1} stroke="#22d3ee" />
                  <Area dataKey="you" stroke="#22d3ee" fill="#22d3ee" fillOpacity={0.15} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="rounded-md border border-ink-700 bg-ink-900 p-2">
              <div className="mb-1 text-xs font-medium text-ink-200">Awareness of your business (%)</div>
              <ResponsiveContainer width="100%" height={90}>
                <LineChart data={dailyChart} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <XAxis dataKey="d" stroke="#5d6b80" fontSize={10} />
                  <YAxis stroke="#5d6b80" fontSize={10} width={28} domain={[0, 100]} />
                  <Tooltip {...TT} />
                  <ReferenceLine x={day + 1} stroke="#22d3ee" />
                  <Line dataKey="aware" stroke="#a78bfa" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="rounded-md border border-ink-700 bg-ink-900 p-3 text-xs">
              <div className="mb-2 font-medium text-ink-200">Monthly economics (agent simulation)</div>
              {abm.monthly_finance.map((m) => (
                <div key={m.month} className="flex justify-between py-0.5">
                  <span className="text-ink-400">Month {m.month}</span>
                  <span className="num">{num(m.capped_units)} {unit} · <span className={m.profit < 0 ? "text-red-300" : "text-emerald-300"}>{money(m.profit, { compact: true })}</span></span>
                </div>
              ))}
              <p className="mt-1.5 text-[10px] text-ink-500">Ramp-up from launch as awareness spreads. Steady-state static model: {money(res.finance.operating_profit, { compact: true })}/month.</p>
            </div>
            <div className="rounded-md border border-ink-700 bg-ink-900 p-3 text-xs">
              <div className="mb-2 font-medium text-ink-200">Who your customers are</div>
              {Object.entries(abm.metrics.customer_segments).map(([k, v]) => (
                <div key={k} className="mb-1">
                  <div className="flex justify-between text-ink-300"><span className="capitalize">{k}</span><span className="num">{pct(v)}</span></div>
                  <div className="mt-0.5 h-1 rounded bg-ink-800"><div className="h-1 rounded bg-userdata" style={{ width: `${(v || 0) * 100}%` }} /></div>
                </div>
              ))}
              <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5">
                {Object.entries(abm.metrics.customer_modes).filter(([, v]) => (v || 0) > 0.005).map(([k, v]) => (
                  <div key={k} className="flex justify-between"><span className="text-ink-400">{MODE_LABEL[k]}</span><span className="num">{pct(v)}</span></div>
                ))}
              </div>
            </div>
            <div className="text-[11px] text-ink-500">
              <Badge className="mb-1">{abm.age_source === "worldpop" ? "Age–sex: WorldPop" : "Age–sex: default assumption"}</Badge>
              <p>{abm.note} Seed {abm.seed}; {num(abm.metrics.decision_events as number)} purchase decisions simulated in {num(abm.duration_ms)} ms{abm.timing_ms ? ` (genomes built in ${num(abm.timing_ms.genome)} ms)` : ""}.</p>
              {abm.calibration?.applied && <p className="mt-1 text-warn">Calibrated: {abm.calibration.reason} ({abm.calibration.summary}).</p>}
              <Link href={`/app/projects/${p.id}/factors`} className="text-accent hover:underline">See all 615 factors →</Link>
            </div>
          </>
        )}
      </aside>
    </div>
  );
}
