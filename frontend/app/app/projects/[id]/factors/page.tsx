"use client";

import { Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useProject } from "@/components/ProjectContext";
import { Badge, Card, cn, ErrorState, Input, Notice, Select, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { num } from "@/lib/format";
import type { FactorsResponse } from "@/lib/types";

const STATUS: Record<string, { label: string; cls: string; help: string }> = {
  computed: { label: "Computed", cls: "border-observed/40 bg-observed/10 text-observed", help: "Derived from live data for this location (OpenStreetMap, WorldPop, geometry)." },
  user: { label: "User", cls: "border-userdata/40 bg-userdata/10 text-userdata", help: "Entered by you." },
  assumed: { label: "Assumed", cls: "border-ink-500 bg-ink-800 text-ink-200", help: "Documented model assumption (default or your override)." },
  simulated: { label: "Simulated", cls: "border-model/40 bg-model/10 text-model", help: "Produced by the simulation run." },
  pending: { label: "Pending", cls: "border-sky-400/30 bg-sky-400/5 text-sky-300", help: "Computable once market data is loaded or the scenario is run." },
  unavailable: { label: "No source yet", cls: "border-ink-700 bg-ink-900 text-ink-500", help: "Defined for future data. No source connected, so no value is invented." },
};
const ROLE: Record<string, string> = { agent: "Agent profile", choice: "Choice model", finance: "Economics", output: "Output", context: "Evidence", reserved: "Future data" };

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Math.abs(v) < 1 && v !== 0 ? v.toFixed(3) : num(v, 2);
  if (typeof v === "boolean") return v ? "yes" : "no";
  const s = String(v);
  return s.length > 60 ? s.slice(0, 57) + "…" : s;
}

export default function Factors() {
  const { project: p } = useProject();
  const scenarios = p.scenarios || [];
  const [sid, setSid] = useState(scenarios.find((s) => s.is_baseline)?.id);
  const [data, setData] = useState<FactorsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [domain, setDomain] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");
  const [q, setQ] = useState("");

  const load = useCallback(() => {
    setData(null);
    api<FactorsResponse>(`/projects/${p.id}/factors${sid ? `?scenario_id=${sid}` : ""}`).then(setData).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load factors"));
  }, [p.id, sid]);
  useEffect(load, [load]);

  const rows = useMemo(() => {
    if (!data) return [];
    const vals = Object.fromEntries(data.values.map((v) => [v.key, v]));
    const ql = q.trim().toLowerCase();
    return data.definitions
      .map((d) => ({ d, v: vals[d.key] }))
      .filter(({ d, v }) => (domain === "all" || d.domain === domain) && (status === "all" || v.status === status) && (!ql || d.label.toLowerCase().includes(ql) || d.key.includes(ql) || d.group.toLowerCase().includes(ql)));
  }, [data, domain, status, q]);

  if (error) return <div className="p-6"><ErrorState message={error} onRetry={load} /></div>;
  if (!data) return <div className="space-y-3 p-6"><Skeleton className="h-24" /><Skeleton className="h-96" /></div>;

  const domStatus = (dom: string) => {
    const keys = new Set(data.definitions.filter((d) => d.domain === dom).map((d) => d.key));
    const vs = data.values.filter((v) => keys.has(v.key));
    return { total: vs.length, filled: vs.filter((v) => !["pending", "unavailable"].includes(v.status)).length };
  };

  return (
    <main className="mx-auto w-full max-w-7xl space-y-5 p-4 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Factor Intelligence Engine</h2>
          <p className="text-sm text-ink-300">{data.counts.total} factors across {Object.keys(data.domains).length} domains, each labelled with where its value comes from.</p>
        </div>
        <Select value={sid} onChange={(e) => setSid(e.target.value)} className="w-auto" aria-label="Scenario">
          {scenarios.map((s) => <option key={s.id} value={s.id}>{s.name}{s.is_baseline ? " (baseline)" : ""}</option>)}
        </Select>
      </div>

      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {Object.entries(STATUS).map(([k, s]) => (
          <button key={k} onClick={() => setStatus(status === k ? "all" : k)} title={s.help} className={cn("rounded-lg border p-3 text-left transition-colors", status === k ? "border-accent" : "border-ink-700 hover:border-ink-500", "bg-ink-900")}>
            <div className={cn("inline-flex rounded border px-1.5 py-px text-[10px] font-medium uppercase", s.cls)}>{s.label}</div>
            <div className="num mt-1.5 text-2xl font-semibold">{data.summary[k] || 0}</div>
          </button>
        ))}
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {Object.entries(data.domains).map(([k, label]) => {
          const ds = domStatus(k);
          return (
            <button key={k} onClick={() => setDomain(domain === k ? "all" : k)} className={cn("rounded-lg border bg-ink-900 p-3 text-left", domain === k ? "border-accent" : "border-ink-700 hover:border-ink-500")}>
              <div className="text-xs font-medium text-ink-200">{label}</div>
              <div className="num mt-1 text-sm"><span className="text-ink-100">{ds.filled}</span><span className="text-ink-500"> / {ds.total} with values</span></div>
              <div className="mt-1.5 h-1 rounded bg-ink-800"><div className="h-1 rounded bg-accent" style={{ width: `${(ds.filled / Math.max(1, ds.total)) * 100}%` }} /></div>
            </button>
          );
        })}
      </div>

      <Notice>
        Values come from live sources for this location, your inputs, documented assumptions, or the simulation run. Factors marked <b>No source yet</b> are part of the framework but no data source
        is connected, so StrataIQ shows them empty instead of making numbers up.
      </Notice>

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-ink-700 p-3">
          <div className="relative min-w-60 flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-ink-400" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search factors, e.g. ‘age’, ‘metro’, ‘churn’" className="pl-9" aria-label="Search factors" />
          </div>
          {(domain !== "all" || status !== "all") && (
            <button onClick={() => { setDomain("all"); setStatus("all"); }} className="text-xs text-accent hover:underline">Clear filters</button>
          )}
          <Badge>{rows.length} shown</Badge>
        </div>
        <div className="max-h-[70vh] overflow-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead className="sticky top-0 bg-ink-900 text-left text-xs text-ink-400">
              <tr>
                <th className="px-3 py-2 font-normal">Factor</th>
                <th className="font-normal">Domain · group</th>
                <th className="text-right font-normal">Value</th>
                <th className="pl-3 font-normal">Unit</th>
                <th className="font-normal">Status</th>
                <th className="pr-3 font-normal">Used in</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ d, v }) => (
                <tr key={d.key} className="border-t border-ink-800/70 hover:bg-ink-850" title={d.description}>
                  <td className="px-3 py-1.5">
                    <div className="text-ink-100">{d.label}</div>
                    <div className="num text-[10px] text-ink-500">{d.key}</div>
                  </td>
                  <td className="text-xs text-ink-400">{data.domains[d.domain]} · {d.group}</td>
                  <td className="num text-right">{fmt(v.value)}</td>
                  <td className="pl-3 text-xs text-ink-400">{d.unit}</td>
                  <td><span className={cn("inline-flex rounded border px-1.5 py-px text-[10px] font-medium uppercase", STATUS[v.status].cls)}>{STATUS[v.status].label}</span></td>
                  <td className="pr-3 text-xs text-ink-300">{ROLE[d.role]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </main>
  );
}
