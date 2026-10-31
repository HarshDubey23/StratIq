"use client";

import { ClipboardCopy, Dna, Printer, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AgentXray from "@/components/AgentXray";
import { useProject } from "@/components/ProjectContext";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Evidence, Notice, Select, Spinner, cn } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { CHANNEL_LABEL, GROUP_COLOR, GROUP_LABEL, MECH_LABEL, pctRGB } from "@/lib/genome";
import { num } from "@/lib/format";
import type { GenomeMatrix, Run, SimResult, SurveyKit } from "@/lib/types";

function decode(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function DnaCanvas({ m, onPick }: { m: GenomeMatrix; onPick: (agent: number) => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ r: number; c: number; x: number; y: number } | null>(null);
  const bytes = useMemo(() => decode(m.data), [m.data]);
  const BAND = 6;

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    cv.width = m.cols + BAND;
    cv.height = m.rows;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(cv.width, cv.height);
    const hex = (h: string) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
    for (let r = 0; r < m.rows; r++) {
      const g = hex(GROUP_COLOR[m.groups[r]] || "#334155");
      for (let c = 0; c < BAND; c++) {
        const o = (r * cv.width + c) * 4;
        img.data[o] = g[0];
        img.data[o + 1] = g[1];
        img.data[o + 2] = g[2];
        img.data[o + 3] = c < BAND - 1 ? 255 : 0;
      }
      for (let c = 0; c < m.cols; c++) {
        const [R, G, B] = pctRGB(bytes[r * m.cols + c]);
        const o = (r * cv.width + c + BAND) * 4;
        img.data[o] = R;
        img.data[o + 1] = G;
        img.data[o + 2] = B;
        img.data[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [m, bytes]);

  function locate(e: React.MouseEvent) {
    const cv = ref.current;
    if (!cv) return null;
    const rect = cv.getBoundingClientRect();
    const c = Math.floor(((e.clientX - rect.left) / rect.width) * cv.width) - BAND;
    const r = Math.floor(((e.clientY - rect.top) / rect.height) * cv.height);
    if (r < 0 || r >= m.rows) return null;
    return { r, c: Math.max(-1, Math.min(m.cols - 1, c)), x: e.clientX - (wrap.current?.getBoundingClientRect().left || 0), y: e.clientY - (wrap.current?.getBoundingClientRect().top || 0) };
  }

  const hp = hover && hover.c >= 0 ? m.params[hover.c] : null;
  return (
    <div ref={wrap} className="relative">
      <div className="relative ml-[1%] h-5 text-[9px] text-ink-500">
        {m.blocks.map((b) => (
          <div key={b.key} className="absolute top-0 truncate border-l border-white/[0.07] pl-0.5" style={{ left: `${((b.start + BAND) / (m.cols + BAND)) * 100}%`, width: `${(b.size / (m.cols + BAND)) * 100}%` }} title={b.label}>
            {b.size >= 30 ? b.label : ""}
          </div>
        ))}
      </div>
      <canvas
        ref={ref}
        className="h-[min(62vh,640px)] w-full cursor-crosshair rounded border border-white/[0.06]"
        style={{ imageRendering: "pixelated" }}
        onMouseMove={(e) => setHover(locate(e))}
        onMouseLeave={() => setHover(null)}
        onClick={(e) => {
          const h = locate(e);
          if (h) onPick(m.agent_index[h.r]);
        }}
        aria-label="Market DNA matrix: rows are synthetic agents, columns are the 615 genome parameters"
      />
      {hover && (
        <div className="pointer-events-none absolute z-10 w-64 rounded-md border border-ink-600 bg-ink-950/95 p-2 text-[11px] shadow-xl" style={{ left: Math.min(hover.x + 14, (wrap.current?.clientWidth || 600) - 270), top: hover.y + 14 }}>
          <div className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full" style={{ background: GROUP_COLOR[m.groups[hover.r]] }} /> Agent #{m.agent_index[hover.r].toLocaleString("en-IN")} · {GROUP_LABEL[m.groups[hover.r]]}</div>
          {hp ? (
            <>
              <div className="mt-1 font-medium text-ink-100">{hp.label}</div>
              <div className="text-ink-400">{bytes[hover.r * m.cols + hover.c]}th percentile · {MECH_LABEL[hp.mechanism] || hp.mechanism}</div>
            </>
          ) : null}
          <div className="mt-1 text-ink-500">Click to X-ray this agent</div>
        </div>
      )}
    </div>
  );
}

export default function GenomePage() {
  const { project: p } = useProject();
  const scenarios = useMemo(() => p.scenarios || [], [p.scenarios]);
  const [sid, setSid] = useState(scenarios.find((s) => s.is_baseline)?.id || scenarios[0]?.id);
  const sc = scenarios.find((s) => s.id === sid);
  const runId = sc?.latest_run?.status === "succeeded" ? sc.latest_run.id : sc?.latest_run?.id;
  const [res, setRes] = useState<SimResult | null>(null);
  const [m, setM] = useState<GenomeMatrix | null>(null);
  const [kit, setKit] = useState<SurveyKit | null>(null);
  const [kitLoading, setKitLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pick, setPick] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    setErr(null);
    setM(null);
    setKit(null);
    try {
      const r = await api<Run>(`/simulation-runs/${runId}/results`);
      setRes(r.results || null);
      if (r.results?.abm?.genome) setM(await api<GenomeMatrix>(`/simulation-runs/${runId}/genome-matrix?rows=480`));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not load the market DNA");
    } finally {
      setLoading(false);
    }
  }, [runId]);
  useEffect(() => {
    load();
  }, [load]);

  async function loadKit() {
    if (!runId) return;
    setKitLoading(true);
    try {
      setKit(await api<SurveyKit>(`/simulation-runs/${runId}/survey-kit`));
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not generate the survey");
    } finally {
      setKitLoading(false);
    }
  }

  function kitText(k: SurveyKit) {
    const lines = [k.title, "", k.purpose, ""];
    let sec = "";
    k.questions.forEach((q, i) => {
      if (q.section !== sec) {
        sec = q.section;
        lines.push("", sec.toUpperCase());
      }
      lines.push(`${i + 1}. ${q.text}`);
      (q.options || []).forEach((o) => lines.push(`   [ ] ${o}`));
      if (q.type === "money") lines.push("   ₹ ______");
      if (q.type === "scale5") lines.push("   1   2   3   4   5");
    });
    lines.push("", `Sample: ${k.sample_size.recommended} people (minimum ${k.sample_size.minimum}). ${k.sample_size.how}`);
    return lines.join("\n");
  }

  const abm = res?.abm;
  const dec = abm?.decomposition;
  const g = m?.group_counts;

  if (!sc) return <div className="p-6"><EmptyState title="No scenario" /></div>;

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-5 p-4 sm:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-[11px]st text-agent"><Dna className="h-3.5 w-3.5" /> Market DNA</div>
          <h1 className="mt-1 text-2xl font-semibold text-ink-100">Every synthetic customer, every parameter</h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-400">
            Each row is one synthetic agent; each column is one of its 615 genome parameters, coloured by where that agent sits in the population.
            Rows are grouped by what the agent finally did. Click any row to X-ray the decision.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={sid} onChange={(e) => { setSid(e.target.value); setPick(null); }} aria-label="Scenario" className="w-56">
            {scenarios.map((s) => <option key={s.id} value={s.id}>{s.name}{s.is_baseline ? " (baseline)" : ""}</option>)}
          </Select>
        </div>
      </div>

      {err && <ErrorState message={err} onRetry={load} />}
      {!runId && (
        <EmptyState icon={<Dna className="h-6 w-6" />} title="Run the live market first" body="The DNA matrix is built from a finished simulation run."
          action={<Link href={`/app/projects/${p.id}/live`} className="text-accent underline">Open the live market</Link>} />
      )}
      {loading && <Card className="p-10"><Spinner label="Rebuilding 10,000 genomes and ranking 615 parameters…" /></Card>}
      {res && abm && !abm.genome && <Notice tone="warn">This run predates the Agent Genome. Re-run the scenario on the Live market tab.</Notice>}

      {abm?.genome && m && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {[
              ["Synthetic agents", num(abm.n_agents), `each ≈ ${num(abm.scale)} residents`],
              ["Parameters per agent", String(abm.genome.per_agent), "16 blocks"],
              ["Parameters simulated", num(abm.genome.total_parameters), `genomes in ${num(abm.timing_ms?.genome)} ms`],
              ["Chose you", num(g?.you), "in-market agents", "you"],
              ["Chose a competitor", num(g?.competitor), "in-market agents", "competitor"],
              ["Chose nothing", num(g?.none), `${num(g?.not_in_market)} not in market`, "none"],
            ].map(([l, v, sub, grp]) => (
              <Card key={l} className="p-3">
                <div className="flex items-center gap-1.5 text-[11px] text-ink-400">{grp && <span className="h-2 w-2 rounded-full" style={{ background: GROUP_COLOR[grp] }} />}{l}</div>
                <div className="num mt-0.5 text-2xl font-semibold text-ink-100">{v}</div>
                <div className="text-[11px] text-ink-500">{sub}</div>
              </Card>
            ))}
          </div>

          <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
            <Card className="p-4">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm font-medium text-ink-100">{m.rows} sampled agents × {m.cols} parameters</div>
                <div className="flex flex-wrap items-center gap-3 text-[11px] text-ink-400">
                  {Object.entries(GROUP_LABEL).map(([k, l]) => <span key={k} className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm" style={{ background: GROUP_COLOR[k] }} />{l}</span>)}
                  <span className="flex items-center gap-1">percentile <span className="h-2 w-16 rounded-sm" style={{ background: "linear-gradient(90deg,#2563eb,#10141c,#fb923c,#FF4D5E)" }} /></span>
                </div>
              </div>
              <DnaCanvas m={m} onPick={setPick} />
              <p className="mt-2 text-[11px] text-ink-500">{m.note} Stratified sample: rows within each group are sorted by how much they like your business.</p>
            </Card>

            <div className="space-y-4">
              {pick !== null && runId ? (
                <AgentXray runId={runId} agent={pick} price={res?.summary.price} onClose={() => setPick(null)} className="max-h-[78vh]" />
              ) : (
                <Card className="p-4">
                  <CardHeader title="What makes your customers different" subtitle="Mean population percentile: your customers vs competitors' customers" right={<Evidence kind="model" label="Simulated" />} />
                  {m.separators.length ? (
                    <div className="mt-3 space-y-2">
                      {m.separators.map((s) => (
                        <div key={s.key} className="text-[11px]">
                          <div className="flex justify-between gap-2"><span className="truncate text-ink-200" title={s.label}>{s.label}</span><span className={cn("num", s.delta_pct > 0 ? "text-accent" : "text-observed")}>{s.delta_pct > 0 ? "+" : ""}{s.delta_pct}</span></div>
                          <div className="relative mt-0.5 h-1.5 rounded bg-ink-800">
                            <div className={cn("absolute top-0 h-1.5 rounded", s.delta_pct > 0 ? "left-1/2 bg-accent" : "right-1/2 bg-observed")} style={{ width: `${Math.min(50, Math.abs(s.delta_pct))}%` }} />
                          </div>
                        </div>
                      ))}
                      <p className="pt-1 text-[10px] text-ink-500">Cyan: your customers sit higher on this parameter. Amber: competitors&apos; customers do. Use this to sharpen targeting and positioning.</p>
                    </div>
                  ) : (
                    <p className="mt-3 text-xs text-ink-400">Too few agents chose you (or competitors) to compare groups. Try a lower price or more marketing in the Simulation lab.</p>
                  )}
                </Card>
              )}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="p-4">
              <CardHeader title="Where you win and lose" subtitle="Average utility edge vs each agent's best competitor (you − them), by channel" right={<Evidence kind="model" label="Simulated" />} />
              <div className="mt-3 space-y-4">
                {(["chose_competitor", "chose_none", "chose_you"] as const).map((k) => {
                  const d = dec?.[k];
                  if (!d) return null;
                  return (
                    <div key={k}>
                      <div className="mb-1 text-xs text-ink-300">{k === "chose_competitor" ? "Agents you lost to a competitor" : k === "chose_none" ? "Agents who bought nothing" : "Your customers"} <span className="text-ink-500">· {num(d.n_agents)}</span></div>
                      {Object.entries(d.channels).map(([ch, v]) => (
                        <div key={ch} className="flex items-center gap-2 text-[11px]">
                          <span className="w-44 shrink-0 text-ink-400">{CHANNEL_LABEL[ch] || ch}</span>
                          <div className="relative h-2 flex-1 rounded bg-ink-800">
                            <div className={cn("absolute top-0 h-2 rounded", v.edge >= 0 ? "left-1/2 bg-model" : "right-1/2 bg-danger")} style={{ width: `${Math.min(50, Math.abs(v.edge) * 25)}%` }} />
                          </div>
                          <span className="num w-12 text-right text-ink-300">{v.edge >= 0 ? "+" : ""}{v.edge.toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            </Card>

            <div className="space-y-4">
              <Card className="p-4">
                <CardHeader title="Parameters working against you" subtitle="Mean effect on you vs best competitor among agents you lost" />
                <div className="mt-3 space-y-1.5">
                  {(abm.top_drivers_against_you || []).slice(0, 10).map((d) => (
                    <div key={d.key} className="flex items-center justify-between gap-2 text-[11px]">
                      <span className="truncate text-ink-200" title={d.label}>{d.label}</span>
                      <span className="flex shrink-0 items-center gap-2"><Badge>{d.feat?.replace("attr_", "") || d.block}</Badge><span className="num text-danger">{d.mean_effect.toFixed(3)}</span></span>
                    </div>
                  ))}
                  {!(abm.top_drivers_against_you || []).length && <p className="text-xs text-ink-400">No lost agents in range to analyse.</p>}
                </div>
              </Card>
              <Card className="p-4">
                <CardHeader title="How the 615 parameters reach decisions" subtitle="Every parameter is consumed by the model — audited in the test suite" />
                <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                  {Object.entries(abm.genome.audit).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-2"><span className="truncate text-ink-400" title={k}>{k}</span><span className="num text-ink-200">{v}</span></div>
                  ))}
                </div>
              </Card>
              {abm.calibration && (
                <Card className="p-4 text-xs">
                  <CardHeader title="Calibration against incumbents" subtitle={abm.calibration.method} right={<Badge tone={abm.calibration.applied ? "warn" : "ok"}>{abm.calibration.applied ? `participation ×${abm.calibration.multiplier}` : "no change"}</Badge>} />
                  <p className="mt-2 text-ink-300">{abm.calibration.reason}.</p>
                  {abm.calibration.median_incumbent_units !== undefined && (
                    <p className="mt-1 text-ink-500">Median nearby incumbent: {num(abm.calibration.median_incumbent_units)} units/month modeled vs survival floor {num(abm.calibration.survival_floor_units)} ({abm.calibration.incumbents_used} incumbents in the inner catchment). Businesses that exist need customers; if the model starves them, it is under-counting demand.</p>
                  )}
                </Card>
              )}
            </div>
          </div>

          <Card className="p-4">
            <CardHeader
              title="Get real feedback: field survey kit"
              subtitle="Synthetic agents are not real customers. This questionnaire measures exactly the assumptions this result is most sensitive to."
              right={!kit && <Button variant="primary" size="sm" onClick={loadKit} loading={kitLoading}><Sparkles className="h-3.5 w-3.5" /> Generate survey</Button>}
            />
            {kit && (
              <div className="mt-3 space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="accent">{kit.questions.length} questions</Badge>
                  <Badge>Sample {kit.sample_size.recommended} (min {kit.sample_size.minimum})</Badge>
                  <Badge>{kit.sample_size.margin_of_error_at_100}</Badge>
                  {kit.focus.weakest_channels_vs_competitors.map((c) => <Badge key={c} tone="warn">weak: {CHANNEL_LABEL[c] || c}</Badge>)}
                  <div className="ml-auto flex gap-2">
                    <Button size="sm" onClick={() => { navigator.clipboard?.writeText(kitText(kit)); setCopied(true); setTimeout(() => setCopied(false), 1500); }}><ClipboardCopy className="h-3.5 w-3.5" /> {copied ? "Copied" : "Copy as text"}</Button>
                    <Button size="sm" onClick={() => window.print()}><Printer className="h-3.5 w-3.5" /> Print</Button>
                    <Button size="sm" variant="ghost" onClick={() => setKit(null)} aria-label="Close survey"><X className="h-3.5 w-3.5" /></Button>
                  </div>
                </div>
                <ol className="grid gap-2 md:grid-cols-2">
                  {kit.questions.map((q, i) => (
                    <li key={q.id} className="rounded-md border border-white/[0.06] bg-ink-900 p-3 text-xs">
                      <div className="text-[10px] text-ink-500">{q.section}</div>
                      <div className="mt-0.5 text-ink-100">{i + 1}. {q.text}</div>
                      {q.options && <div className="mt-1 flex flex-wrap gap-1">{q.options.map((o) => <span key={o} className="rounded border border-white/[0.07] px-1.5 py-0.5 text-[10px] text-ink-300">{o}</span>)}</div>}
                      <div className="mt-1.5 text-[10px] text-ink-500">Why: {q.why}</div>
                      <div className="mt-0.5 text-[10px] text-ink-600">Replaces: {q.measures.join(", ")}</div>
                    </li>
                  ))}
                </ol>
                <p className="text-[11px] text-ink-400">{kit.sample_size.how} {kit.note}</p>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
