"use client";

import { ArrowRight, FlaskConical, GitCompareArrows, MapPinned, Rocket, Trash2, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "@/components/AppShell";
import { Badge, Button, ButtonLink, Dialog, EmptyState, ErrorState, Evidence, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { ago, money, num, OBJECTIVES, pct } from "@/lib/format";
import type { Project } from "@/lib/types";

const actions = [
  { href: "/app/projects/new?objective=start_new", t: "Start a business", d: "Test a new idea at a location", i: Rocket },
  { href: "/app/projects/new?objective=improve_existing", t: "Grow my business", d: "Diagnose and improve with your figures", i: TrendingUp },
  { href: "/app/projects/new?objective=compare_locations", t: "Compare locations", d: "Rank candidate sites side by side", i: MapPinned },
  { href: "/app/projects/new?objective=test_strategy", t: "Optimise my strategy", d: "Price, marketing and capacity tests", i: GitCompareArrows },
];

export default function Dashboard() {
  const { user } = useSession();
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [del, setDel] = useState<Project | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api<Project[]>("/projects").then(setProjects).catch((e) => setError(e instanceof ApiError ? e.message : "Could not load projects"));
  }, []);
  useEffect(load, [load]);

  async function demo() {
    setBusy(true);
    try {
      const p = await api<Project>("/demo", { method: "POST" });
      router.push(`/app/projects/${p.id}/simulation`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create demo");
      setBusy(false);
    }
  }

  async function remove() {
    if (!del) return;
    await api(`/projects/${del.id}`, { method: "DELETE" });
    setDel(null);
    load();
  }

  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-8 md:px-8">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="text-sm text-ink-400">{user?.name ? `Hi ${user.name.split(" ")[0]}` : " "}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Make your next business move with more confidence.</h1>
          <p className="mt-1.5 text-sm text-ink-300">Explore markets, test strategies, and find out what you need to validate before investing.</p>
        </div>
        <ButtonLink href="/app/projects/new" variant="primary">New analysis <ArrowRight className="h-4 w-4" /></ButtonLink>
      </div>

      <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {actions.map((a) => (
          <Link key={a.t} href={a.href} className="group rounded-lg border border-ink-700 bg-ink-900 p-4 transition-colors hover:border-accent/50">
            <a.i className="h-5 w-5 text-accent" />
            <div className="mt-3 text-sm font-semibold">{a.t}</div>
            <div className="mt-0.5 text-xs text-ink-400">{a.d}</div>
          </Link>
        ))}
      </div>

      <div className="mt-10 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-300">Your simulations</h2>
        <Button size="sm" variant="ghost" onClick={demo} loading={busy}>
          <FlaskConical className="h-3.5 w-3.5" /> Open labelled demo
        </Button>
      </div>

      <div className="mt-3">
        {error && <ErrorState message={error} onRetry={load} />}
        {!projects && !error && (
          <div className="grid gap-3 md:grid-cols-2">
            {[0, 1].map((i) => <Skeleton key={i} className="h-36" />)}
          </div>
        )}
        {projects && projects.length === 0 && (
          <EmptyState
            icon={<MapPinned className="h-6 w-6" />}
            title="No simulations yet"
            body="Describe a business, pick a place, and StrataIQ will load live market evidence and simulate customer choices."
            action={<ButtonLink href="/app/projects/new" variant="primary">Build your first market simulation</ButtonLink>}
          />
        )}
        {projects && projects.length > 0 && (
          <div className="grid gap-3 md:grid-cols-2">
            {projects.map((p) => (
              <div key={p.id} className="flex flex-col rounded-lg border border-ink-700 bg-ink-900 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link href={`/app/projects/${p.id}`} className="block truncate font-semibold hover:text-accent">{p.name}</Link>
                    <div className="mt-0.5 truncate text-xs text-ink-400">
                      {p.category.label} · {p.locations[0]?.address || `${p.locations[0]?.lat.toFixed(4)}, ${p.locations[0]?.lng.toFixed(4)}`}
                    </div>
                  </div>
                  <button aria-label={`Delete ${p.name}`} onClick={() => setDel(p)} className="text-ink-500 hover:text-red-300">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {p.is_demo && <Evidence kind="demo" />}
                  {p.data_kinds?.connected_sources && !p.is_demo && <Evidence kind="observed" label="Live sources" />}
                  <Evidence kind="user" label="Your inputs" />
                  <Evidence kind="model" label="Synthetic estimates" />
                  <Badge>{OBJECTIVES[p.objective]}</Badge>
                </div>
                <div className="mt-4 flex-1 text-sm">
                  {p.summary ? (
                    <div className="grid grid-cols-3 gap-2">
                      <div>
                        <div className="text-[11px] text-ink-400">Baseline {p.summary.unit_label}</div>
                        <div className="num">{num(p.summary.units_sold)}</div>
                      </div>
                      <div>
                        <div className="text-[11px] text-ink-400">Monthly op. profit</div>
                        <div className={`num ${p.summary.operating_profit < 0 ? "text-red-300" : "text-emerald-300"}`}>{money(p.summary.operating_profit, { compact: true })}</div>
                      </div>
                      <div>
                        <div className="text-[11px] text-ink-400">Modeled loss risk</div>
                        <div className="num">{pct(p.summary.prob_loss)}</div>
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-ink-400">Not simulated yet.</p>
                  )}
                </div>
                <div className="mt-4 flex items-center justify-between text-xs text-ink-400">
                  <span>Updated {ago(p.updated_at)}</span>
                  <Link href={`/app/projects/${p.id}`} className="inline-flex items-center gap-1 text-accent hover:underline">Open project <ArrowRight className="h-3 w-3" /></Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Dialog
        open={!!del}
        onClose={() => setDel(null)}
        title="Delete project?"
        footer={
          <>
            <Button onClick={() => setDel(null)}>Cancel</Button>
            <Button variant="danger" onClick={remove}>Delete permanently</Button>
          </>
        }
      >
        “{del?.name}” and all its scenarios, runs, competitors you added and reports will be deleted. This cannot be undone.
      </Dialog>
    </main>
  );
}
