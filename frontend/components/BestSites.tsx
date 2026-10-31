"use client";

/**
 * Location finder: the same business and plan evaluated at every populated spot in the catchment.
 * Shows the shortlist, paints the opportunity on the 3D map, and can open a site as a real new location
 * (its own live data + the same strategy) and compare it on the Live market.
 */
import { Crosshair, MapPin, Navigation, ShieldCheck, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { MapOpportunity } from "@/components/MapView";
import { Button, cn, Notice } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import { sendStrategy } from "@/lib/screen";

export interface Site {
  lat: number;
  lng: number;
  current: boolean;
  demand: number;
  units: number;
  capacity: number;
  profit: number;
  revenue: number;
  payback_months: number | null;
  nearest_competitor_km: number | null;
  competitors_within_500m: number;
  people_within_1km: number;
  from_current_km: number;
  risk?: { prob_loss: number; profit_p10: number; profit_p90: number };
}

export interface SitesOut {
  current: Site;
  top: Site[];
  candidates: Site[];
  uplift_profit: number;
  uplift_demand: number;
  method: string;
  unit: string;
  scenario: { id: string; name: string };
  location: { id: string; label: string };
}

export function toOpportunity(s: SitesOut): MapOpportunity[] {
  const all = s.candidates;
  const lo = Math.min(...all.map((c) => c.profit));
  const hi = Math.max(...all.map((c) => c.profit));
  const span = Math.max(1, hi - lo);
  const rankOf = (c: Site) => {
    const i = s.top.findIndex((t) => t.lat === c.lat && t.lng === c.lng);
    return i >= 0 ? i + 1 : undefined;
  };
  return all.map((c) => {
    const rank = rankOf(c);
    const d = c.profit - s.current.profit;
    return { lat: c.lat, lng: c.lng, score: (c.profit - lo) / span, rank, label: rank ? `#${rank}  ${d >= 0 ? "+" : "−"}${money(Math.abs(d), { compact: true })}/mo` : undefined };
  });
}

export function BestSites({ projectId, scenarioId, locationKey, onData, onFocus }: {
  projectId: string;
  scenarioId?: string;
  locationKey: string;
  onData: (s: SitesOut | null) => void;
  onFocus: (lat: number, lng: number) => void;
}) {
  const router = useRouter();
  const [data, setData] = useState<SitesOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setErr(null);
    api<SitesOut>(`/projects/${projectId}/sites${scenarioId ? `?scenario_id=${scenarioId}` : ""}`)
      .then((d) => {
        if (!live) return;
        setData(d);
        onData(d);
      })
      .catch((e) => live && setErr(e instanceof ApiError ? e.message : "Could not scan sites"))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
      onData(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, scenarioId, locationKey]);

  async function adopt(i: number, s: Site) {
    setBusy(i);
    setErr(null);
    try {
      const out = await api<{ scenario: { id: string } }>(`/projects/${projectId}/sites/adopt`, { method: "POST", json: { lat: s.lat, lng: s.lng, from_scenario_id: scenarioId } });
      sendStrategy({ scenario_id: out.scenario.id, result: out });
      router.push(`/app/projects/${projectId}/live`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not open this site");
      setBusy(null);
    }
  }

  if (loading) return <p className="text-xs text-ink-400">Testing your plan at every populated spot in the catchment…</p>;
  if (err) return <Notice tone="warn">{err}</Notice>;
  if (!data) return null;
  const c = data.current;
  const better = data.top.filter((t) => t.profit > c.profit);
  return (
    <div className="space-y-3 text-xs">
      <div className="rounded-xl border border-model/40 bg-model/[0.06] p-3">
        <div className="mb-1 flex items-center gap-1.5 font-medium text-ink-100"><Crosshair className="h-3.5 w-3.5 text-model" /> Where should you open?</div>
        <p className="leading-relaxed text-ink-300">
          I tested your exact plan at {num(data.candidates.length)} spots. {better.length
            ? <>The best is <b className="text-model">{money(data.uplift_profit, { compact: true })}/month better</b> than your current site.</>
            : <>Your current site is already the best spot in this area.</>} Green glow on the map = more profit; the green pillars are the shortlist.
        </p>
      </div>
      <SiteRow title={`Your site · ${data.location.label}`} s={c} unit={data.unit} base={c} current onFocus={() => onFocus(c.lat, c.lng)} />
      {data.top.map((s, i) => (
        <SiteRow key={`${s.lat},${s.lng}`} title={`#${i + 1} · ${s.from_current_km} km away`} s={s} unit={data.unit} base={c} onFocus={() => onFocus(s.lat, s.lng)}
          action={<Button size="sm" variant={i === 0 ? "primary" : "secondary"} loading={busy === i} disabled={busy !== null} onClick={() => adopt(i, s)}>
            <Sparkles className="h-3 w-3" /> {busy === i ? "Loading live data there…" : "Open this site & simulate"}
          </Button>} />
      ))}
      <p className="text-[10.5px] leading-relaxed text-ink-500">{data.method}</p>
    </div>
  );
}

function SiteRow({ title, s, unit, base, current, onFocus, action }: { title: string; s: Site; unit: string; base: Site; current?: boolean; onFocus: () => void; action?: React.ReactNode }) {
  const d = s.profit - base.profit;
  return (
    <div className={cn("rounded-xl border p-3", current ? "border-accent/40 bg-accent/[0.04]" : "border-black/[0.07] bg-black/[0.025]")}>
      <div className="mb-1.5 flex items-center gap-2">
        <MapPin className={cn("h-3.5 w-3.5", current ? "text-accent" : "text-model")} />
        <span className="font-medium text-ink-100">{title}</span>
        <button onClick={onFocus} className="ml-auto inline-flex items-center gap-1 text-[11px] text-ink-400 hover:text-ink-100"><Navigation className="h-3 w-3" /> Show</button>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Stat l="Profit / month" v={money(s.profit, { compact: true })} d={current ? undefined : d} />
        <Stat l={`Demand (${unit})`} v={num(s.demand)} />
        <Stat l="People ≤1 km" v={num(s.people_within_1km)} />
        <Stat l="Rivals ≤500 m" v={String(s.competitors_within_500m)} />
        <Stat l="Nearest rival" v={s.nearest_competitor_km !== null ? `${num(s.nearest_competitor_km * 1000)} m` : "—"} />
        {s.risk ? <Stat l="Loss chance" v={pct(s.risk.prob_loss)} icon /> : <Stat l="Payback" v={s.payback_months ? `${s.payback_months} mo` : "—"} />}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

function Stat({ l, v, d, icon }: { l: string; v: string; d?: number; icon?: boolean }) {
  return (
    <div>
      <div className="flex items-center gap-1 text-[10px] text-ink-500">{icon && <ShieldCheck className="h-2.5 w-2.5" />}{l}</div>
      <div className="num text-[12.5px] font-medium text-ink-100">{v}</div>
      {d !== undefined && Math.abs(d) >= 1 && <div className={cn("num text-[10px]", d > 0 ? "text-model" : "text-danger")}>{d > 0 ? "+" : "−"}{money(Math.abs(d), { compact: true })}</div>}
    </div>
  );
}
