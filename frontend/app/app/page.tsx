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

  const [liveBusy, setLiveBusy] = useState(false);
  async function liveDemo() {
    setLiveBusy(true);
    try {
      const p = await api<Project>("/demo/live", { method: "POST" });
      router.push(`/app/projects/${p.id}/market`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the live demo");
      setLiveBusy(false);
    }
  }

  async function demo() {
    setBusy(true);
    try {
      const p = await api<Project>("/demo", { method: "POST" });
      router.push(`/app/projects/${p.id}/live`);
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
    <main className="mx-auto w-full max-w-7xl px-4 py-10 md:px-10">
      <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
        <div>
          <p className="text-sm text-ink-400">{user?.name && user.name !== "Guest" ? `Namaste, ${user.name.split(" ")[0]}` : "Namaste"}</p>
          <h1 className="font-display mt-2 max-w-3xl text-[clamp(2rem,4.4vw,3.6rem)] font-semibold leading-[0.98] tracking-[-0.04em]">What would you open, and where?</h1>
          <p className="mt-3 max-w-xl text-[15px] text-ink-300">Describe any business and pick any street. StrataIQ loads the real market around it and simulates who would come.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={liveDemo} loading={liveBusy}>
            <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-model opacity-70" /><span className="relative inline-flex h-2 w-2 rounded-full bg-model" /></span>
            Live demo: gym in Connaught Place
          </Button>
          <ButtonLink href="/app/projects/new" variant="primary">New analysis <ArrowRight className="h-4 w-4" /></ButtonLink>
        </div>
      </div>

      <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {actions.map((a) => (
          <Link key={a.t} href={a.href} className="group relative overflow-hidden rounded-3xl border border-white/[0.07] bg-gradient-to-b from-ink-850 to-ink-900 p-5 transition-[border-color,transform] duration-500 hover:-translate-y-0.5 hover:border-accent/40">
            <span className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-accent/0 blur-2xl transition-colors duration-500 group-hover:bg-accent/20" />
            <a.i className="h-5 w-5 text-accent" />
            <div className="font-display mt-6 text-lg font-semibold tracking-tight">{a.t}</div>
            <div className="mt-1 text-[13px] text-ink-400">{a.d}</div>
          </Link>
        ))}
      </div>

      <div className="mt-12 flex items-center justify-between">
        <h2 className="font-display text-xl font-semibold tracking-tight">Your simulations</h2>
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
              <div key={p.id} className="flex flex-col rounded-3xl border border-white/[0.07] bg-gradient-to-b from-ink-850 to-ink-900 p-5 transition-colors hover:border-white/15">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link href={`/app/projects/${p.id}`} className="font-display block truncate text-lg font-semibold tracking-tight hover:text-accent">{p.name}</Link>
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
                        <div className="num font-display text-lg font-semibold">{num(p.summary.units_sold)}</div>
                      </div>
                      <div>
                        <div className="text-[11px] text-ink-400">Monthly op. profit</div>
                        <div className={`num font-display text-lg font-semibold ${p.summary.operating_profit < 0 ? "text-red-300" : "text-emerald-300"}`}>{money(p.summary.operating_profit, { compact: true })}</div>
                      </div>
                      <div>
                        <div className="text-[11px] text-ink-400">Modeled loss risk</div>
                        <div className="num font-display text-lg font-semibold">{pct(p.summary.prob_loss)}</div>
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
