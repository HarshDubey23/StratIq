"use client";

import { Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useProject } from "@/components/ProjectContext";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Evidence, Field, Input, Notice, NumberInput, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money, num, pct, when } from "@/lib/format";

interface Monitor {
  forecast: { run_id: string; run_at: string; units: number; revenue: number; costs: number; units_p10: number | null; units_p90: number | null; unit_label: string } | null;
  actuals: { period: string; units: number | null; revenue: number | null; costs: number | null; note: string; source: string; error: { units_abs: number; units_pct: number } | null; within_p10_p90: boolean | null }[];
  wape_units: number | null;
  note: string;
}

export default function MonitorPage() {
  const { project: p } = useProject();
  const [m, setM] = useState<Monitor | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [units, setUnits] = useState<number | null>(null);
  const [revenue, setRevenue] = useState<number | null>(null);
  const [costs, setCosts] = useState<number | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<Monitor>(`/projects/${p.id}/monitor`).then(setM).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load"));
  }, [p.id]);
  useEffect(load, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(`/projects/${p.id}/actual-outcomes`, { method: "POST", json: { period, units, revenue, costs, note } });
      setUnits(null);
      setRevenue(null);
      setCosts(null);
      setNote("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? (err.fields[0]?.message ? `${err.message}: ${err.fields[0].message}` : err.message) : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  if (!m && !error) return <div className="p-6"><Skeleton className="h-80" /></div>;
  const f = m?.forecast;
  const data = (m?.actuals || []).map((a) => ({ period: a.period, actual: a.units, forecast: f?.units }));
  return (
    <main className="mx-auto w-full max-w-6xl space-y-5 p-4 md:p-6">
      <Notice>
        Record what actually happens once you open. StrataIQ compares it with the baseline forecast so you can see which assumptions were off. {m?.note}
      </Notice>
      {error && <ErrorState message={error} />}
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <Card>
          <CardHeader title="Forecast vs actual" subtitle={f ? `Baseline forecast from ${when(f.run_at)}` : "Run the baseline first to get a forecast."} right={m?.wape_units !== null && m?.wape_units !== undefined ? <Badge>WAPE {pct(m.wape_units, 1)}</Badge> : null} />
          <div className="p-3">
            {data.length === 0 ? (
              <EmptyState title="No actual outcomes recorded yet" body="Add a month’s figures on the right." />
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <ComposedChart data={data} margin={{ top: 10, right: 16, left: 4, bottom: 4 }}>
                  <CartesianGrid stroke="#192233" vertical={false} />
                  <XAxis dataKey="period" stroke="#64718A" fontSize={11} />
                  <YAxis stroke="#64718A" fontSize={11} width={48} />
                  <Tooltip contentStyle={{ background: "#111826", border: "1px solid #243045", fontSize: 12 }} />
                  {f?.units_p10 != null && f?.units_p90 != null && <ReferenceArea y1={f.units_p10} y2={f.units_p90} fill="#45E0A8" fillOpacity={0.08} />}
                  {f && <ReferenceLine y={f.units} stroke="#45E0A8" strokeDasharray="4 3" label={{ value: "forecast", fill: "#45E0A8", fontSize: 10, position: "right" }} />}
                  <Line dataKey="actual" stroke="#C59BFF" strokeWidth={2} dot={{ r: 3 }} />
                </ComposedChart>
              </ResponsiveContainer>
            )}
            {f && <p className="px-2 text-xs text-ink-400">Green band: P10–P90 of modeled {f.unit_label}. Purple: your reported figures.</p>}
          </div>
          {m && m.actuals.length > 0 && (
            <div className="overflow-x-auto border-t border-white/[0.06]">
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-ink-400"><th className="px-3 py-2 font-normal">Period</th><th className="text-right font-normal">Forecast</th><th className="text-right font-normal">Actual</th><th className="text-right font-normal">Error</th><th className="text-right font-normal">Revenue</th><th className="px-3 font-normal">Source</th><th /></tr></thead>
                <tbody>
                  {m.actuals.map((a) => (
                    <tr key={a.period} className="border-t border-white/[0.06]/60">
                      <td className="num px-3 py-2">{a.period}</td>
                      <td className="num text-right">{num(f?.units)}</td>
                      <td className="num text-right">{num(a.units)}</td>
                      <td className="num text-right">{a.error ? `${a.error.units_abs > 0 ? "+" : ""}${num(a.error.units_abs)} (${pct(a.error.units_pct)})` : "—"}</td>
                      <td className="num text-right">{money(a.revenue, { compact: true })}</td>
                      <td className="px-3"><Evidence kind="user" label="User-reported" /></td>
                      <td><button aria-label={`Delete ${a.period}`} onClick={async () => { await api(`/projects/${p.id}/actual-outcomes/${a.period}`, { method: "DELETE" }); load(); }} className="px-2 text-ink-500 hover:text-red-300"><Trash2 className="h-3.5 w-3.5" /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card>
          <CardHeader title="Record a month" />
          <form onSubmit={add} className="space-y-3 p-4">
            <Field label="Month"><Input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} required /></Field>
            <Field label={`Actual ${f?.unit_label || "units"}`}><NumberInput value={units} onChange={setUnits} allowEmpty /></Field>
            <Field label="Revenue"><NumberInput value={revenue} onChange={setRevenue} prefix="₹" allowEmpty /></Field>
            <Field label="Total costs"><NumberInput value={costs} onChange={setCosts} prefix="₹" allowEmpty /></Field>
            <Field label="Note"><Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. launch offer running" /></Field>
            <Button type="submit" variant="primary" className="w-full" loading={busy}>Save</Button>
            <p className="text-[11px] text-ink-500">Figures are labelled user-reported and are not independently verified. Saving the same month again overwrites it.</p>
          </form>
        </Card>
      </div>
    </main>
  );
}
