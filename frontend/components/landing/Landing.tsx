"use client";

import { ArrowUpRight, Loader2, Mic, RefreshCw } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Logo } from "@/components/brand";
import { cn } from "@/components/ui";
import { SPOTS, type PreviewComp, type Spot } from "./spots";

const HeroMap = dynamic(() => import("./HeroMap"), { ssr: false, loading: () => <div className="absolute inset-0 bg-ink-950" /> });

const CATS = [
  { key: "cafe", label: "Cafés" },
  { key: "gym", label: "Gyms" },
  { key: "pharmacy", label: "Pharmacies" },
  { key: "salon", label: "Salons" },
  { key: "restaurant", label: "Restaurants" },
];

interface Preview {
  spot: Spot;
  category: { key: string; label: string };
  radius_m: number;
  competitors: PreviewComp[];
  source: { name: string; retrieved_at: string; detail: string; from_cache: boolean };
}

async function ensureSession(): Promise<void> {
  const me = await fetch("/api/v1/auth/me", { credentials: "include" });
  if (me.ok) return;
  const g = await fetch("/api/v1/auth/guest", { method: "POST", credentials: "include" });
  if (!g.ok) throw new Error("The server is waking up. Try again in a few seconds.");
}

function useReveal() {
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal], .reveal-lines"));
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && (e.target.classList.add("is-in"), io.unobserve(e.target))),
      { threshold: 0.18, rootMargin: "0px 0px -8% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
}

function useLenis() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    let lenis: { raf: (t: number) => void; destroy: () => void } | null = null;
    import("lenis").then(({ default: Lenis }) => {
      lenis = new Lenis({ lerp: 0.085, wheelMultiplier: 0.95 }) as unknown as typeof lenis;
      const loop = (t: number) => {
        lenis?.raf(t);
        raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
    });
    return () => {
      cancelAnimationFrame(raf);
      lenis?.destroy();
    };
  }, []);
}

function Lines({ lines, className, as: As = "h1" }: { lines: string[]; className?: string; as?: "h1" | "h2" }) {
  return (
    <As className={cn("reveal-lines", className)}>
      {lines.map((l, i) => (
        <span key={i} className="line-mask">
          <span style={{ transitionDelay: `${120 + i * 110}ms` }}>{l}</span>
        </span>
      ))}
    </As>
  );
}

export default function Landing() {
  const router = useRouter();
  const [spot, setSpot] = useState<Spot>(SPOTS[0]);
  const [cat, setCat] = useState("cafe");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [chapter, setChapter] = useState(0);
  const [busy, setBusy] = useState<null | "live" | "new">(null);
  const [goErr, setGoErr] = useState<string | null>(null);
  const [now, setNow] = useState<number>(() => Date.now());
  useReveal();
  useLenis();

  const load = useCallback(async () => {
    setLoading(true);
    setLoadErr(null);
    const ctl = new AbortController();
    const to = setTimeout(() => ctl.abort(), 75_000);
    try {
      const r = await fetch(`/api/v1/market/preview?spot=${spot.key}&category=${cat}`, { signal: ctl.signal });
      if (!r.ok) throw new Error(r.status === 502 || r.status === 503 ? "OpenStreetMap is busy" : `HTTP ${r.status}`);
      setPreview(await r.json());
    } catch (e) {
      setLoadErr(e instanceof Error && e.name !== "AbortError" ? e.message : "The live-data server is waking up");
    } finally {
      clearTimeout(to);
      setLoading(false);
    }
  }, [spot.key, cat]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 15_000);
    return () => clearInterval(id);
  }, []);

  // scroll chapters drive the camera
  const chapters = useRef<HTMLElement[]>([]);
  useEffect(() => {
    const io = new IntersectionObserver(
      (es) => {
        for (const e of es) if (e.isIntersecting) setChapter(Number((e.target as HTMLElement).dataset.chapter || 0));
      },
      { threshold: 0.45 },
    );
    chapters.current.forEach((c) => c && io.observe(c));
    return () => io.disconnect();
  }, []);
  const reg = (i: number) => (el: HTMLElement | null) => {
    if (el) chapters.current[i] = el;
  };

  async function go(kind: "live" | "new") {
    setBusy(kind);
    setGoErr(null);
    try {
      await ensureSession();
      if (kind === "new") {
        router.push("/app/projects/new");
        return;
      }
      const r = await fetch(`/api/v1/demo/live?spot=${spot.key === "bandra" || spot.key === "indiranagar" ? spot.key : "cp-delhi"}`, { method: "POST", credentials: "include" });
      if (!r.ok) throw new Error("Could not start the live demo. Try again in a moment.");
      const p = await r.json();
      router.push(`/app/projects/${p.id}/market`);
    } catch (e) {
      setGoErr(e instanceof Error ? e.message : "Something went wrong");
      setBusy(null);
    }
  }

  const comps = preview && preview.spot.key === spot.key ? preview.competitors : [];
  const agoMin = preview ? Math.max(0, Math.round((now - new Date(preview.source.retrieved_at).getTime()) / 60000)) : null;
  const catLabel = CATS.find((c) => c.key === cat)?.label.toLowerCase() || "businesses";

  return (
    <div className="relative bg-ink-950 text-ink-100">
      {/* the city stays pinned behind every chapter */}
      <div className="fixed inset-0 z-0">
        <HeroMap spot={spot} comps={comps} chapter={chapter} showTrips={chapter >= 1 || !loading} />
      </div>

      <header className="fixed inset-x-0 top-0 z-40">
        <nav className="mx-auto flex h-20 max-w-[1400px] items-center justify-between px-5 md:px-10">
          <Logo />
          <div className="hidden items-center gap-8 text-[13.5px] text-ink-300 md:flex">
            <a href="#real" className="transition-colors hover:text-ink-100">The data</a>
            <a href="#agents" className="transition-colors hover:text-ink-100">The simulation</a>
            <a href="#voice" className="transition-colors hover:text-ink-100">Voice analyst</a>
            <Link href="/methodology" className="transition-colors hover:text-ink-100">Methodology</Link>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/sign-in" className="hidden px-3 py-2 text-[13.5px] text-ink-200 hover:text-ink-100 sm:block">Sign in</Link>
            <button onClick={() => go("new")} className="inline-flex h-10 items-center gap-1.5 rounded-full bg-ink-100 px-5 text-[13.5px] font-medium text-ink-950 transition-colors hover:bg-white">
              {busy === "new" ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Start a simulation
            </button>
          </div>
        </nav>
      </header>

      <main className="relative z-10">
        {/* ---------------- hero ---------------- */}
        <section ref={reg(0)} data-chapter={0} className="relative flex min-h-[100svh] flex-col justify-end px-5 pb-10 pt-28 md:px-10 md:pb-14">
          <div className="mx-auto grid w-full max-w-[1400px] items-end gap-10 lg:grid-cols-[1.35fr_0.65fr]">
            <div>
              <p data-reveal className="mb-6 flex items-center gap-3 text-[13px] text-ink-300">
                <span className="font-deva text-base text-accent" lang="hi">बाज़ार</span>
                Market simulation for India&apos;s small businesses
              </p>
              <Lines
                lines={["Every street", "is a market.", "Test yours first."]}
                className="font-display text-[clamp(3.2rem,9.2vw,9.5rem)] font-semibold leading-[0.9] tracking-[-0.05em]"
              />
              <p data-reveal style={{ transitionDelay: "450ms" }} className="mt-8 max-w-[34rem] text-[17px] leading-[1.6] text-ink-200">
                Pick any business and any place. StrataIQ pulls the real competitors and population around it, lets ten thousand simulated
                customers choose, and shows profit, risk and break-even before you sign a lease.
              </p>
              <div data-reveal style={{ transitionDelay: "560ms" }} className="mt-9 flex flex-wrap items-center gap-3">
                <button onClick={() => go("live")} className="group inline-flex h-14 items-center gap-3 rounded-full bg-accent pl-7 pr-2 text-[15px] font-semibold text-ink-950 shadow-[0_20px_60px_-15px_rgba(255,159,46,.8)] transition-transform hover:-translate-y-0.5">
                  {busy === "live" ? "Opening the live market…" : "Open the live demo"}
                  <span className="flex h-10 w-10 items-center justify-center rounded-full bg-ink-950 text-accent transition-transform duration-500 group-hover:rotate-45">
                    {busy === "live" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUpRight className="h-4 w-4" />}
                  </span>
                </button>
                <button onClick={() => go("new")} className="inline-flex h-14 items-center rounded-full border border-white/15 bg-ink-950/40 px-7 text-[15px] text-ink-100 backdrop-blur-md transition-colors hover:border-white/30">
                  Test my own idea
                </button>
                <span className="flex items-center gap-2 pl-2 text-[13px] text-ink-400"><Mic className="h-3.5 w-3.5 text-accent" /> or press V and just ask</span>
              </div>
              {goErr && <p className="mt-4 text-sm text-warn">{goErr}</p>}
            </div>

            {/* live instrument: the one thing on this page that is fetched right now */}
            <aside data-reveal style={{ transitionDelay: "700ms" }} className="panel w-full rounded-[28px] p-5 lg:mb-2">
              <div className="flex items-center justify-between text-[12px] text-ink-400">
                <span className="flex items-center gap-2">
                  <span className="relative flex h-2 w-2">
                    <span className={cn("absolute inline-flex h-full w-full rounded-full opacity-75", loading ? "animate-ping bg-warn" : loadErr ? "bg-danger" : "animate-ping bg-model")} />
                    <span className={cn("relative inline-flex h-2 w-2 rounded-full", loading ? "bg-warn" : loadErr ? "bg-danger" : "bg-model")} />
                  </span>
                  {loading ? "Fetching from OpenStreetMap" : loadErr ? "Live data unavailable" : "Live from OpenStreetMap"}
                </span>
                <span className="coord">{spot.lat.toFixed(4)}°N {spot.lng.toFixed(4)}°E</span>
              </div>
              <div className="mt-4 flex items-end gap-3">
                <span className="num font-display text-[64px] font-semibold leading-none tracking-tight">{loading ? "—" : loadErr ? "?" : comps.length}</span>
                <span className="pb-2 text-[14px] leading-snug text-ink-300">
                  {catLabel} mapped within {((preview?.radius_m || 1600) / 1000).toFixed(1)} km of <span className="text-ink-100">{spot.label.split(",")[0]}</span>
                </span>
              </div>
              {loadErr ? (
                <button onClick={() => void load()} className="mt-3 inline-flex items-center gap-1.5 text-xs text-ink-300 hover:text-ink-100">
                  <RefreshCw className="h-3.5 w-3.5" /> {loadErr}. Retry
                </button>
              ) : (
                <div className="mt-3 line-clamp-1 text-xs text-ink-400">
                  {comps.slice(0, 4).map((c) => c.name).filter((n) => n !== "Unnamed").join(", ") || (loading ? "Querying Overpass mirrors…" : "")}
                </div>
              )}
              <div className="mt-5 flex flex-wrap gap-1.5">
                {CATS.map((c) => (
                  <button key={c.key} onClick={() => setCat(c.key)} className={cn("rounded-full px-3 py-1.5 text-[12px] transition-colors", cat === c.key ? "bg-ink-100 text-ink-950" : "bg-white/[0.05] text-ink-300 hover:text-ink-100")}>
                    {c.label}
                  </button>
                ))}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {SPOTS.map((s) => (
                  <button key={s.key} onClick={() => setSpot(s)} className={cn("rounded-full border px-3 py-1.5 text-[12px] transition-colors", spot.key === s.key ? "border-accent/60 text-ink-100" : "border-white/10 text-ink-400 hover:text-ink-100")}>
                    {s.label.split(",")[1]?.trim() || s.label}
                  </button>
                ))}
              </div>
              <p className="mt-4 border-t border-white/[0.06] pt-3 text-[11px] leading-relaxed text-ink-500">
                Blue pillars are real {catLabel} from OpenStreetMap{agoMin !== null && !loadErr ? `, retrieved ${agoMin === 0 ? "just now" : `${agoMin} min ago`}${preview?.source.from_cache ? " (cached)" : ""}` : ""}. Moving dots are simulated people, not real individuals.
              </p>
            </aside>
          </div>
        </section>

        {/* ---------------- the data is real ---------------- */}
        <section id="real" ref={reg(1)} data-chapter={1} className="relative flex min-h-[110vh] items-center px-5 md:px-10">
          <div className="mx-auto w-full max-w-[1400px]">
            <div className="max-w-xl">
              <Lines as="h2" lines={["The map", "isn't a mock-up."]} className="font-display text-[clamp(2.6rem,6vw,5.6rem)] font-semibold leading-[0.95] tracking-[-0.045em]" />
              <p data-reveal className="mt-7 text-[17px] leading-[1.65] text-ink-200">
                Every building you see is an OpenStreetMap footprint, extruded to its mapped height. Competitors are queried live for the exact
                category you type. Population comes from WorldPop&apos;s 100-metre grid and is spread across real buildings.
              </p>
              <dl data-reveal className="mt-10 grid grid-cols-2 gap-x-8 gap-y-6 border-t border-white/10 pt-8">
                {[
                  ["Competitors", "OpenStreetMap via racing Overpass mirrors, with a Photon fallback so a busy server never empties the map."],
                  ["Population", "WorldPop, constrained to mapped buildings inside your catchment."],
                  ["Every value", "Tagged observed, user-entered, assumed or modeled — on screen, in reports, in the voice answers."],
                  ["Gaps", "Unmapped shops are flagged, and you can add the ones you see on the street."],
                ].map(([t, d]) => (
                  <div key={t}>
                    <dt className="font-display text-[15px] font-semibold">{t}</dt>
                    <dd className="mt-1.5 text-[14px] leading-relaxed text-ink-300">{d}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        </section>

        {/* ---------------- agents ---------------- */}
        <section id="agents" ref={reg(2)} data-chapter={2} className="relative flex min-h-[110vh] items-center px-5 md:px-10">
          <div className="mx-auto flex w-full max-w-[1400px] justify-end">
            <div className="max-w-xl">
              <Lines as="h2" lines={["Ten thousand", "people decide."]} className="font-display text-[clamp(2.6rem,6vw,5.6rem)] font-semibold leading-[0.95] tracking-[-0.045em]" />
              <p data-reveal className="mt-7 text-[17px] leading-[1.65] text-ink-200">
                Synthetic customers are placed at real population density, each with a 615-parameter profile: budget, distance tolerance,
                habits, hours, trust. For 84 simulated days they choose between you, every competitor, or not buying at all.
              </p>
              <div data-reveal className="panel mt-10 rounded-3xl p-6">
                <div className="grid grid-cols-3 gap-4">
                  {[
                    ["10,000", "agents per run"],
                    ["615", "parameters each"],
                    ["84", "simulated days"],
                  ].map(([n, l]) => (
                    <div key={l}>
                      <div className="num font-display text-[34px] font-semibold tracking-tight">{n}</div>
                      <div className="mt-1 text-xs text-ink-400">{l}</div>
                    </div>
                  ))}
                </div>
                <p className="mt-5 border-t border-white/[0.06] pt-4 text-[13px] leading-relaxed text-ink-300">
                  Click any agent in the app to X-ray why it chose a competitor: price, travel, opening hours, down to the single parameter.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ---------------- decision ---------------- */}
        <section ref={reg(3)} data-chapter={3} className="relative flex min-h-[110vh] items-center px-5 md:px-10">
          <div className="mx-auto w-full max-w-[1400px]">
            <div className="max-w-xl">
              <Lines as="h2" lines={["A range,", "not a promise."]} className="font-display text-[clamp(2.6rem,6vw,5.6rem)] font-semibold leading-[0.95] tracking-[-0.045em]" />
              <p data-reveal className="mt-7 text-[17px] leading-[1.65] text-ink-200">
                Eight hundred uncertainty runs turn into a bad month, a typical month and a good month, the chance of losing money, and the
                customers you need to break even. Change the price, the rent or the site and the engine runs again.
              </p>
              <ProfitRange />
            </div>
          </div>
        </section>

        {/* ---------------- voice ---------------- */}
        <section id="voice" ref={reg(4)} data-chapter={4} className="relative flex min-h-[110vh] items-center px-5 md:px-10">
          <div className="mx-auto flex w-full max-w-[1400px] justify-end">
            <div className="max-w-xl">
              <Lines as="h2" lines={["Ask it out loud,", "in Hinglish."]} className="font-display text-[clamp(2.6rem,6vw,5.6rem)] font-semibold leading-[0.95] tracking-[-0.045em]" />
              <p data-reveal className="mt-7 text-[17px] leading-[1.65] text-ink-200">
                Strata keeps listening while you explore. It reads the live project, runs what-if prices through the real engine, and answers
                with the model&apos;s numbers — never its own guesses.
              </p>
              <div data-reveal className="mt-10 space-y-3 text-[15px]">
                <div className="ml-auto w-fit max-w-[85%] rounded-3xl rounded-br-md bg-white/[0.08] px-5 py-3 backdrop-blur-md">Kitne gyms hain paas mein?</div>
                <div className="w-fit max-w-[90%] rounded-3xl rounded-bl-md bg-accent/15 px-5 py-3 ring-1 ring-accent/30 backdrop-blur-md">
                  I&apos;m reading the live project… the nearest competitors come straight from OpenStreetMap, and I&apos;ll tell you which one the simulation says is strongest.
                </div>
                <div className="ml-auto w-fit max-w-[85%] rounded-3xl rounded-br-md bg-white/[0.08] px-5 py-3 backdrop-blur-md">What if I charge fifteen hundred?</div>
              </div>
              <p data-reveal className="mt-6 text-[13px] text-ink-400">Press <kbd className="rounded-md border border-white/15 px-1.5 py-0.5 text-ink-200">V</kbd> anywhere to talk. Works on English and Hindi speech.</p>
            </div>
          </div>
        </section>

        {/* ---------------- honesty + CTA ---------------- */}
        <section className="relative bg-gradient-to-b from-transparent via-ink-950/95 to-ink-950 px-5 pb-16 pt-40 md:px-10">
          <div className="mx-auto max-w-[1400px]">
            <div className="grid gap-12 border-t border-white/10 pt-14 lg:grid-cols-2">
              <div>
                <h2 data-reveal className="font-display text-[clamp(2rem,4vw,3.4rem)] font-semibold leading-[1] tracking-[-0.04em]">What StrataIQ won&apos;t pretend.</h2>
                <p data-reveal className="mt-5 max-w-md text-[15px] leading-relaxed text-ink-300">
                  A tool that helps people risk their savings has to be honest about its limits. These are on every result screen too.
                </p>
              </div>
              <ul className="divide-y divide-white/10 border-y border-white/10">
                {[
                  "It doesn't know every shop. Informal businesses are often unmapped, so the gaps are shown and you can add what you see.",
                  "Synthetic agents are not real people. They are a computational sample drawn from aggregate population data.",
                  "No accuracy percentage is advertised, because none has been measured on real outcomes yet.",
                  "Forecasts are conditional estimates, never a guarantee of profit or a substitute for financial advice.",
                ].map((t) => (
                  <li key={t} data-reveal className="py-5 text-[15px] leading-relaxed text-ink-200">{t}</li>
                ))}
              </ul>
            </div>

            <div className="mt-28 flex flex-col items-start justify-between gap-8 md:flex-row md:items-end">
              <Lines as="h2" lines={["Before the lease,", "run the market."]} className="font-display text-[clamp(2.8rem,7vw,7rem)] font-semibold leading-[0.92] tracking-[-0.05em]" />
              <button onClick={() => go("live")} className="group inline-flex h-16 shrink-0 items-center gap-3 rounded-full bg-accent pl-8 pr-2 text-base font-semibold text-ink-950 transition-transform hover:-translate-y-0.5">
                Open the live demo
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-ink-950 text-accent transition-transform duration-500 group-hover:rotate-45"><ArrowUpRight className="h-5 w-5" /></span>
              </button>
            </div>

            <footer className="mt-24 flex flex-col gap-4 border-t border-white/10 pt-6 text-xs text-ink-500 md:flex-row md:items-center md:justify-between">
              <Logo />
              <p>Map data © OpenStreetMap contributors (ODbL) · Population © WorldPop (CC BY 4.0) · Tiles © OpenFreeMap / OpenMapTiles · Voice by ElevenLabs</p>
              <Link href="/methodology" className="hover:text-ink-200">Methodology and limitations</Link>
            </footer>
          </div>
        </section>
      </main>
    </div>
  );
}

/** Shape-only illustration of how results are shown (no figures): a distribution with P10 / P50 / P90 markers. */
function ProfitRange() {
  const bars = Array.from({ length: 44 }, (_, i) => {
    const x = (i - 21) / 8;
    return Math.exp(-x * x * 0.9) * (1 + 0.18 * Math.sin(i * 1.7));
  });
  return (
    <figure data-reveal className="panel mt-10 rounded-3xl p-6">
      <div className="flex h-36 items-end gap-[3px]">
        {bars.map((h, i) => (
          <span key={i} className={cn("flex-1 rounded-t-[3px]", i < 13 ? "bg-danger/70" : i > 30 ? "bg-model/80" : "bg-accent/85")} style={{ height: `${Math.max(4, h * 100)}%` }} />
        ))}
      </div>
      <div className="mt-3 flex justify-between text-[12px] text-ink-400">
        <span>Bad month (P10)</span>
        <span className="text-ink-200">Typical (P50)</span>
        <span>Good month (P90)</span>
      </div>
      <figcaption className="mt-4 border-t border-white/[0.06] pt-3 text-[12px] text-ink-500">Shape for illustration only. Your project shows the computed distribution.</figcaption>
    </figure>
  );
}
