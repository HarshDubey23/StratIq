"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Map as MarketMap } from "@/components/Map";
import { Evidence, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import type { MarketData, Project, Run, SimResult } from "@/lib/types";

/** Overview hero: the 3D market with its headline numbers, all from live sources or the model. */
export default function MarketGlance({ project: p }: { project: Project }) {
  const [data, setData] = useState<MarketData | null>(null);
  const [res, setRes] = useState<SimResult | null>(null);
  const loc = p.locations[0];
  const baseline = p.scenarios?.find((s) => s.is_baseline);
  useEffect(() => {
    if (!loc) return;
    api<MarketData>(`/projects/${p.id}/market?location_id=${loc.id}`).then(setData).catch(() => setData(null));
  }, [p.id, loc]);
  useEffect(() => {
    const rid = baseline?.latest_run?.id;
    if (!rid) return setRes(null);
    api<Run>(`/simulation-runs/${rid}/results`).then((r) => setRes(r.results || null)).catch(() => setRes(null));
  }, [baseline?.latest_run?.id]);

  const snap = data?.snapshot;
  const comps = useMemo(() => (data?.competitors || []).filter((c) => c.active).map((c) => ({ id: c.id, name: c.name, lat: c.lat, lng: c.lng, kind: (c.source === "user" ? "user" : c.source) as "osm" | "user" | "demo" })), [data]);
  const zones = useMemo(() => (snap?.zones || []).map((z) => ({ lat: z.lat, lng: z.lng, value: z.population })), [snap]);
  const weight = useMemo(() => Object.fromEntries((res?.competitors || []).map((c) => [c.id, c.modeled_units])), [res]);
  if (!loc) return null;

  const stats: [string, string, "observed" | "official" | "model" | "demo"][] = [
    ["Competitors mapped", data ? num(comps.length) : "—", p.is_demo ? "demo" : "observed"],
    ["People in catchment", snap?.population.total ? num(snap.population.total) : "—", p.is_demo ? "demo" : "official"],
    [`${res?.unit_label || "Customers"} / month`, res ? num(res.summary.units_sold) : "—", "model"],
    ["Operating profit / month", res ? money(res.finance.operating_profit, { compact: true }) : "—", "model"],
    ["Chance of a loss", res?.monte_carlo ? pct(res.monte_carlo.prob_loss) : "—", "model"],
  ];
  return (
    <section className="relative overflow-hidden rounded-[28px] border border-white/[0.07]">
      <div className="relative h-[420px]">
        {data ? (
          <MarketMap
            fill
            center={[loc.lng, loc.lat]}
            catchment={snap?.catchment_geojson || null}
            zones={zones}
            competitors={comps}
            candidates={[{ id: loc.id, label: loc.label, lat: loc.lat, lng: loc.lng, active: true }]}
            layers={{ catchment: true, zones: true, competitors: true, agents: false, activity: false, buildings3d: true }}
            zoneSpacingKm={snap?.population.spacing_km}
            competitorWeight={weight}
            fitKey={snap?.id || "none"}
            pitch={60}
          />
        ) : (
          <Skeleton className="h-full rounded-none" />
        )}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-ink-950/80 to-transparent" />
        <Link href={`/app/projects/${p.id}/market`} className="panel absolute left-4 top-4 z-10 rounded-full px-4 py-2 text-xs text-ink-100 hover:border-accent/50">Open market map</Link>
      </div>
      <div className="relative grid grid-cols-2 gap-3 p-4 sm:grid-cols-5">
        {stats.map(([l, v, k]) => (
          <div key={l} className="rounded-2xl border border-white/[0.07] bg-white/[0.025] p-4">
            <div className="flex items-center justify-between gap-2 text-[11.5px] text-ink-400">{l}<Evidence kind={k} className="scale-90" /></div>
            <div className="num font-display mt-2 text-[26px] font-semibold leading-none tracking-tight">{v}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
