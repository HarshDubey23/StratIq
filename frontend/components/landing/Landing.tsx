"use client";

import { ArrowRight, ArrowUpRight, Footprints, Loader2, Map as MapIcon, MessageSquareText, Mic, RefreshCw, Scale, Store, Users } from "lucide-react";
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
  { key: "pizza", label: "Pizza" },
  { key: "pharmacy", label: "Pharmacies" },
  { key: "salon", label: "Salons" },
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
      { threshold: 0.15, rootMargin: "0px 0px -6% 0px" },
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
      lenis = new Lenis({ lerp: 0.09, wheelMultiplier: 0.95 }) as unknown as typeof lenis;
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
          <span style={{ transitionDelay: `${100 + i * 110}ms` }}>{l}</span>
        </span>
      ))}
    </As>
  );
}

const STEPS = [
  { n: "01", icon: MapIcon, t: "Map the market", d: "Type any business and any place. Real competitors and real population load on a 3D map in seconds." },
  { n: "02", icon: Footprints, t: "Check the street", d: "Maps miss informal shops and real prices. A researcher from your industry walks the area and records what is true." },
  { n: "03", icon: Users, t: "Let 10,000 people decide", d: "Synthetic customers with real budgets and travel times choose you, a rival, or nothing — every day for 12 weeks." },
  { n: "04", icon: Scale, t: "Decide with a range", d: "Bad month, typical month, good month. Break-even, chance of a loss, and what could make the answer wrong." },
];

const TICKER = ["Real competitors", "10,000 agents", "615 parameters each", "Field-verified ground data", "Profit range", "Break-even", "Best site", "Hinglish voice analyst"];

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

  // dark sections drive the camera of the city behind the page
  const chapters = useRef<HTMLElement[]>([]);
  useEffect(() => {
    const io = new IntersectionObserver(
      (es) => {
        for (const e of es) if (e.isIntersecting) setChapter(Number((e.target as HTMLElement).dataset.chapter || 0));
      },
      { threshold: 0.4 },
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
      const demoKind = ["cafe", "pizza", "gym"].includes(cat) ? cat : "cafe";
      const r = await fetch(`/api/v1/demo/live?spot=${spot.key}&kind=${demoKind}`, { method: "POST", credentials: "include" });
      if (!r.ok) throw new Error("Could not start the live demo. Try again in a moment.");
      const p = await r.json();
      router.push(`/app/projects/${p.id}/market`);
    } catch (e) {
      setGoErr(e instanceof Error ? e.message : "Something went wrong");
      setBusy(null);
    }
  }

  const comps = preview && preview.spot.key === spot.key ? preview.competitors : [];
  const catLabel = CATS.find((c) => c.key === cat)?.label.toLowerCase() || "businesses";

  return (
    <div className="relative bg-ink-950 text-ink-100">
      <div className="fixed inset-0 z-0">
        <HeroMap spot={spot} comps={comps} chapter={chapter} showTrips={chapter >= 1 || !loading} />
      </div>

      {/* ---------------- nav ---------------- */}
      <header className="fixed inset-x-0 top-0 z-40 border-b border-white/[0.06] bg-ink-950/55 backdrop-blur-xl">
        <nav className="mx-auto flex h-16 max-w-[1440px] items-center justify-between px-5 md:px-10">
          <Logo />
          <div className="hidden items-center gap-8 font-mono text-[11.5px] uppercase tracking-wide text-ink-300 md:flex">
            <a href="#how" className="transition-colors hover:text-ink-100"><span className="text-ink-500">01.</span> How it works</a>
            <a href="#field" className="transition-colors hover:text-ink-100"><span className="text-ink-500">02.</span> Field research</a>
            <a href="#trust" className="transition-colors hover:text-ink-100"><span className="text-ink-500">03.</span> Honesty</a>
            <Link href="/methodology" className="transition-colors hover:text-ink-100"><span className="text-ink-500">04.</span> Methodology</Link>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/sign-in" className="hidden px-3 py-2 text-[13.5px] text-ink-300 hover:text-ink-100 sm:block">Sign in</Link>
            <button onClick={() => go("new")} className="sheen inline-flex h-9 items-center gap-1.5 bg-accent px-4 font-mono text-[11.5px] font-medium uppercase tracking-wide text-white transition-colors hover:bg-[#6580ff]">
              {busy === "new" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null} Start free
            </button>
          </div>
        </nav>
      </header>

      <main className="relative z-10">
        {/* ---------------- hero ---------------- */}
        <section ref={reg(0)} data-chapter={0} className="relative flex min-h-[100svh] flex-col justify-end px-5 pb-10 pt-28 md:px-10 md:pb-12">
          <div className="mx-auto grid w-full max-w-[1440px] items-end gap-10 lg:grid-cols-[1fr_360px]">
            <div>
              <p data-reveal className="idx mb-6 flex items-center gap-3 uppercase">
                <span className="h-px w-8 bg-accent" /> Market simulation for India&apos;s small businesses
              </p>
              <Lines lines={["Test the street", "before the lease."]} className="mega text-[clamp(3rem,9.6vw,10.5rem)]" />
              <div className="mt-8 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
                <p data-reveal style={{ transitionDelay: "420ms" }} className="max-w-[30rem] text-[17px] leading-[1.55] text-ink-200">
                  Pick any business and any place. See the real competitors, the people who live there, and what 10,000 simulated customers would do — before you invest.
                </p>
              </div>
              <div data-reveal style={{ transitionDelay: "520ms" }} className="mt-8 flex flex-wrap items-center gap-3">
                <button onClick={() => go("live")} className="sheen group inline-flex h-14 items-center gap-3 bg-accent pl-6 pr-2 text-[15px] font-medium text-white shadow-[0_20px_60px_-18px_rgba(79,108,255,.9)] transition-colors hover:bg-[#6580ff]">
                  {busy === "live" ? "Opening the live market…" : "Open the live demo"}
                  <span className="flex h-10 w-10 items-center justify-center bg-white text-accent transition-transform duration-500 group-hover:rotate-45">
                    {busy === "live" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUpRight className="h-4 w-4" />}
                  </span>
                </button>
                <button onClick={() => go("new")} className="inline-flex h-14 items-center gap-2 border border-white/20 bg-ink-950/40 px-6 text-[15px] text-ink-100 backdrop-blur-md transition-colors hover:border-white/40">
                  Test my own idea <ArrowRight className="h-4 w-4" />
                </button>
                <span className="flex items-center gap-2 pl-1 text-[13px] text-ink-400"><Mic className="h-3.5 w-3.5 text-accent" /> or press V and just ask</span>
              </div>
              {goErr && <p className="mt-4 text-sm text-warn">{goErr}</p>}
            </div>

            {/* the one live number on this page */}
            <aside data-reveal style={{ transitionDelay: "650ms" }} className="panel w-full rounded-xl p-5">
              <div className="flex items-center justify-between font-mono text-[10.5px] uppercase tracking-wide text-ink-400">
                <span className="flex items-center gap-2">
                  <span className="relative flex h-2 w-2">
                    <span className={cn("absolute inline-flex h-full w-full rounded-full opacity-75", loading ? "animate-ping bg-warn" : loadErr ? "bg-danger" : "animate-ping bg-ok")} />
                    <span className={cn("relative inline-flex h-2 w-2 rounded-full", loading ? "bg-warn" : loadErr ? "bg-danger" : "bg-ok")} />
                  </span>
                  {loading ? "Fetching live" : loadErr ? "Offline" : "Live now"}
                </span>
                <span>{spot.label.split(",")[0]}</span>
              </div>
              <div className="mt-4 flex items-end gap-3">
                <span className="num font-display text-[64px] font-medium leading-none tracking-[-0.05em]">{loading ? "—" : loadErr ? "?" : comps.length}</span>
                <span className="pb-2 text-[13.5px] leading-snug text-ink-300">real {catLabel} within {((preview?.radius_m || 1600) / 1000).toFixed(1)} km</span>
              </div>
              {loadErr && (
                <button onClick={() => void load()} className="mt-2 inline-flex items-center gap-1.5 text-xs text-ink-300 hover:text-ink-100">
                  <RefreshCw className="h-3.5 w-3.5" /> {loadErr}. Retry
                </button>
              )}
              <div className="mt-5 flex flex-wrap gap-1.5">
                {CATS.map((c) => (
                  <button key={c.key} onClick={() => setCat(c.key)} className={cn("h-8 rounded-md px-3 text-[12px] transition-colors", cat === c.key ? "bg-ink-100 text-ink-950" : "bg-white/[0.05] text-ink-300 hover:text-ink-100")}>
                    {c.label}
                  </button>
                ))}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {SPOTS.map((s) => (
                  <button key={s.key} onClick={() => setSpot(s)} className={cn("h-8 rounded-md border px-3 text-[12px] transition-colors", spot.key === s.key ? "border-accent text-ink-100" : "border-white/10 text-ink-400 hover:text-ink-100")}>
                    {s.label.split(",")[1]?.trim() || s.label}
                  </button>
                ))}
              </div>
              <p className="mt-4 border-t border-white/[0.06] pt-3 text-[11px] leading-relaxed text-ink-500">
                <span className="text-observed">Amber</span> pillars: real shops from OpenStreetMap + Foursquare. <span className="text-[#9fb0ff]">Blue</span>: your site. Moving dots are simulated people.
              </p>
            </aside>
          </div>
        </section>

        {/* ---------------- ticker ---------------- */}
        <div className="relative overflow-hidden border-y border-white/10 bg-accent py-3.5">
          <div className="ticker">
            {[0, 1].map((k) => (
              <div key={k} className="flex shrink-0 items-center" aria-hidden={k === 1}>
                {TICKER.map((t) => (
                  <span key={t} className="flex items-center gap-6 px-6 font-mono text-[13px] uppercase tracking-wide text-white">
                    {t} <span className="h-1.5 w-1.5 bg-white/70" />
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>

        {/* ---------------- how it works (paper) ---------------- */}
        <section id="how" className="paper relative px-5 py-24 md:px-10 md:py-32">
          <div className="mx-auto max-w-[1440px]">
            <div className="grid gap-8 md:grid-cols-[1fr_1fr] md:items-end">
              <div>
                <p className="font-mono text-[12px] text-black/50">01/</p>
                <Lines as="h2" lines={["Four steps.", "No consultant."]} className="mega mt-3 text-[clamp(2.6rem,6.4vw,6.4rem)] text-[#111216]" />
              </div>
              <p data-reveal className="max-w-md text-[17px] leading-relaxed text-black/60 md:justify-self-end">
                What used to take a market-research firm weeks, in one guided flow. Every number says where it came from.
              </p>
            </div>
            <div className="mt-16 grid border-t border-black/15 md:grid-cols-4">
              {STEPS.map((s, i) => (
                <div key={s.n} data-reveal style={{ transitionDelay: `${i * 90}ms` }} className="group border-b border-black/15 py-8 md:border-b-0 md:border-r md:px-6 md:first:pl-0 md:last:border-r-0">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[12px] text-black/45">{s.n}/</span>
                    <s.icon className={cn("h-5 w-5 transition-transform duration-500 group-hover:-translate-y-0.5", i === 1 ? "text-[#5a7a00]" : "text-accent")} />
                  </div>
                  <h3 className="mt-10 text-[22px] font-medium leading-tight tracking-[-0.03em] text-[#111216]">{s.t}</h3>
                  <p className="mt-3 text-[14.5px] leading-relaxed text-black/60">{s.d}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ---------------- field research ---------------- */}
        <section id="field" ref={reg(1)} data-chapter={1} className="relative flex min-h-[100vh] items-center px-5 py-24 md:px-10">
          <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-r from-ink-950 via-ink-950/85 to-ink-950/30" />
          <div className="relative mx-auto grid w-full max-w-[1440px] items-center gap-14 lg:grid-cols-[1.1fr_0.9fr]">
            <div>
              <p className="idx">02/ GROUND TRUTH</p>
              <Lines as="h2" lines={["When the map", "runs out, we", "walk the street."]} className="mega mt-4 text-[clamp(2.6rem,6vw,6rem)]" />
              <p data-reveal className="mt-8 max-w-lg text-[17px] leading-[1.6] text-ink-300">
                No data for your area? Request a field researcher from <span className="text-ink-100">your own industry</span> — a gym trainer for a gym, a chef for a café. They open a link on their phone, interview people, visit every rival and count footfall. The 10,000 agents re-run on what they find.
              </p>
              <ul data-reveal className="mt-10 grid max-w-lg grid-cols-2 gap-px overflow-hidden rounded-lg border border-white/10 bg-white/10">
                {[
                  [MessageSquareText, "Street interviews", "who buys, how often, the most they'd pay"],
                  [Store, "Every rival visited", "real prices, quality, unmapped shops"],
                  [Footprints, "Footfall counts", "a tap counter at your site"],
                  [Users, "Agents re-run", "on field-verified parameters"],
                ].map(([I, t, d]) => {
                  const Icon = I as typeof Store;
                  return (
                    <li key={t as string} className="bg-ink-950 p-4">
                      <Icon className="h-4 w-4 text-field" />
                      <div className="mt-3 text-sm font-medium">{t as string}</div>
                      <div className="mt-1 text-[12.5px] text-ink-400">{d as string}</div>
                    </li>
                  );
                })}
              </ul>
            </div>
            <PhoneMock />
          </div>
        </section>

        {/* ---------------- numbers ---------------- */}
        <section ref={reg(2)} data-chapter={2} className="relative border-y border-white/10 bg-ink-950/90 px-5 py-20 backdrop-blur-sm md:px-10">
          <div className="mx-auto grid max-w-[1440px] gap-10 md:grid-cols-4">
            {[
              ["10,000", "synthetic customers per run, placed at real population density"],
              ["615", "parameters per customer — budget, travel, time, taste"],
              ["84", "simulated days of choices: you, a rival, or nothing"],
              ["800", "uncertainty runs turned into a bad, typical and good month"],
            ].map(([n, l], i) => (
              <div key={n} data-reveal style={{ transitionDelay: `${i * 80}ms` }}>
                <div className="num font-display text-[clamp(3rem,5vw,4.6rem)] font-medium leading-none tracking-[-0.05em]">{n}</div>
                <p className="mt-3 max-w-[16rem] text-[14px] leading-relaxed text-ink-400">{l}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ---------------- honesty + CTA ---------------- */}
        <section id="trust" ref={reg(3)} data-chapter={3} className="relative bg-gradient-to-b from-ink-950/70 via-ink-950 to-ink-950 px-5 pb-12 pt-28 md:px-10">
          <div className="mx-auto max-w-[1440px]">
            <div className="grid gap-12 lg:grid-cols-2">
              <div>
                <p className="idx">03/ HONESTY</p>
                <h2 data-reveal className="font-display mt-4 text-[clamp(2rem,4vw,3.4rem)] font-medium leading-[1] tracking-[-0.045em]">What StrataIQ won&apos;t pretend.</h2>
              </div>
              <ul className="divide-y divide-white/10 border-y border-white/10">
                {[
                  "It doesn't know every shop. Gaps are shown, and a field researcher can fill them.",
                  "Synthetic agents are not real people — they are a sample drawn from official aggregate data.",
                  "No accuracy percentage is advertised, because none has been measured on real outcomes yet.",
                  "A forecast is a range, never a guarantee of profit or a substitute for financial advice.",
                ].map((t, i) => (
                  <li key={t} data-reveal className="flex gap-5 py-5 text-[15px] leading-relaxed text-ink-200">
                    <span className="idx pt-0.5">0{i + 1}</span> {t}
                  </li>
                ))}
              </ul>
            </div>

            <div className="mt-32 flex flex-col items-start justify-between gap-10 md:flex-row md:items-end">
              <Lines as="h2" lines={["Run the market", "first."]} className="mega text-[clamp(3rem,8.4vw,8.8rem)]" />
              <button onClick={() => go("live")} className="sheen group inline-flex h-16 shrink-0 items-center gap-3 bg-accent pl-7 pr-2 text-base font-medium text-white transition-colors hover:bg-[#6580ff]">
                Open the live demo
                <span className="flex h-12 w-12 items-center justify-center bg-white text-accent transition-transform duration-500 group-hover:rotate-45"><ArrowUpRight className="h-5 w-5" /></span>
              </button>
            </div>

            <footer className="mt-24 flex flex-col gap-4 border-t border-white/10 pt-6 text-xs text-ink-500 md:flex-row md:items-center md:justify-between">
              <Logo />
              <p className="max-w-2xl">Map data © OpenStreetMap contributors (ODbL) · Places © Foursquare · Population © WorldPop (CC BY 4.0) · Tiles © OpenFreeMap / OpenMapTiles · Voice by ElevenLabs</p>
              <Link href="/methodology" className="hover:text-ink-200">Methodology and limitations</Link>
            </footer>
          </div>
        </section>
      </main>
    </div>
  );
}

/** Illustration of the field app (what the researcher sees on their phone). Not live data. */
function PhoneMock() {
  return (
    <div data-reveal className="relative mx-auto w-full max-w-[340px]">
      <div aria-hidden className="absolute -inset-16 rounded-full bg-field/10 blur-3xl" />
      <div className="relative overflow-hidden rounded-[34px] border border-white/15 bg-ink-900 p-3 shadow-[0_40px_120px_-30px_rgba(0,0,0,.9)]">
        <div className="rounded-[26px] border border-white/[0.06] bg-ink-950 p-5">
          <div className="flex items-center justify-between font-mono text-[10px] uppercase text-ink-500">
            <span>StrataIQ Field</span>
            <span className="flex items-center gap-1.5 text-field"><span className="h-1.5 w-1.5 rounded-full bg-field" /> collecting</span>
          </div>
          <div className="mt-4 text-[17px] font-medium leading-tight tracking-tight">Gym · Sector 18</div>
          <div className="mt-4 grid grid-cols-4 gap-1">
            {["Interview", "Rival", "Footfall", "Rent"].map((t, i) => (
              <div key={t} className={cn("rounded-md border py-2 text-center text-[10px]", i === 0 ? "border-white/25 bg-white/[0.07] text-ink-100" : "border-white/[0.06] text-ink-500")}>{t}</div>
            ))}
          </div>
          <div className="mt-5 text-[12.5px] text-ink-200"><span className="idx mr-2">01</span>Do you go to a gym now?</div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div className="rounded-md bg-field py-2.5 text-center text-[13px] font-medium text-ink-950">Yes</div>
            <div className="rounded-md border border-white/10 py-2.5 text-center text-[13px] text-ink-300">No</div>
          </div>
          <div className="mt-4 text-[12.5px] text-ink-200"><span className="idx mr-2">02</span>Most you&apos;d pay a month?</div>
          <div className="mt-2 rounded-md border border-accent bg-white/[0.03] px-3 py-2.5 font-mono text-[13px] text-ink-100">₹ 1,500<span className="ml-0.5 inline-block h-3.5 w-px animate-pulse bg-accent align-middle" /></div>
          <div className="mt-4 text-[12.5px] text-ink-200"><span className="idx mr-2">03</span>How far do you travel?</div>
          <div className="mt-2 flex gap-1.5">
            {["1 km", "2 km", "3 km", "5 km"].map((t, i) => <span key={t} className={cn("rounded-md border px-2.5 py-1.5 text-[11px]", i === 1 ? "border-accent bg-accent text-white" : "border-white/10 text-ink-400")}>{t}</span>)}
          </div>
          <div className="mt-5 rounded-md bg-accent py-3 text-center text-[13px] font-medium text-white">Save interview · 18/25</div>
        </div>
      </div>
      <p className="mt-4 text-center font-mono text-[10.5px] uppercase text-ink-500">Illustration of the field app</p>
    </div>
  );
}
