"use client";

import { Copy, Download, Play, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { MarketingCurve, PriceCurve, ProfitHistogram, Tornado } from "@/components/charts";
import { Map as MarketMap } from "@/components/Map";
import { useProject } from "@/components/ProjectContext";
import { Badge, Button, Card, CardHeader, cn, Dialog, EmptyState, ErrorState, Evidence, Field, Input, Metric, Notice, NumberInput, Segmented, Select, Spinner, statusToKind, Tip } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money, num, pct, signed } from "@/lib/format";
import type { CompareRow, MarketData, Run, Scenario, ScenarioInputs, SimResult } from "@/lib/types";

const ADV_PARAMS = ["participation", "frequency", "beta_price", "distance_decay", "awareness_base", "competitor_price_ratio", "competitor_quality"];

export default function SimulationLab() {
  const { project: p, reload } = useProject();
  const arch = p.archetype!;
  const scenarios = useMemo(() => p.scenarios || [], [p.scenarios]);
  const baseline = scenarios.find((s) => s.is_baseline)!;
  const [selId, setSelId] = useState<string>(baseline?.id);
  const sel = scenarios.find((s) => s.id === selId) || baseline;
  const [draft, setDraft] = useState<ScenarioInputs>(sel.inputs);
  const [draftLoc, setDraftLoc] = useState(sel.location_id);
  const [results, setResults] = useState<Record<string, SimResult>>({});
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [market, setMarket] = useState<MarketData | null>(null);
  const [compare, setCompare] = useState<CompareRow[]>([]);
  const [agentColor, setAgentColor] = useState<"red" | "choice">("choice");
  const [sensTab, setSensTab] = useState<"price" | "tornado" | "marketing" | "stress">("price");
  const [newOpen, setNewOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [delOpen, setDelOpen] = useState(false);

  useEffect(() => {
    setDraft(sel.inputs);
    setDraftLoc(sel.location_id);
  }, [sel.id, sel.inputs, sel.location_id]);

  const loadResults = useCallback(async () => {
    const out: Record<string, SimResult> = {};
    await Promise.all(
      scenarios.filter((s) => s.latest_run).map(async (s) => {
        try {
          const r = await api<Run>(`/simulation-runs/${s.latest_run!.id}/results`);
          if (r.results) out[s.id] = r.results;
        } catch {
          /* ignore */
        }
      }),
    );
    setResults(out);
    api<{ rows: CompareRow[] }>(`/projects/${p.id}/compare`).then((r) => setCompare(r.rows)).catch(() => undefined);
  }, [scenarios, p.id]);
  useEffect(() => {
    loadResults();
  }, [loadResults]);

  useEffect(() => {
    api<MarketData>(`/projects/${p.id}/market?location_id=${draftLoc}`).then(setMarket).catch(() => setMarket(null));
  }, [p.id, draftLoc]);

  const res = results[sel.id];
  const baseRes = results[baseline.id];
  const dirty = JSON.stringify(draft) !== JSON.stringify(sel.inputs) || draftLoc !== sel.location_id;
  const stale = !!sel.latest_run?.stale;
  const hasSnapshot = !!market?.snapshot;

  function set<K extends keyof ScenarioInputs>(k: K, v: ScenarioInputs[K]) {
    setDraft((d) => ({ ...d, [k]: v }));
  }

  async function save(): Promise<boolean> {
    setSaving(true);
    setError(null);
    try {
      await api(`/scenarios/${sel.id}`, { method: "PATCH", json: { inputs: draft, location_id: draftLoc } });
      await reload();
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? (e.fields.length ? `${e.message}: ${e.fields.map((f) => `${f.field}: ${f.message}`).join("; ")}` : e.message) : "Save failed");
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function run() {
    setError(null);
    if (dirty && !(await save())) return;
    setRunning(true);
    try {
      const r = await api<Run>(`/scenarios/${sel.id}/runs`, { method: "POST" });
      setResults((x) => ({ ...x, [sel.id]: r.results! }));
      await reload();
      api<{ rows: CompareRow[] }>(`/projects/${p.id}/compare`).then((c) => setCompare(c.rows)).catch(() => undefined);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Simulation failed");
    } finally {
      setRunning(false);
    }
  }

  async function createScenario(clone: boolean) {
    const name = newName.trim() || `Scenario ${String.fromCharCode(64 + scenarios.length)}`;
    try {
      const s = await api<Scenario>(`/projects/${p.id}/scenarios`, { method: "POST", json: { name, clone_from: clone ? sel.id : baseline.id } });
      setNewOpen(false);
      setNewName("");
      await reload();
      setSelId(s.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create scenario");
    }
  }

  async function resetToBaseline() {
    await api(`/scenarios/${sel.id}/reset`, { method: "POST" });
    await reload();
  }

  async function rename(name: string) {
    await api(`/scenarios/${sel.id}`, { method: "PATCH", json: { name } });
    setRenaming(false);
    await reload();
  }

  async function remove() {
    await api(`/scenarios/${sel.id}`, { method: "DELETE" });
    setDelOpen(false);
    setSelId(baseline.id);
    await reload();
  }

  function exportCsv() {
    const head = ["Scenario", "Price", `Units (${arch.unit_label})`, "Revenue", "Operating cost", "Operating profit", "Profit P10", "Profit P50", "Profit P90", "P(loss)", "Break-even units", "Utilization", "Payback months"];
    const rows = compare.filter((r) => r.metrics).map((r) => {
      const m = r.metrics!;
      return [r.scenario.name, m.price, m.units_sold, m.revenue, m.operating_cost, m.operating_profit, m.profit_p10, m.profit_p50, m.profit_p90, m.prob_loss, m.break_even_units, m.utilization, m.payback_months];
    });
    const csv = [head, ...rows].map((r) => r.map((x) => (x === null || x === undefined ? "" : `"${String(x).replace(/"/g, '""')}"`)).join(",")).join("\n");
    const blob = new Blob([`# StrataIQ model estimates (${res?.model_version || ""}). Not a guarantee.\n${csv}`], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${p.name.replace(/[^a-z0-9]+/gi, "-")}-scenarios.csv`;
    a.click();
  }

  const d = (cur?: number | null, base?: number | null) => (cur === null || cur === undefined || base === null || base === undefined || sel.is_baseline ? null : cur - base);
  const center: [number, number] = market ? [market.location.lng, market.location.lat] : [p.locations[0].lng, p.locations[0].lat];
  const zones = useMemo(() => (res?.zones || []).map((z) => ({ lat: z.lat, lng: z.lng, value: z.capture * z.weight })), [res]);
  const comps = useMemo(
    () => (market?.competitors || []).filter((c) => c.active).map((c) => ({ id: c.id, name: c.name, lat: c.lat, lng: c.lng, kind: (c.source === "user" ? (c.is_hypothetical ? "hypothetical" : "user") : c.source) as "osm" | "user" | "hypothetical" | "demo" })),
    [market],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* scenario bar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-white/[0.06] px-4 py-2 md:px-6">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label="Scenarios">
          {scenarios.map((s) => (
            <button
              key={s.id}
              role="tab"
              aria-selected={s.id === sel.id}
              onClick={() => setSelId(s.id)}
              className={cn("rounded-md border px-3 py-1.5 text-xs", s.id === sel.id ? "border-accent bg-accent/10 text-ink-100" : "border-white/[0.07] text-ink-300 hover:border-ink-500")}
            >
              {s.name}
              {s.is_baseline && <span className="ml-1 text-ink-500">(baseline)</span>}
              {!s.latest_run && <span className="ml-1 text-ink-500">· not run</span>}
              {s.latest_run?.stale && <span className="ml-1 text-amber-300">· changed</span>}
            </button>
          ))}
        </div>
        <div className="ml-auto flex flex-wrap gap-1.5">
          <Button size="sm" onClick={() => setNewOpen(true)}><Plus className="h-3.5 w-3.5" /> New scenario</Button>
          <Button size="sm" onClick={() => createScenario(true)}><Copy className="h-3.5 w-3.5" /> Duplicate</Button>
          {!sel.is_baseline && <Button size="sm" onClick={resetToBaseline}><RotateCcw className="h-3.5 w-3.5" /> Reset to baseline</Button>}
          <Button size="sm" onClick={exportCsv} disabled={!compare.some((r) => r.metrics)}><Download className="h-3.5 w-3.5" /> Export CSV</Button>
        </div>
      </div>

      <div className="grid flex-1 gap-0 xl:grid-cols-[320px_1fr_360px]">
        {/* LEFT: controls */}
        <aside className="space-y-4 border-b border-white/[0.06] p-4 xl:max-h-[calc(100vh-150px)] xl:overflow-y-auto xl:border-b-0 xl:border-r">
          <div className="flex items-center justify-between gap-2">
            {renaming ? (
              <form onSubmit={(e) => { e.preventDefault(); rename((e.currentTarget.elements.namedItem("n") as HTMLInputElement).value); }} className="flex flex-1 gap-1">
                <Input name="n" defaultValue={sel.name} autoFocus className="h-8" />
                <Button size="sm" type="submit">OK</Button>
              </form>
            ) : (
              <button onClick={() => setRenaming(true)} className="truncate text-left text-sm font-semibold hover:text-accent" title="Rename">{sel.name}</button>
            )}
            {!sel.is_baseline && <button onClick={() => setDelOpen(true)} aria-label="Delete scenario" className="text-ink-500 hover:text-red-300"><Trash2 className="h-4 w-4" /></button>}
          </div>

          <Field label="Location">
            <Select value={draftLoc} onChange={(e) => setDraftLoc(e.target.value)}>
              {p.locations.map((l) => <option key={l.id} value={l.id}>{l.label} — {l.address.slice(0, 40)}</option>)}
            </Select>
          </Field>

          <Field label={`${arch.price_label}: ${money(draft.price)}`} kind="user">
            <input type="range" min={Math.max(1, Math.round(sel.inputs.price * 0.4))} max={Math.round(sel.inputs.price * 2)} step={Math.max(1, Math.round(sel.inputs.price / 100))} value={draft.price} onChange={(e) => set("price", Number(e.target.value))} className="w-full" aria-label="Price" />
            <NumberInput value={draft.price} onChange={(v) => v && set("price", v)} prefix="₹" min={1} />
          </Field>
          <Field label={`Marketing / month: ${money(draft.marketing_spend)}`} kind="user">
            <input type="range" min={0} max={Math.max(100000, sel.inputs.marketing_spend * 3)} step={1000} value={draft.marketing_spend} onChange={(e) => set("marketing_spend", Number(e.target.value))} className="w-full" aria-label="Marketing spend" />
          </Field>
          <Field label={<span className="inline-flex items-center gap-1">Attractiveness / quality: {draft.quality.toFixed(2)} <Tip text="Your claimed quality on a 0–1 scale. Competitors with unknown quality are assumed at 0.50. Unverified user claim." /></span>} kind="user">
            <input type="range" min={0} max={1} step={0.05} value={draft.quality} onChange={(e) => set("quality", Number(e.target.value))} className="w-full" aria-label="Quality" />
          </Field>
          <Field
            label={<span className="inline-flex items-center gap-1">Opening hours <Tip text="Each synthetic agent has 48 hour-by-hour availability parameters. Hours that miss when people are free cost you customers in the agent simulation." /></span>}
            kind={draft.offer?.open_hour != null ? "user" : "assumption"}
            hint={draft.offer?.open_hour != null ? undefined : "Using the hours from your profile, or the category default."}
          >
            <div className="flex items-center gap-2 text-xs">
              <Select aria-label="Opening time" className="h-8" value={draft.offer?.open_hour ?? ""} onChange={(e) => set("offer", { open_hour: e.target.value === "" ? null : Number(e.target.value), close_hour: draft.offer?.close_hour ?? 22, weekend_open: draft.offer?.weekend_open ?? true, attributes: draft.offer?.attributes ?? {} })}>
                <option value="">default</option>
                {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
              </Select>
              <span className="text-ink-400">to</span>
              <Select aria-label="Closing time" className="h-8" value={draft.offer?.close_hour ?? ""} onChange={(e) => set("offer", { open_hour: draft.offer?.open_hour ?? 6, close_hour: e.target.value === "" ? null : Number(e.target.value), weekend_open: draft.offer?.weekend_open ?? true, attributes: draft.offer?.attributes ?? {} })}>
                <option value="">default</option>
                {Array.from({ length: 24 }, (_, h) => h + 1).map((h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
              </Select>
              <label className="ml-auto flex items-center gap-1 text-ink-300">
                <input type="checkbox" checked={draft.offer?.weekend_open ?? true} onChange={(e) => set("offer", { open_hour: draft.offer?.open_hour ?? null, close_hour: draft.offer?.close_hour ?? null, weekend_open: e.target.checked, attributes: draft.offer?.attributes ?? {} })} /> Weekends
              </label>
            </div>
          </Field>
          <div className="grid grid-cols-2 gap-2">
            {arch.capacity_fields.map((f) => (
              <Field key={f.key} label={f.label} kind="user">
                <NumberInput value={draft.capacity[f.key] ?? f.default} onChange={(v) => set("capacity", { ...draft.capacity, [f.key]: v ?? 0 })} min={0} />
              </Field>
            ))}
          </div>

          <details className="group rounded-md border border-white/[0.07]" open>
            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-ink-200">Monthly costs</summary>
            <div className="grid grid-cols-2 gap-2 p-3 pt-0">
              {(["rent", "payroll", "utilities", "other_fixed"] as const).map((k) => (
                <Field key={k} label={k === "other_fixed" ? "Other fixed" : k[0].toUpperCase() + k.slice(1)}>
                  <NumberInput value={draft[k]} onChange={(v) => set(k, v ?? 0)} prefix="₹" min={0} />
                </Field>
              ))}
              <Field label="Variable cost / unit" kind={draft.variable_cost_per_unit === null ? "assumption" : "user"}>
                <NumberInput value={draft.variable_cost_per_unit} onChange={(v) => set("variable_cost_per_unit", v)} prefix="₹" allowEmpty placeholder="default" />
              </Field>
              <Field label="Startup cost">
                <NumberInput value={draft.startup_cost} onChange={(v) => set("startup_cost", v ?? 0)} prefix="₹" min={0} />
              </Field>
            </div>
          </details>

          <details className="rounded-md border border-white/[0.07]">
            <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-ink-200">Market assumptions (advanced)</summary>
            <div className="space-y-3 p-3 pt-0">
              <Field label="Typical local price" kind={draft.reference_price ? "user" : "unknown"} hint="Leave empty to derive it from competitor prices you entered, or fall back to your baseline price.">
                <NumberInput value={draft.reference_price} onChange={(v) => set("reference_price", v)} prefix="₹" allowEmpty placeholder="unknown" />
              </Field>
              {ADV_PARAMS.map((k) => {
                const pd = arch.params[k];
                if (!pd) return null;
                const ov = draft.param_overrides[k];
                return (
                  <Field key={k} label={<span className="inline-flex items-center gap-1">{res?.parameters[k]?.label || k} <Tip text={pd.description} /></span>} kind={ov !== undefined ? "user" : "assumption"} hint={`Default ${pd.value} (range ${pd.low}–${pd.high}) ${pd.unit}`}>
                    <NumberInput
                      value={ov ?? null}
                      allowEmpty
                      placeholder={String(pd.value)}
                      onChange={(v) => {
                        const next = { ...draft.param_overrides };
                        if (v === null) delete next[k];
                        else next[k] = v;
                        set("param_overrides", next);
                      }}
                    />
                  </Field>
                );
              })}
              <Field label="Random seed" hint="Same inputs + same seed = identical results.">
                <NumberInput value={draft.seed} onChange={(v) => set("seed", Math.max(0, Math.round(v ?? 42)))} min={0} />
              </Field>
            </div>
          </details>

          <div className="sticky bottom-0 -mx-4 flex gap-2 border-t border-white/[0.06] bg-ink-950/80 backdrop-blur-xl p-3">
            <Button variant="secondary" size="sm" onClick={save} loading={saving} disabled={!dirty}><Save className="h-3.5 w-3.5" /> Save</Button>
            <Button variant="primary" className="flex-1" onClick={run} loading={running} disabled={!hasSnapshot}>
              <Play className="h-4 w-4" /> {res && !dirty && !stale ? "Recalculate" : "Run simulation"}
            </Button>
          </div>
          {!hasSnapshot && market && (
            <Notice tone="warn">No market data for this location yet. <Link className="text-accent underline" href={`/app/projects/${p.id}/market`}>Load it on the Market map</Link>.</Notice>
          )}
          {(dirty || stale) && res && <p className="text-xs text-amber-300">Inputs changed since the last run. Results shown are from the previous run.</p>}
        </aside>

        {/* CENTER: map + analysis */}
        <section className="min-w-0 space-y-4 p-4 xl:max-h-[calc(100vh-150px)] xl:overflow-y-auto">
          {error && <ErrorState message={error} />}
          {res?.evidence?.failed_layers?.includes("competitors") && res.competitors.length === 0 && (
            <Notice tone="warn">Competitor data failed to load for this location, so this run assumes no competitors and is optimistic. Refresh live data on the Market map, then re-run.</Notice>
          )}
          <div className="relative h-[380px] overflow-hidden rounded-lg border border-white/[0.07]">
            <MarketMap
              fill
              center={center}
              catchment={market?.snapshot?.catchment_geojson || null}
              zones={zones}
              competitors={comps}
              candidates={p.locations.map((l) => ({ id: l.id, label: l.label, lat: l.lat, lng: l.lng, active: l.id === draftLoc }))}
              agents={res?.agents.rows}
              agentColor={agentColor}
              layers={{ catchment: true, zones: true, competitors: true, agents: true, buildings3d: true }}
              fitKey={`${draftLoc}-${market?.snapshot?.id || ""}`}
              onCandidateClick={(id) => setDraftLoc(id)}
            />
            <div className="absolute bottom-8 left-2 z-10 space-y-1.5 rounded-2xl border border-white/[0.07] bg-white/[0.025]/95 p-2 text-[11px]">
              <Segmented value={agentColor} onChange={setAgentColor} options={[{ value: "choice", label: "Colour by choice" }, { value: "red", label: "All agents" }]} />
              {agentColor === "choice" ? (
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-ink-300">
                  <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-accent" /> chooses you</span>
                  <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-agent" /> a competitor</span>
                  <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-ink-500" /> none / elsewhere</span>
                </div>
              ) : (
                <div className="text-ink-300">Red dots = synthetic customers in the catchment</div>
              )}
              <div className="text-ink-500">Synthetic sample — not real people. Glow = your modeled capture by zone.</div>
            </div>
            {running && <div className="absolute inset-0 z-20 flex items-center justify-center bg-ink-950/60"><Spinner label="Running choice model and Monte Carlo…" /></div>}
          </div>

          {res ? (
            <>
              <Card>
                <CardHeader
                  title="Sensitivity"
                  subtitle="Every curve is recomputed by the model, not interpolated."
                  right={<Segmented value={sensTab} onChange={setSensTab} options={[{ value: "price", label: "Price" }, { value: "tornado", label: "Assumptions" }, { value: "marketing", label: "Marketing" }, { value: "stress", label: "Stress tests" }]} />}
                />
                <div className="p-3">
                  {sensTab === "price" && res.sensitivity && (
                    <>
                      <PriceCurve data={res.sensitivity.price_curve} current={res.summary.price} unit={res.unit_label} />
                      <p className="px-2 text-xs text-ink-400">Green: operating profit per month. Grey dashed: {res.unit_label} sold. Holding everything else fixed.</p>
                    </>
                  )}
                  {sensTab === "tornado" && res.sensitivity && (
                    <>
                      <Tornado data={res.sensitivity.tornado} base={res.finance.operating_profit} />
                      <p className="px-2 text-xs text-ink-400">Change in monthly profit when each assumption moves across its documented range (others held at default). Purple = values you set.</p>
                      {res.sensitivity.thresholds.participation_break_even !== undefined && (
                        <Notice className="mt-2">
                          {res.sensitivity.thresholds.participation_break_even === null
                            ? "Break-even is not reachable by demand alone here (capacity or unit margin is the limit)."
                            : <>Break-even requires at least <b>{pct(res.sensitivity.thresholds.participation_break_even, 1)}</b> of residents to be in this market (model assumes {pct(res.parameters.participation.value, 1)}).</>}
                        </Notice>
                      )}
                    </>
                  )}
                  {sensTab === "marketing" && res.sensitivity && (
                    <>
                      <MarketingCurve data={res.sensitivity.marketing_curve} current={draft.marketing_spend} />
                      <p className="px-2 text-xs text-ink-400">Marketing raises awareness of a new business along an uncalibrated saturating curve; treat the shape as illustrative of diminishing returns.</p>
                    </>
                  )}
                  {sensTab === "stress" && res.sensitivity && (
                    <table className="w-full text-sm">
                      <thead><tr className="text-left text-xs text-ink-400"><th className="py-1.5 font-normal">Stress test</th><th className="text-right font-normal">{res.unit_label}</th><th className="text-right font-normal">Profit / mo</th><th className="text-right font-normal">Change</th></tr></thead>
                      <tbody>
                        {res.sensitivity.stress_tests.map((s) => (
                          <tr key={s.label} className="border-t border-white/[0.06]">
                            <td className="py-2">{s.label}</td>
                            <td className="num text-right">{num(s.units)}</td>
                            <td className={cn("num text-right", s.profit < 0 && "text-red-300")}>{money(s.profit)}</td>
                            <td className={cn("num text-right", s.delta_profit < 0 ? "text-red-300" : "text-emerald-300")}>{money(s.delta_profit, { sign: true })}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </Card>

              <Card>
                <CardHeader title="Scenario comparison" subtitle="Latest successful run of each scenario." />
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px] text-sm">
                    <thead>
                      <tr className="border-b border-white/[0.06] text-left text-xs text-ink-400">
                        <th className="px-3 py-2 font-normal">Metric</th>
                        {compare.map((r) => <th key={r.scenario.id} className={cn("px-3 py-2 text-right font-normal", r.scenario.id === sel.id && "text-accent")}>{r.scenario.name}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {(
                        [
                          ["Price", (m) => money(m.price)],
                          [`${arch.unit_label} sold`, (m) => num(m.units_sold)],
                          ["Revenue / mo", (m) => money(m.revenue, { compact: true })],
                          ["Operating cost / mo", (m) => money(m.operating_cost, { compact: true })],
                          ["Operating profit / mo", (m) => money(m.operating_profit, { compact: true })],
                          ["Profit P10 – P90", (m) => `${money(m.profit_p10, { compact: true })} – ${money(m.profit_p90, { compact: true })}`],
                          ["Modeled P(loss)", (m) => pct(m.prob_loss)],
                          ["Break-even units", (m) => num(m.break_even_units)],
                          ["Capacity use", (m) => pct(m.utilization)],
                          ["Payback", (m) => (m.payback_months ? `${num(m.payback_months, 1)} mo` : "not reached")],
                        ] as [string, (m: NonNullable<CompareRow["metrics"]>) => string][]
                      ).map(([label, f]) => (
                        <tr key={label} className="border-b border-white/[0.06]/60">
                          <td className="px-3 py-1.5 text-ink-300">{label}</td>
                          {compare.map((r) => <td key={r.scenario.id} className="num px-3 py-1.5 text-right">{r.metrics ? f(r.metrics) : <span className="text-ink-500">not run</span>}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex items-center justify-between px-3 py-2 text-xs text-ink-400">
                  <span>The best scenario depends on your goal; see <Link href={`/app/projects/${p.id}/decisions`} className="text-accent hover:underline">Decisions</Link> for a ranked recommendation.</span>
                  <Evidence kind="model" />
                </div>
              </Card>

              <Card>
                <CardHeader title="Model parameters used" subtitle={`Model ${res.model_version} · ${res.duration_ms} ms · seed ${draft.seed}`} />
                <div className="grid gap-1 p-3 text-xs sm:grid-cols-2">
                  {Object.entries(res.parameters).map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between gap-2 rounded px-2 py-1 hover:bg-ink-850" title={v.description}>
                      <span className="truncate text-ink-300">{v.label}</span>
                      <span className="flex items-center gap-1.5"><span className="num">{num(v.value, 4)}</span><Evidence kind={statusToKind(v.status)} /></span>
                    </div>
                  ))}
                </div>
                <ul className="space-y-1 border-t border-white/[0.06] p-3 text-xs text-ink-400">
                  {res.limitations.map((l) => <li key={l}>• {l}</li>)}
                </ul>
              </Card>
            </>
          ) : (
            <EmptyState title="Not simulated yet" body="Adjust the inputs on the left and run the simulation. The model uses the live market snapshot for this location." action={<Button variant="primary" onClick={run} loading={running} disabled={!hasSnapshot}><Play className="h-4 w-4" /> Run simulation</Button>} />
          )}
        </section>

        {/* RIGHT: results */}
        <aside className="space-y-3 border-t border-white/[0.06] p-4 xl:max-h-[calc(100vh-150px)] xl:overflow-y-auto xl:border-l xl:border-t-0">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Results</h2>
            {res && <Badge tone={sel.is_baseline ? "accent" : "neutral"}>{sel.is_baseline ? "baseline" : "vs baseline"}</Badge>}
          </div>
          {!res && <p className="text-sm text-ink-400">Run the simulation to see results.</p>}
          {res && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <Metric label={`${res.unit_label} / mo`} value={num(res.summary.units_sold)} kind="model" delta={d(res.summary.units_sold, baseRes?.summary.units_sold) !== null ? signed(d(res.summary.units_sold, baseRes?.summary.units_sold)) : null} deltaGood={(d(res.summary.units_sold, baseRes?.summary.units_sold) ?? 0) >= 0} sub={res.summary.capacity_bound ? "capacity-bound" : undefined} />
                <Metric label="Revenue / mo" value={money(res.finance.revenue, { compact: true })} kind="model" delta={d(res.finance.revenue, baseRes?.finance.revenue) !== null ? money(d(res.finance.revenue, baseRes?.finance.revenue), { compact: true, sign: true }) : null} deltaGood={(d(res.finance.revenue, baseRes?.finance.revenue) ?? 0) >= 0} />
                <Metric
                  label="Operating profit / mo"
                  className="col-span-2"
                  value={<span className={res.finance.operating_profit < 0 ? "text-red-300" : "text-emerald-300"}>{money(res.finance.operating_profit)}</span>}
                  kind="model"
                  delta={d(res.finance.operating_profit, baseRes?.finance.operating_profit) !== null ? money(d(res.finance.operating_profit, baseRes?.finance.operating_profit), { sign: true }) : null}
                  deltaGood={(d(res.finance.operating_profit, baseRes?.finance.operating_profit) ?? 0) >= 0}
                  sub={res.monte_carlo ? `P10 ${money(res.monte_carlo.profit.p10, { compact: true })} · P90 ${money(res.monte_carlo.profit.p90, { compact: true })}` : undefined}
                />
                <Metric label="Modeled P(loss)" value={pct(res.monte_carlo?.prob_loss)} kind="model" delta={d(res.monte_carlo?.prob_loss, baseRes?.monte_carlo?.prob_loss) !== null ? `${signed((d(res.monte_carlo?.prob_loss, baseRes?.monte_carlo?.prob_loss) ?? 0) * 100)} pts` : null} deltaGood={(d(res.monte_carlo?.prob_loss, baseRes?.monte_carlo?.prob_loss) ?? 0) <= 0} />
                <Metric label="Break-even" value={res.finance.break_even_units === null ? "n/a" : num(res.finance.break_even_units)} sub={res.unit_label} kind="model" />
                <Metric label="Capacity use" value={pct(res.finance.utilization)} sub={`of ${num(res.summary.capacity_units)}`} kind="model" />
                <Metric label="Payback" value={res.finance.payback_months ? `${num(res.finance.payback_months, 1)} mo` : "not reached"} kind="model" />
              </div>
              {res.monte_carlo && (
                <Card className="p-3">
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="font-medium text-ink-200">Profit distribution ({res.monte_carlo.draws} draws)</span>
                    <Tip text={res.monte_carlo.note} />
                  </div>
                  <ProfitHistogram mc={res.monte_carlo} />
                </Card>
              )}
              <Card className="space-y-2 p-3 text-xs">
                <div className="font-medium text-ink-200">Demand funnel</div>
                <FunnelRow label={`In-market ${res.unit_label} in catchment`} v={res.summary.in_market_units} max={res.summary.in_market_units} />
                <FunnelRow label="Captured by all modeled businesses" v={res.summary.in_market_units * res.summary.captured_by_all_modeled} max={res.summary.in_market_units} />
                <FunnelRow label="Modeled demand for you" v={res.summary.modeled_demand_units} max={res.summary.in_market_units} accent />
                <div className="flex justify-between text-ink-400"><span>Awareness of your business</span><span className="num">{pct(res.summary.awareness)}</span></div>
                <div className="flex justify-between text-ink-400">
                  <span>Reference price</span>
                  <span className="flex items-center gap-1.5"><span className="num">{money(res.summary.reference_price)}</span><Evidence kind={statusToKind(res.summary.reference_price_status)} /></span>
                </div>
              </Card>
              <Card className="space-y-2 p-3 text-xs">
                <div className="font-medium text-ink-200">Affordability at {money(res.summary.price)} <Evidence kind="model" className="ml-1" /></div>
                {res.segments.map((s) => (
                  <div key={s.key}>
                    <div className="flex justify-between text-ink-300"><span>{s.label} ({pct(s.share)})</span><span className="num">{pct(s.affordability_at_price)}</span></div>
                    <div className="mt-1 h-1.5 rounded bg-ink-800"><div className="h-1.5 rounded bg-model" style={{ width: `${Math.round(s.affordability_at_price * 100)}%` }} /></div>
                    <div className="mt-0.5 text-[10px] text-ink-500">{num(s.units_to_user)} of your {res.unit_label}</div>
                  </div>
                ))}
                <p className="text-[10px] text-ink-500">Share of each synthetic segment whose assumed willingness to pay exceeds your price.</p>
              </Card>
              {res.drivers.length > 0 && (
                <Card className="space-y-1.5 p-3 text-xs">
                  <div className="font-medium text-ink-200">What moves profit most</div>
                  {res.drivers.slice(0, 5).map((x) => (
                    <div key={x.param} className="flex justify-between"><span className="text-ink-300">{x.label}</span><span className="num">{x.spearman_rho > 0 ? "+" : ""}{x.spearman_rho.toFixed(2)}</span></div>
                  ))}
                  <p className="text-[10px] text-ink-500">Spearman correlation across Monte Carlo draws. Describes the model, not proven causes.</p>
                </Card>
              )}
              {res.competitors.length > 0 && (
                <Card className="p-3 text-xs">
                  <div className="mb-1.5 font-medium text-ink-200">Modeled competitor shares</div>
                  {res.competitors.slice().sort((a, b) => b.modeled_units - a.modeled_units).slice(0, 6).map((c) => (
                    <div key={c.id} className="flex justify-between gap-2 py-0.5">
                      <span className="truncate text-ink-300">{c.name}</span>
                      <span className="num shrink-0">{pct(c.modeled_share_of_in_market, 1)} <span className="text-ink-500">{c.price_status === "assumed" ? "· price assumed" : ""}</span></span>
                    </div>
                  ))}
                </Card>
              )}
              <Card className="p-3 text-[11px] text-ink-400">
                <div className="mb-1 font-medium text-ink-300">Included in operating profit</div>
                {res.finance.included.map((x) => <div key={x}>• {x}</div>)}
                <div className="mb-1 mt-2 font-medium text-ink-300">Not included</div>
                {res.finance.excluded.map((x) => <div key={x}>• {x}</div>)}
              </Card>
            </>
          )}
        </aside>
      </div>

      <Dialog open={newOpen} onClose={() => setNewOpen(false)} title="New scenario" footer={<><Button onClick={() => setNewOpen(false)}>Cancel</Button><Button variant="primary" onClick={() => createScenario(false)}>Create from baseline</Button></>}>
        <Field label="Name"><Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Lower price, Location B, Stronger marketing" autoFocus /></Field>
      </Dialog>
      <Dialog open={delOpen} onClose={() => setDelOpen(false)} title="Delete scenario?" footer={<><Button onClick={() => setDelOpen(false)}>Cancel</Button><Button variant="danger" onClick={remove}>Delete</Button></>}>
        “{sel.name}” and its run history will be deleted.
      </Dialog>
    </div>
  );
}

function FunnelRow({ label, v, max, accent }: { label: string; v: number; max: number; accent?: boolean }) {
  return (
    <div>
      <div className="flex justify-between text-ink-300"><span>{label}</span><span className="num">{num(v)}</span></div>
      <div className="mt-1 h-1.5 rounded bg-ink-800"><div className={cn("h-1.5 rounded", accent ? "bg-accent" : "bg-ink-500")} style={{ width: `${max ? Math.max(1, (v / max) * 100) : 0}%` }} /></div>
    </div>
  );
}
