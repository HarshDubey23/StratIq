"use client";

import { ArrowRight, Check, Copy, ExternalLink, Home, MapPin, RefreshCw, Trash2, UserRoundCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { FieldRecorder, KIND_META, type RecordDraft } from "@/components/field/FieldRecorder";
import { useProject } from "@/components/ProjectContext";
import { Button, Card, CardHeader, cn, ErrorState, Evidence, inputCls, Skeleton, Textarea } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { ago, money, num, pct } from "@/lib/format";
import type { FieldPayload, FieldStatus, Run } from "@/lib/types";

const PARAM_LABEL: Record<string, { t: string; fmt: (v: number) => string; d: string }> = {
  participation: { t: "People who use the category", fmt: (v) => pct(v, 1), d: "Share of interviewees who already buy this. Sets how many agents are in the market." },
  frequency: { t: "Visits per month", fmt: (v) => num(v, 1), d: "How often a customer comes back. Multiplies every agent's purchases." },
  max_km: { t: "How far people travel", fmt: (v) => `${num(v, 1)} km`, d: "Agents beyond this distance do not consider the business." },
  wtp_sigma: { t: "Spread of price tolerance", fmt: (v) => num(v, 2), d: "How different people's maximum prices are. Wider = more bargain hunters and more premium buyers." },
};

const STAGES: { s: FieldStatus; t: string }[] = [
  { s: "requested", t: "Requested" },
  { s: "in_field", t: "On the street" },
  { s: "submitted", t: "Data submitted" },
];

export default function FieldResearch() {
  const { project: p, reload } = useProject();
  const router = useRouter();
  const [f, setF] = useState<FieldPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [due, setDue] = useState("");
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState<null | "req" | "run" | "rent" | "status">(null);
  const [copied, setCopied] = useState(false);
  const [origin, setOrigin] = useState("");

  const load = useCallback(async () => {
    try {
      setF(await api<FieldPayload>(`/projects/${p.id}/field`));
      setErr(null);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not load field research");
    }
  }, [p.id]);
  useEffect(() => {
    void load();
    setOrigin(window.location.origin);
  }, [load]);

  const loc = p.locations[0];
  const baseline = p.scenarios?.find((s) => s.is_baseline);
  const link = f?.request?.token ? `${origin}/field/${f.request.token}` : "";
  const counts = f?.summary.counts || {};
  const params = Object.entries(f?.summary.params || {});

  async function requestResearcher() {
    setBusy("req");
    try {
      setF(await api<FieldPayload>(`/projects/${p.id}/field/request`, { method: "POST", json: { researcher_name: name, brief, due_date: due || null } }));
      await reload();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not create the request");
    } finally {
      setBusy(null);
    }
  }
  async function setStatus(status: FieldStatus) {
    setBusy("status");
    try {
      setF(await api<FieldPayload>(`/projects/${p.id}/field/request`, { method: "PATCH", json: { status } }));
      await reload();
    } finally {
      setBusy(null);
    }
  }
  async function save(d: RecordDraft) {
    await api(`/projects/${p.id}/field/records`, { method: "POST", json: d });
    await load();
    await reload();
  }
  async function remove(id: string) {
    await api(`/projects/${p.id}/field/records/${id}`, { method: "DELETE" });
    await load();
    await reload();
  }
  async function rerun() {
    if (!baseline) return;
    setBusy("run");
    try {
      const r = await api<Run>(`/scenarios/${baseline.id}/runs`, { method: "POST" });
      if (r.status !== "succeeded") throw new ApiError(500, r.error || "The simulation failed");
      await reload();
      router.push(`/app/projects/${p.id}/live`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not run the simulation");
      setBusy(null);
    }
  }
  async function applyRent(v: number) {
    if (!baseline) return;
    setBusy("rent");
    try {
      await api(`/scenarios/${baseline.id}`, { method: "PATCH", json: { inputs: { ...baseline.inputs, rent: Math.round(v) } } });
      await reload();
    } finally {
      setBusy(null);
    }
  }

  if (err && !f) return <main className="p-6"><ErrorState message={err} onRetry={load} /></main>;
  if (!f) return <main className="space-y-3 p-6"><Skeleton className="h-40" /><Skeleton className="h-72" /></main>;

  const stageIdx = f.request ? STAGES.findIndex((x) => x.s === f.request!.status) : -1;
  const total = f.records.length;

  return (
    <main className="mx-auto w-full max-w-7xl p-4 md:p-8">
      <header className="rise grid gap-6 md:grid-cols-[1fr_auto] md:items-end">
        <div>
          <p className="idx">02/ GROUND TRUTH</p>
          <h2 className="font-display mt-2 text-[clamp(1.8rem,3.4vw,2.8rem)] font-medium leading-[1] tracking-[-0.04em]">Field research</h2>
          <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-ink-300">
            Maps miss informal shops, real prices and how people actually behave. A researcher from the {p.category.label.toLowerCase()} industry walks the
            street, records what is true, and the 10,000 agents are re-run on that data.
          </p>
        </div>
        <div className="flex items-center gap-6">
          <Stat n={counts.interview ?? 0} l="interviews" />
          <Stat n={counts.competitor ?? 0} l="shops visited" />
          <Stat n={params.length} l="agent inputs from field" accent />
        </div>
      </header>

      {err && <div className="mt-4"><ErrorState message={err} /></div>}

      <div className="mt-8 grid gap-5 lg:grid-cols-[1.45fr_1fr]">
        <div className="space-y-5">
          {/* ---------- request / assignment ---------- */}
          {!f.request || f.request.status === "closed" ? (
            <Card className="rise rise-1 overflow-hidden">
              <div className="relative border-b border-white/[0.06] p-6">
                <div aria-hidden className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-field/10 blur-3xl" />
                <span className="inline-flex items-center gap-2 rounded-md border border-field/40 bg-field/10 px-2 py-1 text-[11px] font-medium text-field">
                  <UserRoundCheck className="h-3.5 w-3.5" /> Matched specialty
                </span>
                <h3 className="font-display mt-3 text-2xl font-medium tracking-tight">Send a {f.specialty.toLowerCase()} to {loc?.address?.split(",")[0] || "your site"}</h3>
                <p className="mt-2 max-w-xl text-sm text-ink-300">They get a link that opens a field app on their phone — no login. Everything they record lands here and in the simulation.</p>
              </div>
              <ol className="grid gap-px bg-white/[0.06] sm:grid-cols-2">
                {f.checklist.map((t, i) => (
                  <li key={t.kind} className="bg-ink-900 p-5">
                    <div className="flex items-center gap-2">
                      <span className="idx">0{i + 1}</span>
                      <KindIcon kind={t.kind} />
                      <span className="text-sm font-medium">{t.title}</span>
                      <span className="num ml-auto font-mono text-[11px] text-ink-500">target {t.target}</span>
                    </div>
                    <p className="mt-2 text-[13px] leading-relaxed text-ink-400">{t.how}</p>
                  </li>
                ))}
              </ol>
              <div className="grid gap-3 p-6 sm:grid-cols-2">
                <label className="space-y-1.5 text-xs text-ink-300">Researcher name <span className="text-ink-500">(optional)</span>
                  <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Assigned by StrataIQ if empty" maxLength={120} />
                </label>
                <label className="space-y-1.5 text-xs text-ink-300">Needed by
                  <input type="date" className={inputCls} value={due} onChange={(e) => setDue(e.target.value)} />
                </label>
                <label className="space-y-1.5 text-xs text-ink-300 sm:col-span-2">Anything specific to check?
                  <Textarea value={brief} onChange={(e) => setBrief(e.target.value)} placeholder="e.g. Are there unlisted gyms above the shops on the main road? What do they charge?" maxLength={2000} />
                </label>
                <Button variant="primary" size="lg" className="sm:col-span-2" onClick={requestResearcher} loading={busy === "req"}>
                  Request field researcher <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </Card>
          ) : (
            <Card className="rise rise-1">
              <div className="flex flex-wrap items-start justify-between gap-4 p-6">
                <div>
                  <p className="idx">ASSIGNMENT</p>
                  <h3 className="font-display mt-1.5 text-xl font-medium tracking-tight">{f.request.researcher_name || "Field researcher"} · <span className="text-ink-300">{f.request.specialty}</span></h3>
                  <p className="mt-1 text-xs text-ink-400">Requested {ago(f.request.created_at)}{f.request.due_date ? ` · needed by ${f.request.due_date}` : ""}</p>
                </div>
                <div className="flex items-center gap-2">
                  {f.request.status !== "submitted" ? (
                    <Button size="sm" onClick={() => setStatus("submitted")} loading={busy === "status"}><Check className="h-3.5 w-3.5" /> Mark data complete</Button>
                  ) : (
                    <Button size="sm" variant="ghost" onClick={() => setStatus("in_field")} loading={busy === "status"}>Reopen</Button>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 px-6 pb-5">
                {STAGES.map((s, i) => (
                  <div key={s.s} className="flex flex-1 items-center gap-2">
                    <span className={cn("flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[11px] font-medium", i <= stageIdx ? "bg-field text-ink-950" : "bg-white/[0.06] text-ink-500")}>
                      {i < stageIdx ? <Check className="h-3.5 w-3.5" /> : i + 1}
                    </span>
                    <span className={cn("text-xs", i <= stageIdx ? "text-ink-100" : "text-ink-500")}>{s.t}</span>
                    {i < STAGES.length - 1 && <span className={cn("h-px flex-1", i < stageIdx ? "bg-field/60" : "bg-white/10")} />}
                  </div>
                ))}
              </div>
              <div className="border-t border-white/[0.06] p-6">
                <p className="text-xs text-ink-400">Researcher&apos;s field link — send it on WhatsApp. It only lets them add data to this project.</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <code className="num min-w-0 flex-1 truncate rounded-lg border border-white/10 bg-ink-950 px-3 py-2.5 font-mono text-[12px] text-ink-200">{link}</code>
                  <Button size="md" onClick={() => { void navigator.clipboard?.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 1800); }}>
                    {copied ? <Check className="h-4 w-4 text-field" /> : <Copy className="h-4 w-4" />} {copied ? "Copied" : "Copy"}
                  </Button>
                  <a href={link} target="_blank" rel="noreferrer" className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-white/10 px-3 text-sm text-ink-200 hover:border-white/25">
                    <ExternalLink className="h-4 w-4" /> Open field app
                  </a>
                </div>
              </div>
            </Card>
          )}

          {/* ---------- progress ---------- */}
          <Card className="rise rise-2">
            <CardHeader title="Collection progress" subtitle={total ? `${total} records saved` : "Nothing collected yet"} />
            <div className="grid gap-4 p-5 sm:grid-cols-2">
              {f.checklist.map((t) => {
                const n = counts[t.kind] ?? 0;
                const done = n >= t.target;
                return (
                  <div key={t.kind}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="flex items-center gap-2"><KindIcon kind={t.kind} /> {t.title}</span>
                      <span className="num font-mono text-xs text-ink-300">{n}/{t.target}</span>
                    </div>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                      <div className={cn("h-full rounded-full transition-[width] duration-700", done ? "bg-field" : "bg-accent")} style={{ width: `${Math.min(100, (n / t.target) * 100)}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* ---------- what the agents now use ---------- */}
          <Card className="rise rise-3">
            <CardHeader
              title="What the agents now use from the street"
              subtitle="Field data replaces the model's assumption once there are enough answers. Your own overrides still win."
              right={<Evidence kind="field" />}
            />
            {params.length === 0 ? (
              <div className="p-5 text-sm text-ink-400">
                {f.summary.interviews.n > 0
                  ? `${f.summary.interviews.n} interview${f.summary.interviews.n === 1 ? "" : "s"} so far — at least ${f.checklist[0]?.min ?? 8} are needed before the agents switch to field data.`
                  : "No interviews yet. Once the researcher saves 8 or more, these agent inputs switch from assumptions to street data."}
              </div>
            ) : (
              <ul className="divide-y divide-white/[0.06]">
                {params.map(([k, v]) => {
                  const L = PARAM_LABEL[k];
                  const def = p.archetype?.params[k];
                  return (
                    <li key={k} className="grid grid-cols-[1fr_auto] items-center gap-3 px-5 py-3.5">
                      <div className="min-w-0">
                        <div className="text-sm font-medium">{L?.t || k}</div>
                        <div className="mt-0.5 text-xs text-ink-400">{L?.d}</div>
                      </div>
                      <div className="text-right">
                        <div className="num font-display text-lg font-medium text-field">{L ? L.fmt(v.value) : num(v.value, 2)}</div>
                        <div className="num text-[11px] text-ink-500">
                          {L ? `${L.fmt(v.low)}–${L.fmt(v.high)}` : ""}{def ? ` · was ${L ? L.fmt(def.value) : def.value}` : ""}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="flex flex-wrap items-center gap-3 border-t border-white/[0.06] p-5">
              <Button variant="primary" onClick={rerun} loading={busy === "run"} disabled={!baseline || total === 0}>
                <RefreshCw className="h-4 w-4" /> Re-run agents with field data
              </Button>
              {f.summary.rent && baseline && (
                <Button onClick={() => applyRent(f.summary.rent!.median)} loading={busy === "rent"} disabled={baseline.inputs.rent === Math.round(f.summary.rent.median)}>
                  <Home className="h-4 w-4" /> {baseline.inputs.rent === Math.round(f.summary.rent.median) ? "Field rent in use" : `Use field rent ${money(f.summary.rent.median)}/mo`}
                </Button>
              )}
              {f.summary.footfall && <span className="text-xs text-ink-400">Footfall ≈ <b className="num text-ink-200">{num(f.summary.footfall.people_per_hour)}</b> people/hour at the site</span>}
            </div>
            {f.summary.notes.length > 0 && <p className="border-t border-white/[0.06] px-5 py-3 text-[11.5px] leading-relaxed text-ink-500">{f.summary.notes.join(" ")}</p>}
          </Card>

          {/* ---------- records ---------- */}
          {total > 0 && (
            <Card>
              <CardHeader title="Everything collected" subtitle="Newest first. Deleting a competitor visit also removes it from the map." />
              <ul className="max-h-[420px] divide-y divide-white/[0.05] overflow-y-auto">
                {[...f.records].reverse().map((r) => (
                  <li key={r.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                    <KindIcon kind={r.kind} />
                    <span className="min-w-0 flex-1 truncate text-ink-200">{describe(r.kind, r.data)}</span>
                    <span className="hidden text-xs text-ink-500 sm:inline">{r.collected_by} · {ago(r.created_at)}</span>
                    <button onClick={() => remove(r.id)} aria-label="Delete record" className="rounded-md p-1.5 text-ink-500 hover:bg-white/5 hover:text-red-300"><Trash2 className="h-3.5 w-3.5" /></button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        {/* ---------- record yourself ---------- */}
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <Card className="rise rise-2 p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="idx">RECORD</p>
                <h3 className="font-display mt-1 text-lg font-medium tracking-tight">Add ground data yourself</h3>
              </div>
              {loc && <Link href={`/app/projects/${p.id}/market`} className="inline-flex items-center gap-1 text-xs text-ink-400 hover:text-ink-100"><MapPin className="h-3.5 w-3.5" /> map</Link>}
            </div>
            <FieldRecorder category={p.category.label} priceLabel={p.archetype?.price_label || "Price"} site={loc ? { lat: loc.lat, lng: loc.lng } : null} counts={counts} onSave={save} who="Owner" />
          </Card>
        </aside>
      </div>
    </main>
  );
}

function Stat({ n, l, accent }: { n: number; l: string; accent?: boolean }) {
  return (
    <div>
      <div className={cn("num font-display text-3xl font-medium tracking-tight", accent && "text-field")}>{n}</div>
      <div className="text-[11px] text-ink-400">{l}</div>
    </div>
  );
}

function KindIcon({ kind }: { kind: keyof typeof KIND_META }) {
  const M = KIND_META[kind];
  return <M.icon className={cn("h-4 w-4 shrink-0", M.tint)} />;
}

function describe(kind: string, d: Record<string, unknown>): string {
  const n = (x: unknown) => (typeof x === "number" ? x : null);
  if (kind === "interview") {
    const parts = [d.uses_category ? "Uses it" : "Doesn't use it"];
    if (n(d.visits_per_month)) parts.push(`${d.visits_per_month}×/mo`);
    if (n(d.travel_km)) parts.push(`${d.travel_km} km`);
    if (n(d.max_price)) parts.push(`max ${money(d.max_price as number)}`);
    return parts.join(" · ");
  }
  if (kind === "competitor") return `${d.name}${n(d.price) ? ` · ${money(d.price as number)}` : ""}${n(d.quality) ? ` · ${d.quality}/5` : ""}`;
  if (kind === "footfall") return `${d.count} people in ${d.minutes} min · ${d.time_of_day}${d.weekend ? " · weekend" : ""}`;
  if (kind === "rent") return `${money(d.monthly_rent as number)}/mo${n(d.deposit) ? ` · deposit ${money(d.deposit as number)}` : ""}`;
  return kind;
}

