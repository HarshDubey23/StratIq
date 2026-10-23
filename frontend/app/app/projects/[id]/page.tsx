"use client";

import { ArrowRight, CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";
import { useProject } from "@/components/ProjectContext";
import { Badge, Card, CardHeader, Evidence, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, GOALS, money, num, OBJECTIVES, pct } from "@/lib/format";
import type { Goal } from "@/lib/types";

export default function Overview() {
  const { project: p, reload } = useProject();
  const base = `/app/projects/${p.id}`;
  const scen = p.scenarios || [];
  const hasSnap = Object.values(p.snapshots || {}).some(Boolean);
  const baseline = scen.find((s) => s.is_baseline);
  const ran = !!baseline?.latest_run;
  const alt = scen.length > 1;
  const steps = [
    { done: hasSnap, t: "Load live market evidence", href: `${base}/market` },
    { done: ran, t: "Run the live market (10,000 agents)", href: `${base}/live` },
    { done: false, t: "X-ray agents & read the Market DNA", href: `${base}/genome` },
    { done: alt && scen.filter((s) => s.latest_run).length > 1, t: "Test an alternative scenario", href: `${base}/simulation` },
    { done: false, t: "Review the decision and what to verify", href: `${base}/decisions` },
    { done: false, t: "Share a feasibility report", href: `${base}/report` },
  ];
  const next = steps.find((s) => !s.done);

  async function setGoal(g: Goal) {
    await api(`/projects/${p.id}`, { method: "PATCH", json: { decision_goal: g } });
    await reload();
  }

  const profile = p.profile as Record<string, unknown>;
  return (
    <main className="mx-auto w-full max-w-6xl space-y-5 p-4 md:p-6">
      {next && (
        <Link href={next.href} className="flex items-center justify-between rounded-lg border border-accent/40 bg-accent/5 px-4 py-3 text-sm hover:bg-accent/10">
          <span><span className="text-ink-300">Next step:</span> <span className="font-medium text-ink-100">{next.t}</span></span>
          <ArrowRight className="h-4 w-4 text-accent" />
        </Link>
      )}
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Business concept" subtitle={OBJECTIVES[p.objective]} />
          <div className="grid gap-4 p-4 text-sm sm:grid-cols-2">
            <div className="space-y-2">
              <div><span className="text-ink-400">Category: </span>{p.category.label}</div>
              <div><span className="text-ink-400">Model type: </span>{p.archetype?.label}</div>
              <div><span className="text-ink-400">Searched as: </span><code className="num text-xs text-ink-300">{p.category.filters.join(" OR ")}</code></div>
              {typeof profile.description === "string" && profile.description && <p className="text-ink-300">{profile.description}</p>}
              {Array.isArray(profile.positioning) && profile.positioning.length > 0 && (
                <div className="flex flex-wrap gap-1.5">{(profile.positioning as string[]).map((x) => <Badge key={x}>{x}</Badge>)} <Evidence kind="user" label="Claimed" /></div>
              )}
            </div>
            <div className="space-y-2">
              <label className="block text-xs text-ink-400" htmlFor="goal">Recommendations optimise for</label>
              <Select id="goal" value={p.decision_goal} onChange={(e) => setGoal(e.target.value as Goal)}>
                {Object.entries(GOALS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </Select>
              {p.summary && (
                <div className="grid grid-cols-3 gap-2 pt-2">
                  <div><div className="text-[11px] text-ink-400">{p.summary.unit_label}</div><div className="num">{num(p.summary.units_sold)}</div></div>
                  <div><div className="text-[11px] text-ink-400">Op. profit / mo</div><div className="num">{money(p.summary.operating_profit, { compact: true })}</div></div>
                  <div><div className="text-[11px] text-ink-400">Loss risk</div><div className="num">{pct(p.summary.prob_loss)}</div></div>
                </div>
              )}
            </div>
          </div>
        </Card>
        <Card>
          <CardHeader title="Journey" />
          <ol className="space-y-1 p-3">
            {steps.map((s) => (
              <li key={s.t}>
                <Link href={s.href} className="flex items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-ink-850">
                  {s.done ? <CheckCircle2 className="h-4 w-4 text-model" /> : <Circle className="h-4 w-4 text-ink-500" />}
                  <span className={s.done ? "text-ink-300" : "text-ink-100"}>{s.t}</span>
                </Link>
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title="Candidate locations" right={<Link href={`${base}/market`} className="text-xs text-accent hover:underline">Open map</Link>} />
          <ul className="divide-y divide-white/[0.06]">
            {p.locations.map((l) => {
              const s = p.snapshots?.[l.id];
              return (
                <li key={l.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                  <div className="min-w-0">
                    <div className="font-medium">{l.label}</div>
                    <div className="truncate text-xs text-ink-400">{l.address}</div>
                  </div>
                  {s ? <Badge tone={s.status === "complete" ? "ok" : "warn"}>{s.status} · {ago(s.retrieved_at)}</Badge> : <Badge>no data yet</Badge>}
                </li>
              );
            })}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Scenarios" right={<Link href={`${base}/simulation`} className="text-xs text-accent hover:underline">Open lab</Link>} />
          <ul className="divide-y divide-white/[0.06]">
            {scen.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                <div>
                  <span className="font-medium">{s.name}</span> {s.is_baseline && <Badge tone="accent">baseline</Badge>}
                  <div className="num text-xs text-ink-400">price {money(s.inputs.price)}</div>
                </div>
                {s.latest_run ? <Badge tone={s.latest_run.stale ? "warn" : "ok"}>{s.latest_run.stale ? "inputs changed" : "simulated"} · {ago(s.latest_run.finished_at)}</Badge> : <Badge>not run</Badge>}
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </main>
  );
}
