"use client";

import { ArrowDown, ArrowRight, ArrowUpRight, Loader2, Mic, RefreshCw } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Logo } from "@/components/brand";
import { cn } from "@/components/ui";
import type { Person } from "./HeroMap";
import { SPOTS, type PreviewComp, type Spot } from "./spots";

const HeroMap = dynamic(() => import("./HeroMap"), { ssr: false, loading: () => <div className="absolute inset-0 bg-ink-800" /> });

const CATS = [
  { key: "cafe", label: "Cafés" },
  { key: "gym", label: "Gyms" },
  { key: "pizza", label: "Pizza" },
  { key: "pharmacy", label: "Pharmacies" },
  { key: "salon", label: "Salons" },
];

const IDEAS = ["A gym in Bandra West, fees ₹2,000", "A café in Indiranagar, coffee at ₹250", "A salon in Sector 18, Noida", "A pharmacy near Connaught Place"];

const CHAPTERS = [
  { k: "Street", title: <>Start with the <span className="serif">real</span> street.</>, body: "Every building and road comes from OpenStreetMap. Pick any lane in India — the map is the place you'd actually sign for." },
  { k: "Rivals", title: <>Every rival, <span className="serif">counted.</span></>, body: "Competitors load live from OpenStreetMap and Foursquare. Anything the maps miss, a field researcher adds by walking the lane." },
  { k: "People", title: <>Ten thousand people, where they <span className="serif">live.</span></>, body: "Simulated customers are placed by real population data, each with a budget, habits and a limit on how far they'll travel." },
  { k: "Choice", title: <>Each one <span className="serif">chooses.</span></>, body: "You, a rival, or nothing — every day for twelve weeks. Price, distance, quality and opening hours all pull on the decision." },
  { k: "Answer", title: <>Then you get the <span className="serif">answer.</span></>, body: "Profit in a bad, normal and good month. Break-even. The best spot nearby. And exactly what could make it wrong." },
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

const reduced = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function useReveal(deps: unknown[] = []) {
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]:not(.is-in), .reveal-lines:not(.is-in)"));
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && (e.target.classList.add("is-in"), io.unobserve(e.target))),
      { threshold: 0.15, rootMargin: "0px 0px -6% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

function useLenis() {
  useEffect(() => {
    if (reduced()) return;
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

/** Cycles placeholder ideas like someone typing, so the empty box teaches what to write. */
function useTypewriter(lines: string[]) {
  const [text, setText] = useState("");
  useEffect(() => {
    if (reduced()) {
      setText(lines[0]);
      return;
    }
    let i = 0;
    let j = 0;
    let del = false;
    const id = setInterval(() => {
      const l = lines[i % lines.length];
      if (!del) {
        j++;
        if (j > l.length + 18) del = true;
      } else {
        j -= 2;
        if (j <= 0) {
          del = false;
          i++;
          j = 0;
        }
      }
      setText(l.slice(0, Math.max(0, Math.min(j, l.length))));
    }, 55);
    return () => clearInterval(id);
  }, [lines]);
  return text;
}

/** Which scroll chapter is in the middle of the screen (0 = hero). */
function useScene(count: number) {
  const [scene, setScene] = useState(0);
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>("[data-scene]"));
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => e.isIntersecting && setScene(Number((e.target as HTMLElement).dataset.scene))),
      { rootMargin: "-50% 0px -50% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [count]);
  return scene;
}

/** Buttons drift a little toward the cursor. */
function Magnetic({ children, className }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  return (
    <span
      ref={ref}
      className={cn("inline-block transition-transform duration-500 ease-[cubic-bezier(.16,1,.3,1)]", className)}
      onMouseMove={(e) => {
        if (reduced() || !ref.current) return;
        const r = ref.current.getBoundingClientRect();
        ref.current.style.transform = `translate(${(e.clientX - r.left - r.width / 2) * 0.22}px, ${(e.clientY - r.top - r.height / 2) * 0.3}px)`;
      }}
      onMouseLeave={() => ref.current && (ref.current.style.transform = "")}
    >
      {children}
    </span>
  );
}

/** Counts up once when scrolled into view. */
function CountUp({ to, className, format = (n: number) => Math.round(n).toLocaleString("en-IN") }: { to: number; className?: string; format?: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [v, setV] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reduced()) return setV(to);
    let raf = 0;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      const t0 = performance.now();
      const tick = (now: number) => {
        const k = Math.min(1, (now - t0) / 1400);
        setV(to * (1 - Math.pow(1 - k, 4)));
        if (k < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    });
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [to]);
  return <span ref={ref} className={className}>{format(v)}</span>;
}

/** Opening curtain: a counter and the wordmark, then the page lifts away. Once per session. */
function Intro() {
  const [phase, setPhase] = useState<"on" | "lift" | "off">("on");
  const [n, setN] = useState(0);
  useEffect(() => {
    let seen = false;
    try {
      seen = sessionStorage.getItem("siq-intro") === "1";
      sessionStorage.setItem("siq-intro", "1");
    } catch {
      /* storage blocked */
    }
    if (seen || reduced()) return setPhase("off");
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / 1300);
      setN(Math.round(100 * (1 - Math.pow(1 - k, 3))));
      if (k < 1) raf = requestAnimationFrame(tick);
      else setTimeout(() => setPhase("lift"), 180);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  useEffect(() => {
    if (phase !== "lift") return;
    const id = setTimeout(() => setPhase("off"), 1000);
    return () => clearTimeout(id);
  }, [phase]);
  if (phase === "off") return null;
  return (
    <div aria-hidden className={cn("intro fixed inset-0 z-[80] flex flex-col justify-between bg-ink-100 p-6 text-white md:p-10", phase === "lift" && "intro-lift")}>
      <div className="flex justify-between font-mono text-[12px] text-white/50">
        <span>StrataIQ — market simulation</span>
        <span>India · live data</span>
      </div>
      <div>
        <div className="line-mask is-in">
          <span className="intro-word font-display text-[clamp(3.5rem,13vw,13rem)] font-medium leading-[0.85] tracking-[-0.06em]">
            Strata<span className="serif text-[#8a9bff]">IQ</span>
          </span>
        </div>
        <div className="mt-6 flex items-end justify-between">
          <div className="h-px flex-1 bg-white/15">
            <div className="h-px bg-white" style={{ width: `${n}%` }} />
          </div>
          <span className="num ml-6 font-mono text-[13px] text-white/70">{String(n).padStart(3, "0")}</span>
        </div>
      </div>
    </div>
  );
}

export default function Landing() {
  const router = useRouter();
  const [spot, setSpot] = useState<Spot>(SPOTS[0]);
  const [cat, setCat] = useState("cafe");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [idea, setIdea] = useState("");
  const [busy, setBusy] = useState<null | "live" | "idea">(null);
  const [goErr, setGoErr] = useState<string | null>(null);
  const [people, setPeople] = useState<Person[]>([]);
  const placeholder = useTypewriter(IDEAS);
  const scene = useScene(CHAPTERS.length);
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

  async function simulate(text: string) {
    const t = text.trim();
    if (t.length < 3) return;
    setBusy("idea");
    setGoErr(null);
    try {
      await ensureSession();
      router.push(`/app?idea=${encodeURIComponent(t)}`);
    } catch (e) {
      setGoErr(e instanceof Error ? e.message : "Something went wrong");
      setBusy(null);
    }
  }

  async function liveDemo() {
    setBusy("live");
    setGoErr(null);
    try {
      await ensureSession();
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
  const share = (c: Person["choice"]) => (people.length ? Math.round((100 * people.filter((p) => p.choice === c).length) / people.length) : 0);
  const area = spot.label.split(",")[0];

  return (
    <div className="relative bg-ink-950 text-ink-100">
      <Intro />

      {/* ---------------- nav (floats over the city) ---------------- */}
      <header className="fixed inset-x-0 top-0 z-40">
        <nav className="mx-auto mt-3 flex h-14 max-w-[1320px] items-center justify-between rounded-full px-3 md:px-4">
          <div className="panel flex h-11 items-center rounded-full px-4"><Logo /></div>
          <div className="panel hidden h-11 items-center gap-7 rounded-full px-6 text-[14px] text-ink-300 md:flex">
            <a href="#story" className="transition-colors hover:text-ink-100">How it works</a>
            <a href="#field" className="transition-colors hover:text-ink-100">Field research</a>
            <a href="#voice" className="transition-colors hover:text-ink-100">Voice</a>
            <Link href="/methodology" className="transition-colors hover:text-ink-100">Methodology</Link>
          </div>
          <div className="panel flex h-11 items-center gap-1 rounded-full p-1">
            <Link href="/sign-in" className="hidden h-9 items-center rounded-full px-4 text-[14px] text-ink-200 transition-colors hover:bg-black/[0.05] sm:inline-flex">Sign in</Link>
            <Link href="/sign-up" className="inline-flex h-9 items-center rounded-full bg-ink-100 px-4 text-[14px] font-medium text-white transition-colors hover:bg-black">Start free</Link>
          </div>
        </nav>
      </header>

      <main>
        {/* ---------------- the stage: one pinned 3D city under the hero and the story ---------------- */}
        <div className="relative">
          <div className="sticky top-0 h-[100svh] overflow-hidden">
            <HeroMap spot={spot} comps={comps} scene={scene} onPeople={setPeople} />
            {/* chapter rail */}
            <ol className={cn("pointer-events-none absolute right-5 top-1/2 hidden -translate-y-1/2 flex-col gap-3 transition-opacity duration-700 md:flex", scene > 0 ? "opacity-100" : "opacity-0")} aria-hidden>
              {CHAPTERS.map((c, i) => (
                <li key={c.k} className="flex items-center justify-end gap-3">
                  <span className={cn("font-mono text-[11px] transition-all duration-500", scene === i + 1 ? "translate-x-0 text-ink-100 opacity-100" : "translate-x-2 text-ink-400 opacity-0")}>{c.k}</span>
                  <span className={cn("h-px transition-all duration-500", scene === i + 1 ? "w-10 bg-accent" : scene > i + 1 ? "w-5 bg-ink-100" : "w-5 bg-ink-500")} />
                </li>
              ))}
            </ol>
          </div>

          <div className="relative -mt-[100svh]">
            {/* ---------------- hero ---------------- */}
            <section data-scene={0} className="relative flex min-h-[100svh] flex-col justify-end pb-8 pt-28 md:pb-10">
              <div aria-hidden className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,#F5F3EE_0%,rgba(245,243,238,.92)_30%,rgba(245,243,238,.35)_58%,rgba(245,243,238,0)_75%)] max-md:bg-[linear-gradient(180deg,rgba(245,243,238,.2)_0%,rgba(245,243,238,.9)_45%,#F5F3EE_100%)]" />
              <div className="relative mx-auto w-full max-w-[1320px] px-5 md:px-8">
                <p data-reveal className="inline-flex items-center gap-2 rounded-full border border-black/[0.08] bg-white/80 px-3 py-1.5 text-[13px] text-ink-300 backdrop-blur">
                  <span className="relative flex h-1.5 w-1.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ok opacity-60" /><span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-ok" /></span>
                  Live market data for any street in India
                </p>
                <h1 className="reveal-lines mt-6 max-w-[1000px] font-display text-[clamp(3rem,8vw,8.4rem)] font-medium leading-[0.9] tracking-[-0.06em]">
                  <span className="line-mask"><span style={{ transitionDelay: "120ms" }}>Know if your shop</span></span>
                  <span className="line-mask"><span style={{ transitionDelay: "220ms" }}>will <span className="serif text-accent">work</span>,</span></span>
                  <span className="line-mask"><span style={{ transitionDelay: "320ms" }} className="text-[0.52em] leading-[1.1] tracking-[-0.04em] text-ink-300">before you sign the lease.</span></span>
                </h1>

                <div className="mt-8 grid items-end gap-6 lg:grid-cols-[minmax(0,640px)_1fr]">
                  <div>
                    <form
                      data-reveal
                      style={{ transitionDelay: "420ms" }}
                      onSubmit={(e) => { e.preventDefault(); void simulate(idea || placeholder); }}
                      className="flex flex-col gap-2 rounded-2xl border border-black/[0.08] bg-white p-2 shadow-[0_1px_2px_rgba(20,18,10,.04),0_24px_60px_-28px_rgba(20,18,10,.3)] sm:flex-row"
                    >
                      <label htmlFor="idea" className="sr-only">Your business idea</label>
                      <input
                        id="idea"
                        value={idea}
                        onChange={(e) => setIdea(e.target.value)}
                        placeholder={placeholder || " "}
                        className="h-14 min-w-0 flex-1 rounded-xl bg-transparent px-4 text-[17px] outline-none placeholder:text-ink-500"
                      />
                      <Magnetic className="w-full sm:w-auto">
                        <button type="submit" className="sheen inline-flex h-14 w-full shrink-0 items-center justify-center gap-2 rounded-xl bg-accent px-6 text-[16px] font-medium text-white transition-colors hover:bg-[#2238e0]">
                          {busy === "idea" ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Simulate my idea <ArrowRight className="h-4 w-4" />
                        </button>
                      </Magnetic>
                    </form>
                    <div data-reveal style={{ transitionDelay: "480ms" }} className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-[14px] text-ink-400">
                      <button onClick={liveDemo} className="inline-flex items-center gap-1.5 font-medium text-ink-100 underline decoration-black/20 underline-offset-4 transition-colors hover:decoration-black">
                        {busy === "live" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null} Open the live demo
                      </button>
                      <span className="inline-flex items-center gap-1.5"><Mic className="h-3.5 w-3.5 text-accent" /> or press <kbd className="rounded border border-black/15 bg-white px-1.5 font-mono text-[11px] text-ink-200">V</kbd> and say it in Hinglish</span>
                      {goErr && <span className="text-danger">{goErr}</span>}
                    </div>
                  </div>

                  {/* live data ticket: change the street and the category, the city above reloads */}
                  <div data-reveal style={{ transitionDelay: "560ms" }} className="panel w-full max-w-[420px] justify-self-end rounded-2xl p-4">
                    <div className="flex items-center justify-between text-[12px] text-ink-400">
                      <span className="flex items-center gap-2">
                        <span className={cn("h-1.5 w-1.5 rounded-full", loading ? "animate-pulse bg-warn" : loadErr ? "bg-danger" : "bg-ok")} />
                        {loading ? "Fetching live…" : loadErr ? "Live data offline" : "Live · OpenStreetMap + Foursquare"}
                      </span>
                      {loadErr && <button onClick={() => void load()} className="inline-flex items-center gap-1 hover:text-ink-100"><RefreshCw className="h-3 w-3" /> Retry</button>}
                    </div>
                    <div className="mt-2 flex items-end gap-3">
                      <span className="num font-display text-[54px] font-medium leading-none tracking-[-0.05em]">{loading ? "—" : loadErr ? "?" : comps.length}</span>
                      <span className="pb-1 text-[13.5px] leading-tight text-ink-300">real {catLabel}<br />around {area}</span>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-1">
                      {SPOTS.map((s) => (
                        <button key={s.key} onClick={() => setSpot(s)} className={cn("h-7 rounded-full px-2.5 text-[12.5px] transition-colors", spot.key === s.key ? "bg-ink-100 text-white" : "bg-black/[0.04] text-ink-300 hover:bg-black/[0.08]")}>
                          {s.label.split(",")[0]}
                        </button>
                      ))}
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {CATS.map((c) => (
                        <button key={c.key} onClick={() => setCat(c.key)} className={cn("h-7 rounded-full border px-2.5 text-[12.5px] transition-colors", cat === c.key ? "border-accent bg-accent-dim text-accent" : "border-transparent text-ink-300 hover:bg-black/[0.05]")}>
                          {c.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <a href="#story" className="mt-10 hidden items-center gap-2 text-[13px] text-ink-400 transition-colors hover:text-ink-100 md:inline-flex">
                  <span className="flex h-8 w-8 items-center justify-center rounded-full border border-black/10 bg-white/70"><ArrowDown className="scroll-cue h-3.5 w-3.5" /></span>
                  Scroll to walk the street
                </a>
              </div>
            </section>

            {/* ---------------- the story: the city above changes with each chapter ---------------- */}
            <div id="story">
              {CHAPTERS.map((c, i) => (
                <section key={c.k} data-scene={i + 1} className={cn("flex min-h-[115svh] items-center px-5 md:px-8", i % 2 ? "md:justify-end" : "md:justify-start")}>
                  <div className={cn("mx-auto w-full max-w-[1320px]", i % 2 && "flex md:justify-end")}>
                    <article data-reveal className="panel w-full max-w-[460px] rounded-[28px] p-7 md:p-9">
                      <div className="flex items-center justify-between font-mono text-[12px] text-ink-400">
                        <span>({String(i + 1).padStart(2, "0")})</span>
                        <span>{c.k}</span>
                      </div>
                      <h2 className="mt-8 font-display text-[clamp(2rem,3.6vw,3.2rem)] font-medium leading-[0.98] tracking-[-0.05em]">{c.title}</h2>
                      <p className="mt-4 text-[16px] leading-relaxed text-ink-300">{c.body}</p>
                      <ChapterStat i={i} area={area} comps={comps.length} loading={loading} catLabel={catLabel} share={share} />
                    </article>
                  </div>
                </section>
              ))}
            </div>
          </div>
        </div>

        {/* ---------------- marquee ---------------- */}
        <section aria-label="Categories" className="overflow-hidden border-y border-black/[0.07] bg-white py-8">
          <div className="ticker">
            {[0, 1].map((k) => (
              <div key={k} className="flex shrink-0 items-center gap-10 pr-10 font-display text-[clamp(2.4rem,5vw,4.6rem)] font-medium tracking-[-0.05em]">
                {["Cafés", "Gyms", "Clinics", "Salons", "Pharmacies", "Bakeries", "Pizza", "Coaching", "Kirana"].map((w, j) => (
                  <span key={w} className="flex items-center gap-10">
                    <span className={j % 2 ? "serif text-ink-400" : ""}>{w}</span>
                    <span className="h-2.5 w-2.5 rounded-full bg-accent" />
                  </span>
                ))}
              </div>
            ))}
          </div>
        </section>

        {/* ---------------- field research ---------------- */}
        <section id="field" className="mx-auto grid max-w-[1320px] items-center gap-14 px-5 py-28 md:px-8 md:py-36 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <p data-reveal className="font-mono text-[12px] text-field">(06) Field research</p>
            <h2 className="reveal-lines mt-5 font-display text-[clamp(2.4rem,5vw,4.6rem)] font-medium leading-[0.95] tracking-[-0.055em]">
              <span className="line-mask"><span>When the map runs out,</span></span>
              <span className="line-mask"><span style={{ transitionDelay: "100ms" }}>a person <span className="serif text-field">walks</span> the street.</span></span>
            </h2>
            <p data-reveal className="mt-6 max-w-lg text-[17px] leading-relaxed text-ink-300">
              No data for your lane? Request a researcher from your own industry — a trainer for a gym, a chef for a café. They open a link on their phone, interview people, visit every rival and count footfall. Your simulation re-runs on what they find.
            </p>
            <dl className="mt-10 grid max-w-lg grid-cols-2 gap-x-8 gap-y-6">
              {[
                ["Interviews", "who buys, how often, the most they'd pay"],
                ["Rival visits", "real prices, quality, unmapped shops"],
                ["Footfall", "a tap counter at your site"],
                ["Re-run", "agents switch to street data"],
              ].map(([t, d], i) => (
                <div key={t} data-reveal style={{ transitionDelay: `${i * 80}ms` }} className="border-t border-black/[0.1] pt-3">
                  <dt className="text-[15px] font-medium">{t}</dt>
                  <dd className="mt-1 text-[14px] text-ink-400">{d}</dd>
                </div>
              ))}
            </dl>
          </div>
          <PhoneMock />
        </section>

        {/* ---------------- voice ---------------- */}
        <section id="voice" className="relative overflow-hidden bg-ink-100 text-white">
          <div className="mx-auto grid max-w-[1320px] gap-14 px-5 py-28 md:px-8 md:py-36 lg:grid-cols-2 lg:items-center">
            <div>
              <p className="font-mono text-[12px] text-[#8a9bff]">(07) Strata, the voice analyst</p>
              <h2 className="reveal-lines mt-5 font-display text-[clamp(2.6rem,6vw,5.6rem)] font-medium leading-[0.92] tracking-[-0.055em]">
                <span className="line-mask"><span>Don&apos;t click.</span></span>
                <span className="line-mask"><span style={{ transitionDelay: "100ms" }}>Just <span className="serif text-[#8a9bff]">talk.</span></span></span>
              </h2>
              <Wave />
              <p data-reveal className="mt-8 max-w-md text-[17px] leading-relaxed text-white/60">
                Strata runs the whole app by voice — starts your project, loads the market, changes your rent, finds the best spot, sends a field researcher and builds the report. In proper Hinglish, with numbers only from the simulation.
              </p>
              <p data-reveal className="mt-6 text-[14px] text-white/50">Press <kbd className="rounded border border-white/20 px-1.5 font-mono text-[12px] text-white">V</kbd> anywhere to start.</p>
            </div>
            <div className="space-y-3 text-[16px]">
              <Bubble you d={0}>Mujhe Indiranagar me café kholna hai, coffee 250 ki.</Bubble>
              <Bubble d={1}>Theek hai, project bana raha hoon aur live market load kar raha hoon — ek minute.</Bubble>
              <Bubble you d={2}>Rent actually 90 hazaar hai, update kar do.</Bubble>
              <Bubble d={3}>Update kar diya aur dobara simulate kiya. Rent badhne se profit kam hua — break-even ab zyada customers pe aayega. Best location bhi check karein?</Bubble>
            </div>
          </div>
        </section>

        {/* ---------------- honesty ---------------- */}
        <section className="mx-auto max-w-[1320px] px-5 py-28 md:px-8 md:py-36">
          <div className="grid gap-10 md:grid-cols-[1fr_1.4fr]">
            <div>
              <p data-reveal className="font-mono text-[12px] text-ink-400">(08) Honesty</p>
              <h2 data-reveal className="mt-5 font-display text-[clamp(2.2rem,4vw,3.6rem)] font-medium leading-[0.98] tracking-[-0.05em]">What it won&apos;t <span className="serif">pretend.</span></h2>
            </div>
            <ul className="grid gap-x-10 gap-y-7 sm:grid-cols-2">
              {[
                ["Every shop", "Maps miss informal businesses. Gaps are flagged, and a field researcher can fill them."],
                ["Real people", "Simulated customers are a sample drawn from official data — never real individuals."],
                ["An accuracy score", "None is advertised, because none has been measured on real outcomes yet."],
                ["A promise", "Every forecast is a range under stated assumptions, not a guarantee of profit."],
              ].map(([t, d], i) => (
                <li key={t} data-reveal style={{ transitionDelay: `${i * 70}ms` }} className="border-t border-black/[0.1] pt-4">
                  <div className="text-[15px] font-medium">{t}</div>
                  <p className="mt-1 text-[14.5px] leading-relaxed text-ink-400">{d}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ---------------- CTA ---------------- */}
        <section className="mx-auto max-w-[1320px] px-5 md:px-8">
          <div data-reveal className="relative overflow-hidden rounded-[36px] bg-accent px-6 py-20 text-white md:px-16 md:py-28">
            <div aria-hidden className="pointer-events-none absolute inset-0 opacity-50 [mask-image:radial-gradient(70%_80%_at_80%_20%,black,transparent)]" style={{ backgroundImage: "linear-gradient(to right, rgba(255,255,255,.12) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,.12) 1px, transparent 1px)", backgroundSize: "56px 56px" }} />
            <div aria-hidden className="cta-orb pointer-events-none absolute -right-24 -top-24 h-[420px] w-[420px] rounded-full bg-[radial-gradient(circle,rgba(255,255,255,.35),transparent_65%)]" />
            <h2 className="relative max-w-3xl font-display text-[clamp(2.8rem,7vw,6.4rem)] font-medium leading-[0.92] tracking-[-0.06em]">
              Run the market <span className="serif">first.</span>
            </h2>
            <p className="relative mt-5 max-w-md text-[17px] text-white/75">Three minutes, one line of text. Before the deposit, before the fit-out.</p>
            <div className="relative mt-10 flex flex-wrap gap-3">
              <Magnetic>
                <Link href="/sign-up" className="inline-flex h-14 items-center gap-2 rounded-full bg-white px-7 text-[16px] font-medium text-accent">
                  Start free <ArrowUpRight className="h-4 w-4" />
                </Link>
              </Magnetic>
              <button onClick={liveDemo} className="inline-flex h-14 items-center gap-2 rounded-full border border-white/30 px-7 text-[16px] text-white transition-colors hover:bg-white/10">
                {busy === "live" ? <Loader2 className="h-4 w-4 animate-spin" /> : null} See the live demo
              </button>
            </div>
          </div>
        </section>

        {/* ---------------- footer ---------------- */}
        <footer className="mx-auto max-w-[1320px] px-5 pb-8 pt-20 md:px-8">
          <div className="flex flex-col gap-4 text-[12.5px] text-ink-400 md:flex-row md:items-center md:justify-between">
            <p className="max-w-2xl">Map data © OpenStreetMap contributors (ODbL) · Places © Foursquare · Population © WorldPop (CC BY 4.0) · Tiles © OpenFreeMap / OpenMapTiles · Voice by ElevenLabs</p>
            <div className="flex gap-5">
              <Link href="/methodology" className="hover:text-ink-100">Methodology & limitations</Link>
              <Link href="/sign-in" className="hover:text-ink-100">Sign in</Link>
            </div>
          </div>
          <div className="reveal-lines mt-10 select-none" aria-hidden>
            <span className="line-mask">
              <span className="block font-display text-[21vw] font-medium leading-[0.8] tracking-[-0.075em] text-ink-100 xl:text-[270px]">
                Strata<span className="serif text-accent">IQ</span>
              </span>
            </span>
          </div>
        </footer>
      </main>
    </div>
  );
}

/** One fact per chapter. Chapter 4's shares come from the drawing above and say so. */
function ChapterStat({ i, area, comps, loading, catLabel, share }: { i: number; area: string; comps: number; loading: boolean; catLabel: string; share: (c: Person["choice"]) => number }) {
  const box = "mt-7 border-t border-black/[0.08] pt-5";
  if (i === 0) return <div className={box}><div className="font-mono text-[12px] text-ink-400">Now showing</div><div className="mt-1 font-display text-[28px] font-medium tracking-[-0.04em]">{area}</div></div>;
  if (i === 1)
    return (
      <div className={cn(box, "flex items-end gap-3")}>
        <span className="num font-display text-[64px] font-medium leading-none tracking-[-0.05em] text-[#d97706]">{loading ? "—" : <CountUp key={comps} to={comps} />}</span>
        <span className="pb-1.5 text-[14px] leading-tight text-ink-300">real {catLabel}<br />loaded live around {area}</span>
      </div>
    );
  if (i === 2)
    return (
      <div className={cn(box, "flex items-end gap-3")}>
        <span className="num font-display text-[64px] font-medium leading-none tracking-[-0.05em] text-agent"><CountUp to={10000} /></span>
        <span className="pb-1.5 text-[14px] leading-tight text-ink-300">simulated customers<br />per run, from WorldPop</span>
      </div>
    );
  if (i === 3)
    return (
      <div className={box}>
        <div className="flex h-2.5 overflow-hidden rounded-full bg-black/[0.06]">
          <span className="bg-accent transition-all duration-1000" style={{ width: `${share("you")}%` }} />
          <span className="bg-agent transition-all duration-1000" style={{ width: `${share("rival")}%` }} />
          <span className="bg-ink-500 transition-all duration-1000" style={{ width: `${share("none")}%` }} />
        </div>
        <div className="mt-3 grid grid-cols-3 text-[13px]">
          <span><b className="num font-medium">{share("you")}%</b> <span className="text-ink-400">you</span></span>
          <span><b className="num font-medium">{share("rival")}%</b> <span className="text-ink-400">a rival</span></span>
          <span><b className="num font-medium">{share("none")}%</b> <span className="text-ink-400">nothing</span></span>
        </div>
        <p className="mt-3 text-[12px] text-ink-400">Illustration on this page. The real run uses the calibrated choice model.</p>
      </div>
    );
  return (
    <ul className={cn(box, "space-y-2 text-[14.5px]")}>
      {["Profit · bad / normal / good month", "Break-even customers and months", "Best spot within your catchment", "What would change the answer"].map((t, k) => (
        <li key={t} className="flex items-center gap-3"><span className="font-mono text-[11px] text-ink-400">{String(k + 1).padStart(2, "0")}</span>{t}</li>
      ))}
    </ul>
  );
}

function Wave() {
  return (
    <div aria-hidden className="mt-8 flex h-10 items-center gap-[5px]">
      {Array.from({ length: 28 }, (_, i) => (
        <span key={i} className="wave-bar w-[3px] rounded-full bg-[#8a9bff]" style={{ animationDelay: `${(i * 73) % 900}ms`, height: `${30 + ((i * 37) % 70)}%` }} />
      ))}
    </div>
  );
}

function Bubble({ you, d = 0, children }: { you?: boolean; d?: number; children: React.ReactNode }) {
  return (
    <div data-reveal style={{ transitionDelay: `${d * 260}ms` }} className={cn("w-fit max-w-[88%] rounded-3xl px-5 py-3.5 leading-snug", you ? "ml-auto rounded-br-md bg-white/10 text-white" : "rounded-bl-md bg-white text-ink-100")}>
      {children}
    </div>
  );
}

/** Illustration of the field researcher's phone app (not live data). */
function PhoneMock() {
  return (
    <div data-reveal className="relative mx-auto w-full max-w-[330px]">
      <div aria-hidden className="absolute -inset-10 -z-10 rounded-full bg-[radial-gradient(circle,rgba(63,122,20,.14),transparent_65%)]" />
      <div className="phone-float relative rounded-[40px] border border-black/[0.08] bg-ink-800 p-2.5 shadow-[0_40px_90px_-40px_rgba(20,18,10,.45)]">
        <div className="rounded-[32px] bg-white p-5">
          <div className="flex items-center justify-between text-[11px] text-ink-400">
            <span className="font-medium text-ink-200">StrataIQ Field</span>
            <span className="flex items-center gap-1.5 text-field"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-field" /> collecting</span>
          </div>
          <div className="mt-4 text-[18px] font-medium leading-tight tracking-[-0.02em]">Gym · Sector 18</div>
          <div className="mt-4 grid grid-cols-4 gap-1 rounded-xl bg-ink-800 p-1">
            {["Interview", "Rival", "Footfall", "Rent"].map((t, i) => (
              <div key={t} className={cn("rounded-lg py-1.5 text-center text-[10.5px]", i === 0 ? "bg-white font-medium text-ink-100 shadow-sm" : "text-ink-400")}>{t}</div>
            ))}
          </div>
          <div className="mt-5 text-[13px] text-ink-200">Do you go to a gym now?</div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div className="rounded-xl bg-field py-2.5 text-center text-[13px] font-medium text-white">Yes</div>
            <div className="rounded-xl border border-black/10 py-2.5 text-center text-[13px] text-ink-300">No</div>
          </div>
          <div className="mt-4 text-[13px] text-ink-200">Most you&apos;d pay a month?</div>
          <div className="mt-2 rounded-xl border border-accent px-3 py-2.5 font-mono text-[13px]">₹ 1,500<span className="ml-0.5 inline-block h-3.5 w-px animate-pulse bg-accent align-middle" /></div>
          <div className="mt-4 text-[13px] text-ink-200">How far do you travel?</div>
          <div className="mt-2 flex gap-1.5">
            {["1 km", "2 km", "3 km", "5 km"].map((t, i) => <span key={t} className={cn("rounded-full border px-2.5 py-1 text-[11px]", i === 1 ? "border-accent bg-accent text-white" : "border-black/10 text-ink-400")}>{t}</span>)}
          </div>
          <div className="mt-5 rounded-xl bg-ink-100 py-3 text-center text-[13px] font-medium text-white">Save interview · 18/25</div>
        </div>
      </div>
      <p className="mt-4 text-center text-[12px] text-ink-400">Illustration of the field app</p>
    </div>
  );
}
