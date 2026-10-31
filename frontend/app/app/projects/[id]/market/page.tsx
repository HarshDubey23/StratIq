"use client";

import { Building2, ExternalLink, Layers, MapPinPlus, Plus, RefreshCw, Trash2, Users } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { publishScreen } from "@/lib/screen";
import { BestSites, toOpportunity, type SitesOut } from "@/components/BestSites";
import { LocationPicker, type PickedPlace } from "@/components/LocationPicker";
import { Map as MarketMap, } from "@/components/Map";
import type { LayerKey } from "@/components/MapView";
import { useProject } from "@/components/ProjectContext";
import { Badge, Button, cn, Dialog, EmptyState, ErrorState, Evidence, Field, Input, Notice, NumberInput, Segmented, Select, Spinner } from "@/components/ui";
import { IncomeMix } from "@/components/RealData";
import { api, ApiError } from "@/lib/api";
import { ago, money, num, pct, when } from "@/lib/format";
import { refreshLocation, waitForSnapshot } from "@/lib/market";
import type { CompetitorRec, MarketData, Run, SimResult } from "@/lib/types";

type Tab = "evidence" | "competitors" | "locations" | "sites";

export default function MarketPage() {
  const { project: p, reload } = useProject();
  const [locId, setLocId] = useState(p.locations[0]?.id);
  const [data, setData] = useState<MarketData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<Tab>("evidence");
  const [sites, setSites] = useState<SitesOut | null>(null);
  const [focus, setFocus] = useState<{ lat: number; lng: number; key: string } | null>(null);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("tab") === "sites") setTab("sites");
    const h = () => setTab("sites");
    window.addEventListener("strataiq:sites", h);
    return () => window.removeEventListener("strataiq:sites", h);
  }, []);
  const [sel, setSel] = useState<string | null>(null);
  const [addMode, setAddMode] = useState(false);
  const [draft, setDraft] = useState<{ lat: number; lng: number } | null>(null);
  const [layersOpen, setLayersOpen] = useState(false);
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>({ catchment: true, zones: true, competitors: true, agents: false, activity: false, buildings3d: true });
  const [baseResult, setBaseResult] = useState<SimResult | null>(null);
  const [dirty, setDirty] = useState(false);
  const [rerun, setRerun] = useState<{ before: SimResult | null; after: SimResult } | null>(null);
  const [rerunning, setRerunning] = useState(false);

  const baseline = p.scenarios?.find((s) => s.is_baseline);

  const load = useCallback(async () => {
    if (!locId) return;
    setLoading(true);
    try {
      setData(await api<MarketData>(`/projects/${p.id}/market?location_id=${locId}`));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load market");
    } finally {
      setLoading(false);
    }
  }, [p.id, locId]);
  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const rid = baseline?.latest_run?.id;
    if (!rid) return setBaseResult(null);
    api<Run>(`/simulation-runs/${rid}/results`).then((r) => setBaseResult(r.results || null)).catch(() => setBaseResult(null));
  }, [baseline?.latest_run?.id]);

  const [elapsed, setElapsed] = useState(0);
  const [autoRunning, setAutoRunning] = useState(false);
  const [liveReady, setLiveReady] = useState(false);

  const finishJob = useCallback(
    async (job: Promise<{ status: string; errors: { source: string; message: string }[] }>) => {
      setRefreshing(true);
      setError(null);
      setElapsed(0);
      try {
        const s = await job;
        if (s.status === "failed") setError(`Market data could not be loaded: ${s.errors.map((e) => e.message).join("; ") || "unknown error"}`);
        await load();
        await reload();
        setDirty(true);
        // First load for a new project: run the baseline straight away so the live market is ready.
        if (s.status !== "failed" && baseline && !baseline.latest_run) {
          setAutoRunning(true);
          try {
            const r = await api<Run>(`/scenarios/${baseline.id}/runs`, { method: "POST" });
            setBaseResult(r.results || null);
            setDirty(false);
            setLiveReady(true);
            await reload();
          } catch {
            /* the lab shows the reason */
          } finally {
            setAutoRunning(false);
          }
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Refresh failed");
      } finally {
        setRefreshing(false);
      }
    },
    [load, reload, baseline],
  );

  async function refresh() {
    if (!locId) return;
    await finishJob(refreshLocation(p.id, locId, setElapsed));
  }

  // A load started elsewhere (e.g. right after the wizard) is still running: follow it.
  const pendingId = data?.loading_snapshot_id;
  useEffect(() => {
    if (pendingId && !refreshing) finishJob(waitForSnapshot(p.id, pendingId, setElapsed));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingId]);

  async function rerunBaseline() {
    if (!baseline) return;
    setRerunning(true);
    try {
      const r = await api<Run>(`/scenarios/${baseline.id}/runs`, { method: "POST" });
      setRerun({ before: baseResult, after: r.results! });
      setBaseResult(r.results!);
      setDirty(false);
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Simulation failed");
    } finally {
      setRerunning(false);
    }
  }

  const snap = data?.snapshot;
  const comps = data?.competitors || [];
  const selected = comps.find((c) => c.id === sel) || null;
  const modelComp = baseResult?.competitors.find((c) => c.id === sel);
  const loc = data?.location;
  const center: [number, number] = loc ? [loc.lng, loc.lat] : [78.96, 22.59];

  const mapComps = useMemo(
    () => comps.map((c) => ({ id: c.id, name: c.name, lat: c.lat, lng: c.lng, kind: (c.source === "user" ? (c.is_hypothetical ? "hypothetical" : "user") : c.source === "foursquare" ? "fsq" : c.source) as "osm" | "fsq" | "user" | "hypothetical" | "demo" | "field", inactive: !c.active })),
    [comps],
  );
  const zones = useMemo(() => (snap?.zones || []).map((z) => ({ lat: z.lat, lng: z.lng, value: z.population })), [snap]);
  const compWeight = useMemo(() => Object.fromEntries((baseResult?.competitors || []).map((c) => [c.id, c.modeled_units])), [baseResult]);
  useEffect(() => {
    if (!snap) return;
    const top = [...(baseResult?.competitors || [])].sort((x, y) => y.modeled_units - x.modeled_units).slice(0, 3);
    publishScreen({
      page: "market", project_id: p.id, scenario_id: p.scenarios?.find((s) => s.is_baseline)?.id || null,
      competitors: comps.filter((c) => c.active).length, population: snap.population?.total ?? null,
      population_source: snap.population?.source ?? null,
      selected_competitor: selected ? selected.name : null,
      selected_competitor_modeled_units: modelComp ? Math.round(modelComp.modeled_units) : null,
      strongest_competitors: top.map((c) => ({ name: c.name, modeled_units: Math.round(c.modeled_units) })),
      layers,
    });
  }, [snap, comps, selected, modelComp, baseResult, layers, p.id, p.scenarios]);

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <section className="relative h-[55vh] min-h-[380px] flex-1 lg:h-auto">
        <MarketMap
          fill
          center={center}
          catchment={snap?.catchment_geojson || null}
          zones={zones}
          competitors={mapComps}
          candidates={(data?.locations || []).map((l) => ({ id: l.id, label: l.label, lat: l.lat, lng: l.lng, active: l.id === locId }))}
          activity={snap?.activity_points}
          agents={baseResult?.agents.rows}
          layers={layers}
          selectedCompetitorId={sel}
          onCompetitorClick={(id) => {
            setSel(id);
            setTab("competitors");
          }}
          onCandidateClick={(id) => setLocId(id)}
          onMapClick={(lat, lng) => addMode && setDraft({ lat, lng })}
          crosshair={addMode}
          fitKey={`${locId}-${snap?.id || "none"}`}
          zoneSpacingKm={snap?.population?.spacing_km}
          competitorWeight={compWeight}
          opportunity={tab === "sites" && sites ? toOpportunity(sites) : null}
          onOpportunityClick={(o) => setFocus({ lat: o.lat, lng: o.lng, key: `${o.lat},${o.lng},${Date.now()}` })}
          focus={focus}
        />
        <div className="absolute left-3 top-3 z-10 flex flex-wrap items-center gap-2">
          <Select value={locId} onChange={(e) => setLocId(e.target.value)} className="panel h-8 w-auto text-xs" aria-label="Location">
            {p.locations.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
          </Select>
          <Button size="sm" onClick={refresh} loading={refreshing} className="panel">
            <RefreshCw className="h-3.5 w-3.5" /> {snap ? "Refresh live data" : "Load live data"}
          </Button>
          <Button size="sm" variant={addMode ? "primary" : "secondary"} onClick={() => setAddMode((x) => !x)} className={addMode ? "" : "panel"}>
            <MapPinPlus className="h-3.5 w-3.5" /> {addMode ? "Click the map to place it" : "Add competitor"}
          </Button>
        </div>
        <div className={cn("panel absolute bottom-8 left-3 z-10 rounded-xl text-xs transition-[width] duration-300", layersOpen ? "w-56 p-3" : "w-auto p-0")}>
          <button
            onClick={() => setLayersOpen((x) => !x)}
            aria-expanded={layersOpen}
            className={cn("flex items-center gap-1.5 font-medium text-ink-200", layersOpen ? "mb-1.5" : "h-9 px-3")}
          >
            <Layers className="h-3.5 w-3.5" /> Layers
          </button>
          {layersOpen && (
            [
              ["catchment", "Catchment", "border-accent"],
              ["zones", "Population zones", "bg-[#6E5BFF]"],
              ["competitors", "Competitors", "bg-observed"],
              ["agents", "Synthetic customers", "bg-agent"],
              ["activity", "Activity points", "bg-assumption"],
              ["buildings3d", "3D buildings (OSM)", "bg-ink-500"],
            ] as [LayerKey, string, string][]
          ).map(([k, l, c]) => (
            <label key={k} className="flex cursor-pointer items-center gap-2 py-0.5 text-ink-300">
              <input type="checkbox" checked={layers[k]} onChange={(e) => setLayers({ ...layers, [k]: e.target.checked })} disabled={k === "agents" && !baseResult} />
              <span className={cn("h-2 w-2 rounded-full", c.startsWith("border") ? `border ${c}` : c)} />
              {l}
              {k === "agents" && !baseResult && <span className="text-ink-500">(run first)</span>}
            </label>
          ))}
          {layersOpen && (
            <div className="mt-1.5 border-t border-black/[0.07] pt-1.5 text-[10px] leading-snug text-ink-500">
              Purple = user-entered competitors; white ring = hypothetical. Building heights are shown only where mapped in OSM.
            </div>
          )}
        </div>
        {loading && !refreshing && <div className="absolute right-14 top-3 z-10 rounded bg-ink-900/90 px-2 py-1"><Spinner label="Loading" /></div>}
        {(autoRunning || liveReady) && (
          <div className="absolute inset-x-0 bottom-24 z-10 mx-auto w-fit rounded-md border border-accent/50 bg-ink-900/95 px-4 py-3 text-sm shadow-xl">
            {autoRunning ? (
              <Spinner label="Simulating thousands of synthetic customers at real density…" />
            ) : (
              <div className="flex items-center gap-3">
                <span>Baseline simulated.</span>
                <Link href={`/app/projects/${p.id}/live`} className="rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white">Watch the live market →</Link>
                <button onClick={() => setLiveReady(false)} className="text-xs text-ink-400">dismiss</button>
              </div>
            )}
          </div>
        )}
        {refreshing && (
          <div className="absolute inset-x-0 top-14 z-10 mx-auto w-fit max-w-md rounded-md border border-accent/40 bg-ink-900/95 px-4 py-3 text-sm shadow-xl">
            <Spinner label={`Loading live data from OpenStreetMap and WorldPop… ${elapsed}s`} />
            <p className="mt-1 text-xs text-ink-400">Competitors, buildings and population for the catchment. Public services can take up to a minute.</p>
          </div>
        )}
      </section>

      <aside className="flex w-full flex-col border-l border-black/[0.06] bg-ink-950/80 backdrop-blur-xl lg:w-[400px]">
        <div className="flex gap-1 border-b border-black/[0.06] p-2">
          {(["evidence", "competitors", "sites", "locations"] as Tab[]).map((t) => (
            <button key={t} onClick={() => setTab(t)} data-tour={t === "sites" ? "best-sites" : undefined}
              className={cn("flex-1 rounded px-2 py-1.5 text-xs capitalize", tab === t ? "bg-ink-800 text-ink-100" : t === "sites" ? "text-model hover:text-ink-100" : "text-ink-400 hover:text-ink-100")}>
              {t === "competitors" ? `Competitors (${comps.filter((c) => c.active).length})` : t === "sites" ? "Best sites" : t}
            </button>
          ))}
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-4 lg:max-h-[calc(100vh-112px)]">
          {error && <ErrorState message={error} onRetry={load} />}
          {(dirty || rerun) && baseline && (
            <div className="rounded-md border border-accent/40 bg-accent/5 p-3 text-sm">
              {dirty ? (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-ink-200">Market evidence changed. Re-run the model to see the effect.</span>
                  <Button size="sm" variant="primary" onClick={rerunBaseline} loading={rerunning}>Rerun baseline</Button>
                </div>
              ) : rerun && (
                <div>
                  <div className="mb-2 text-xs font-medium text-ink-200">Baseline re-simulated with the updated market</div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <div className="text-ink-400">{rerun.after.unit_label}</div>
                      <div className="num">{num(rerun.before?.summary.units_sold)} → <span className="text-ink-100">{num(rerun.after.summary.units_sold)}</span></div>
                    </div>
                    <div>
                      <div className="text-ink-400">Op. profit / month</div>
                      <div className="num">{money(rerun.before?.finance.operating_profit, { compact: true })} → <span className="text-ink-100">{money(rerun.after.finance.operating_profit, { compact: true })}</span></div>
                    </div>
                  </div>
                  <Evidence kind="model" className="mt-2" />
                </div>
              )}
            </div>
          )}

          {tab === "evidence" && (
            <>
              {!snap && !loading && !refreshing && (
                <EmptyState
                  icon={<Building2 className="h-6 w-6" />}
                  title="No market data loaded for this location"
                  body="Load live competitors, buildings and population for the catchment. This calls OpenStreetMap and WorldPop and can take up to a minute."
                  action={<Button variant="primary" onClick={refresh} loading={refreshing}>Load live data</Button>}
                />
              )}
              {snap && (
                <>
                  <div className="flex items-center justify-between">
                    <div className="text-xs text-ink-400">Snapshot captured {when(snap.retrieved_at)}</div>
                    <Badge tone={snap.status === "complete" ? "ok" : snap.status === "partial" ? "warn" : "danger"}>{snap.status}</Badge>
                  </div>
                  {p.is_demo && <Notice tone="warn">This is the demo dataset. Population and competitors are synthetic and illustrative.</Notice>}
                  {snap.errors.map((e, i) => (
                    <Notice key={i} tone="warn">
                      <b className="capitalize">{e.source}</b>: {e.message}
                      {e.fallback && <> — fell back to <b>{e.fallback}</b>.</>}
                    </Notice>
                  ))}
                  <div className="rounded-md border border-black/[0.07] p-3">
                    <div className="mb-2 flex items-center justify-between text-xs">
                      <span className="font-medium text-ink-200">Catchment population</span>
                      <Evidence kind={snap.population.source === "user" ? "user" : snap.population.source === "worldpop" ? "official" : snap.population.source === "demo" ? "demo" : snap.population.source === "estimate_buildings" ? "assumption" : "unknown"} label={snap.population.source === "estimate_buildings" ? "Rough estimate" : undefined} />
                    </div>
                    {snap.population.total ? (
                      <>
                        <div className="num text-2xl font-semibold">{num(snap.population.total)}</div>
                        <div className="mt-1 text-xs text-ink-400">
                          {snap.catchment_method === "isochrone" ? "Travel-time catchment" : `${snap.population.radius_km?.toFixed(1)} km radius (straight-line)`} · {snap.population.zones} zones of ~{num((snap.population.spacing_km || 0) * 1000)} m ·{" "}
                          {snap.population.method === "dasymetric_buildings" ? `placed using ${num(snap.population.buildings_used)} mapped buildings` : snap.population.method === "uniform" ? "spread evenly (few buildings mapped)" : snap.population.method}
                        </div>
                        {snap.population.source === "estimate_buildings" && <div className="mt-3"><PopulationFallback projectId={p.id} locationId={locId!} onSaved={refresh} /></div>}
                      </>
                    ) : (
                      <PopulationFallback projectId={p.id} locationId={locId!} onSaved={refresh} />
                    )}
                  </div>
                  {data?.income && <IncomeMix income={data.income} />}
                  <div className="rounded-md border border-black/[0.07] p-3">
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="font-medium text-ink-200">Data coverage</span>
                      <Badge tone={snap.coverage.level === "good" ? "ok" : snap.coverage.level === "partial" ? "warn" : "danger"}>{snap.coverage.level}</Badge>
                    </div>
                    <p className="text-xs text-ink-300">{snap.coverage.note}</p>
                    <ul className="mt-2 space-y-1">
                      {snap.coverage.signals.map((s) => (
                        <li key={s.signal} className="flex justify-between gap-2 text-xs" title={s.why}>
                          <span className="text-ink-400">{s.signal}</span>
                          <span className="num text-ink-200">{num(s.value, 2)}</span>
                        </li>
                      ))}
                    </ul>
                    <p className="mt-2 text-[10px] text-ink-500">{snap.coverage.method}</p>
                    {snap.coverage.level !== "good" && (
                      <Link href={`/app/projects/${p.id}/field`} className="mt-3 flex items-center justify-between rounded-md border border-field/40 bg-field/[0.08] px-3 py-2 text-xs text-field hover:bg-field/15">
                        Gaps here? Send a field researcher <span aria-hidden>→</span>
                      </Link>
                    )}
                  </div>
                  <div>
                    <div className="mb-2 text-xs font-medium text-ink-200">Sources</div>
                    <ul className="space-y-2">
                      {snap.sources.map((s, i) => (
                        <li key={i} className="rounded-md border border-black/[0.07] p-2.5 text-xs">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-medium text-ink-100">{s.name}</span>
                            {s.layer && <Badge>{s.layer}</Badge>}
                          </div>
                          {s.detail && <div className="mt-1 text-ink-300">{s.detail}</div>}
                          <div className="mt-1.5 grid grid-cols-2 gap-1 text-[11px]">
                            <span className="text-ink-500">Retrieved</span>
                            <span className="text-ink-300">{when(s.retrieved_at)}{s.from_cache ? " (cache)" : ""}</span>
                            <span className="text-ink-500">Source data as of</span>
                            <span className="text-ink-300">{s.source_updated_at ? (s.source_updated_at.includes("T") ? when(s.source_updated_at) : s.source_updated_at) : "not reported"}</span>
                            {s.license && <><span className="text-ink-500">License</span><span className="text-ink-300">{s.license}</span></>}
                          </div>
                          {s.coverage_note && <div className="mt-1.5 text-[11px] text-ink-400">{s.coverage_note}</div>}
                        </li>
                      ))}
                    </ul>
                  </div>
                </>
              )}
            </>
          )}

          {tab === "competitors" && (
            <>
              {selected ? (
                <CompetitorPanel
                  c={selected}
                  model={modelComp ? { units: modelComp.modeled_units, share: modelComp.modeled_share_of_in_market, price_used: modelComp.price_used, quality_used: modelComp.quality_used, unit: baseResult!.unit_label } : null}
                  projectId={p.id}
                  onBack={() => setSel(null)}
                  onChanged={async () => {
                    await load();
                    setDirty(true);
                  }}
                />
              ) : (
                <>
                  <Notice>
                    Competitors come from OpenStreetMap and Foursquare Places (a shop in both is counted once) and can still be incomplete, especially for small or informal businesses. Add any you have seen on the ground, or a hypothetical future
                    entrant, using <b>Add competitor</b> on the map.
                  </Notice>
                  {comps.length === 0 && snap && <EmptyState title="No competitors found in the data" body="This can mean an unserved market, or simply missing map data. Verify locally and add what you find." />}
                  <ul className="divide-y divide-black/[0.06] rounded-md border border-black/[0.07]">
                    {comps.map((c) => (
                      <li key={c.id}>
                        <button onClick={() => setSel(c.id)} className={cn("flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-ink-850", !c.active && "opacity-50")}>
                          <span className="min-w-0">
                            <span className="block truncate">{c.name}</span>
                            <span className="block text-[11px] text-ink-400">{num(c.distance_km, 2)} km · {c.price ? money(c.price) : "price unknown"}</span>
                          </span>
                          <Evidence kind={c.source === "user" ? "user" : c.source === "demo" ? "demo" : c.source === "field" ? "field" : "observed"} label={c.is_hypothetical ? "Hypothetical" : undefined} />
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}

          {tab === "sites" && (snap ? (
            <BestSites projectId={p.id} scenarioId={p.scenarios?.find((x) => x.is_baseline && x.location_id === locId)?.id || p.scenarios?.find((x) => x.location_id === locId)?.id}
              locationKey={`${locId}-${snap.id}-${baseResult ? "r" : "n"}`} onData={setSites} onFocus={(lat, lng) => setFocus({ lat, lng, key: `${lat},${lng},${Date.now()}` })} />
          ) : <p className="text-xs text-ink-400">Load live data first, then I can test every spot in the area.</p>)}
          {tab === "locations" && <LocationsPanel onSelect={setLocId} currentId={locId} onChanged={async () => { await reload(); await load(); }} />}
        </div>
      </aside>

      <AddCompetitorDialog
        draft={draft}
        projectId={p.id}
        onClose={() => setDraft(null)}
        onAdded={async (id) => {
          setDraft(null);
          setAddMode(false);
          await load();
          setSel(id);
          setTab("competitors");
          setDirty(true);
        }}
      />
    </div>
  );
}

function PopulationFallback({ projectId, locationId, onSaved }: { projectId: string; locationId: string; onSaved: () => void }) {
  const [pop, setPop] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-2">
      <p className="text-xs text-amber-800">Official population data could not be loaded. Retry later, or enter your best figure for the catchment (labelled as user-entered).</p>
      <div className="flex gap-2">
        <NumberInput value={pop} onChange={setPop} allowEmpty suffix="people" />
        <Button
          size="sm"
          loading={busy}
          disabled={!pop}
          onClick={async () => {
            setBusy(true);
            await api(`/projects/${projectId}/locations/${locationId}`, { method: "PATCH", json: { manual_population: pop } });
            setBusy(false);
            onSaved();
          }}
        >
          Use
        </Button>
      </div>
    </div>
  );
}

function CompetitorPanel({
  c,
  model,
  projectId,
  onBack,
  onChanged,
}: {
  c: CompetitorRec;
  model: { units: number; share: number; price_used: number; quality_used: number; unit: string } | null;
  projectId: string;
  onBack: () => void;
  onChanged: () => void;
}) {
  const [price, setPrice] = useState<number | null>(c.price);
  const [quality, setQuality] = useState<number | null>(c.quality);
  const [busy, setBusy] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  useEffect(() => {
    setPrice(c.price);
    setQuality(c.quality);
  }, [c.id, c.price, c.quality]);

  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    try {
      await api(`/projects/${projectId}/competitors/${c.id}`, { method: "PATCH", json: body });
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  const attrs = Object.entries(c.public_attributes);
  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-xs text-accent hover:underline">← All competitors</button>
      <div>
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold">{c.name}</h3>
          <Evidence kind={c.source === "user" ? "user" : c.source === "demo" ? "demo" : c.source === "field" ? "field" : "observed"} label={c.is_hypothetical ? "Hypothetical" : undefined} />
        </div>
        {!c.active && <Badge tone="warn" className="mt-1">Excluded from simulation</Badge>}
      </div>

      <section className="space-y-1.5 rounded-md border border-black/[0.07] p-3 text-xs">
        <div className="mb-1 font-medium text-ink-200">Observed information</div>
        <Row k="Location" v={`${c.lat.toFixed(5)}, ${c.lng.toFixed(5)}`} />
        <Row k="Distance from site" v={`${num(c.distance_km, 2)} km (straight line)`} />
        {c.category_tag && <Row k="Map category" v={c.category_tag} />}
        {attrs.map(([k, v]) => <Row key={k} k={k} v={v} />)}
        <Row k="Source" v={c.source === "osm" ? "OpenStreetMap" : c.source === "foursquare" ? "Foursquare Places" : c.source === "user" ? "Entered by you" : "Demo dataset"} />
        {c.source_updated_at && <Row k="Record last edited" v={when(c.source_updated_at)} />}
        {c.retrieved_at && <Row k="Retrieved" v={ago(c.retrieved_at)} />}
        {c.osm_url && (
          <a href={c.osm_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">
            View on OpenStreetMap <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </section>

      <section className="space-y-3 rounded-md border border-black/[0.07] p-3 text-xs">
        <div className="font-medium text-ink-200">Unknown unless you add it</div>
        <Field label="Price" kind={c.price ? "user" : "unknown"} hint={c.price ? undefined : "Not available in map data. The model assumes the local reference price."}>
          <div className="flex gap-2">
            <NumberInput value={price} onChange={setPrice} prefix="₹" allowEmpty placeholder="unknown" />
            <Button size="sm" loading={busy} onClick={() => patch(price ? { price } : { clear_price: true })}>Save</Button>
          </div>
        </Field>
        <Field label={`Quality / attractiveness: ${quality === null ? "unknown (model assumes 0.50)" : quality.toFixed(2)}`} kind={c.quality !== null ? "user" : "unknown"}>
          <div className="flex items-center gap-2">
            <input type="range" min={0} max={1} step={0.05} value={quality ?? 0.5} onChange={(e) => setQuality(Number(e.target.value))} className="flex-1" aria-label="Competitor quality" />
            <Button size="sm" loading={busy} onClick={() => patch(quality === null ? { clear_quality: true } : { quality })}>Save</Button>
          </div>
        </Field>
        <div className="text-ink-400">Capacity and current opening status: not available from the source.</div>
      </section>

      <section className="space-y-1.5 rounded-md border border-model/30 bg-model/5 p-3 text-xs">
        <div className="mb-1 flex items-center justify-between">
          <span className="font-medium text-ink-200">Model-derived</span>
          <Evidence kind="model" />
        </div>
        {model ? (
          <>
            <Row k={`Modeled ${model.unit} captured`} v={num(model.units)} />
            <Row k="Share of in-market demand" v={pct(model.share, 1)} />
            <Row k="Price used by model" v={money(model.price_used)} />
            <Row k="Quality used by model" v={model.quality_used.toFixed(2)} />
            <p className="pt-1 text-[11px] text-ink-400">From the latest baseline run. These are estimates under the model’s assumptions.</p>
          </>
        ) : (
          <p className="text-ink-400">Run the baseline simulation to see estimated overlap with your business.</p>
        )}
      </section>

      <div className="flex gap-2">
        <Button size="sm" onClick={() => patch({ active: !c.active })} loading={busy}>{c.active ? "Exclude from simulation" : "Include in simulation"}</Button>
        {c.source === "user" && (
          <Button size="sm" variant="danger" onClick={() => setConfirmDel(true)}><Trash2 className="h-3.5 w-3.5" /> Delete</Button>
        )}
      </div>
      <Dialog
        open={confirmDel}
        onClose={() => setConfirmDel(false)}
        title="Delete this competitor?"
        footer={<><Button onClick={() => setConfirmDel(false)}>Cancel</Button><Button variant="danger" onClick={async () => { await api(`/projects/${projectId}/competitors/${c.id}`, { method: "DELETE" }); setConfirmDel(false); onBack(); onChanged(); }}>Delete</Button></>}
      >
        “{c.name}” will be removed from this project. Re-run the simulation afterwards.
      </Dialog>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-ink-400">{k}</span>
      <span className="text-right text-ink-200">{v}</span>
    </div>
  );
}

function AddCompetitorDialog({ draft, projectId, onClose, onAdded }: { draft: { lat: number; lng: number } | null; projectId: string; onClose: () => void; onAdded: (id: string) => void }) {
  const [name, setName] = useState("");
  const [price, setPrice] = useState<number | null>(null);
  const [hyp, setHyp] = useState(false);
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (draft) {
      setName("");
      setPrice(null);
      setHyp(false);
      setNotes("");
      setErr(null);
    }
  }, [draft]);
  return (
    <Dialog
      open={!!draft}
      onClose={onClose}
      title="Add a competitor"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            loading={busy}
            disabled={!name.trim()}
            onClick={async () => {
              if (!draft) return;
              setBusy(true);
              try {
                const c = await api<CompetitorRec>(`/projects/${projectId}/competitors`, { method: "POST", json: { name: name.trim(), lat: draft.lat, lng: draft.lng, price, is_hypothetical: hyp, notes } });
                onAdded(c.id);
              } catch (e) {
                setErr(e instanceof ApiError ? e.message : "Could not add");
              } finally {
                setBusy(false);
              }
            }}
          >
            Add
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-xs text-ink-400">At {draft?.lat.toFixed(5)}, {draft?.lng.toFixed(5)}. It will be labelled as user-entered, not verified.</p>
        {err && <ErrorState message={err} />}
        <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
        <Field label="Price (if you know it)"><NumberInput value={price} onChange={setPrice} prefix="₹" allowEmpty /></Field>
        <Segmented value={hyp ? "hyp" : "obs"} onChange={(v) => setHyp(v === "hyp")} options={[{ value: "obs", label: "I saw it on the ground" }, { value: "hyp", label: "Hypothetical new entrant" }]} />
        <Field label="Notes"><Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. opened last month, small, women-only" /></Field>
      </div>
    </Dialog>
  );
}

function LocationsPanel({ currentId, onSelect, onChanged }: { currentId?: string; onSelect: (id: string) => void; onChanged: () => void }) {
  const { project: p } = useProject();
  const [adding, setAdding] = useState(false);
  const [place, setPlace] = useState<PickedPlace | null>(null);
  const [radius, setRadius] = useState(p.archetype?.default_catchment_km || 3);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const cur = p.locations.find((l) => l.id === currentId);
  const [editRadius, setEditRadius] = useState<number>(cur?.catchment.radius_km || 3);
  useEffect(() => setEditRadius(cur?.catchment.radius_km || 3), [cur?.id, cur?.catchment.radius_km]);

  return (
    <div className="space-y-4">
      <ul className="space-y-2">
        {p.locations.map((l) => (
          <li key={l.id}>
            <button onClick={() => onSelect(l.id)} className={cn("w-full rounded-md border p-3 text-left text-sm", l.id === currentId ? "border-accent bg-accent/5" : "border-black/[0.07] hover:border-ink-500")}>
              <div className="font-medium">{l.label}</div>
              <div className="truncate text-xs text-ink-400">{l.address}</div>
              <div className="mt-1 text-[11px] text-ink-500">{l.catchment.mode === "isochrone" ? `${l.catchment.minutes} min ${l.catchment.profile}` : `${l.catchment.radius_km} km radius`}{l.manual_population ? ` · population ${num(l.manual_population)} (user)` : ""}</div>
            </button>
          </li>
        ))}
      </ul>
      {cur && cur.catchment.mode === "radius" && (
        <div className="space-y-2 rounded-md border border-black/[0.07] p-3">
          <Field label={`Catchment radius for ${cur.label}: ${editRadius.toFixed(1)} km`}>
            <input type="range" min={0.5} max={6} step={0.1} value={editRadius} onChange={(e) => setEditRadius(Number(e.target.value))} className="w-full" aria-label="Catchment radius" />
          </Field>
          <Button
            size="sm"
            loading={busy}
            onClick={async () => {
              setBusy(true);
              await api(`/projects/${p.id}/locations/${cur.id}`, { method: "PATCH", json: { catchment: { ...cur.catchment, radius_km: editRadius } } });
              await refreshLocation(p.id, cur.id).catch(() => undefined);
              setBusy(false);
              onChanged();
            }}
          >
            Save and reload data
          </Button>
        </div>
      )}
      {!adding ? (
        p.locations.length < 5 && <Button size="sm" onClick={() => setAdding(true)}><Plus className="h-3.5 w-3.5" /> Add candidate location</Button>
      ) : (
        <div className="space-y-3 rounded-md border border-black/[0.07] p-3">
          <div className="text-sm font-medium">New candidate location</div>
          <LocationPicker value={place} onChange={setPlace} radiusKm={radius} height="h-56" />
          <Field label={`Radius ${radius.toFixed(1)} km`}>
            <input type="range" min={0.5} max={6} step={0.1} value={radius} onChange={(e) => setRadius(Number(e.target.value))} className="w-full" aria-label="New location radius" />
          </Field>
          {err && <ErrorState message={err} />}
          <div className="flex gap-2">
            <Button size="sm" onClick={() => setAdding(false)}>Cancel</Button>
            <Button
              size="sm"
              variant="primary"
              disabled={!place}
              loading={busy}
              onClick={async () => {
                if (!place) return;
                setBusy(true);
                setErr(null);
                try {
                  const l = await api<{ id: string }>(`/projects/${p.id}/locations`, { method: "POST", json: { label: "", address: place.address, lat: place.lat, lng: place.lng, catchment: { mode: "radius", radius_km: radius } } });
                  await api(`/projects/${p.id}/locations/${l.id}/refresh`, { method: "POST" }).catch(() => undefined); // loads in the background; the map follows it
                  setAdding(false);
                  setPlace(null);
                  onChanged();
                  onSelect(l.id);
                } catch (e) {
                  setErr(e instanceof ApiError ? e.message : "Could not add location");
                } finally {
                  setBusy(false);
                }
              }}
            >
              Add and load data
            </Button>
          </div>
          <p className="flex items-center gap-1 text-[11px] text-ink-500"><Users className="h-3 w-3" /> Create a scenario using this location in the Simulation Lab to compare it.</p>
        </div>
      )}
    </div>
  );
}
