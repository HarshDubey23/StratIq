"use client";

import { ArrowUpRight, Loader2, Mic, RefreshCw } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/components/ui";
import { SPOTS, type PreviewComp, type Spot } from "./spots";

const HeroMap = dynamic(() => import("./HeroMap"), { ssr: false, loading: () => null });

const CATS = [
  { key: "cafe", label: "Cafés" },
  { key: "gym", label: "Gyms" },
  { key: "pizza", label: "Pizza" },
  { key: "pharmacy", label: "Pharmacies" },
  { key: "salon", label: "Salons" },
];

const IDEAS = ["A gym in Bandra West, fees ₹2,000", "A café in Indiranagar, coffee at ₹250", "A salon in Sector 18, Noida", "A pharmacy near Connaught Place"];

const CHAPTERS = [
  { title: "Start with the real street.", body: "Every building and road comes from OpenStreetMap. Pick any lane in India — the one you'd actually sign for." },
  { title: "Every rival, counted.", body: "Competitors load live from OpenStreetMap and Foursquare. Anything the maps miss, a field researcher adds by walking the lane." },
  { title: "Ten thousand people, where they live.", body: "Simulated customers are placed by real population data, each with a budget, habits and a limit on how far they'll travel." },
  { title: "Each one chooses.", body: "You, a rival, or nothing — every day for twelve weeks. Price, distance, quality and opening hours all pull on the decision." },
  { title: "Then you get the answer.", body: "Profit in a bad, normal and good month. Break-even. The best spot nearby. And what could make it wrong." },
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

function useLenis() {
  useEffect(() => {
    if (reduced()) return;
    let raf = 0;
    let lenis: { raf: (t: number) => void; destroy: () => void } | null = null;
    import("lenis").then(({ default: Lenis }) => {
      lenis = new Lenis({ lerp: 0.085, wheelMultiplier: 0.9 }) as unknown as typeof lenis;
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

/** Scroll position as a chapter number with a fraction (0 = hero, 5 = last chapter), plus the nearest whole chapter. */
function useStoryProgress() {
  const progress = useRef(0);
  const [scene, setScene] = useState(0);
  useEffect(() => {
    const els = Array.from(document.querySelectorAll<HTMLElement>("[data-scene]"));
    const on = () => {
      const mid = window.innerHeight / 2;
      let p = els.length - 1;
      for (let i = 0; i < els.length; i++) {
        const r = els[i].getBoundingClientRect();
        if (r.top > mid) {
          p = i - 0.5;
          break;
        }
        if (r.bottom > mid) {
          p = i + (mid - r.top) / r.height - 0.5;
          break;
        }
      }
      progress.current = Math.max(0, Math.min(els.length - 1, p));
      setScene(Math.round(progress.current));
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => {
      window.removeEventListener("scroll", on);
      window.removeEventListener("resize", on);
    };
  }, []);
  return { progress, scene };
}

/** Opening: blueprint lines draw across the blue, the wordmark sets, the sheet lifts. Once per session. */
function Intro({ onDone }: { onDone: () => void }) {
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
    if (seen || reduced()) {
      setPhase("off");
      onDone();
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / 1500);
      setN(Math.round(100 * (1 - Math.pow(1 - k, 3))));
      if (k < 1) raf = requestAnimationFrame(tick);
      else setTimeout(() => setPhase("lift"), 150);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (phase !== "lift") return;
    onDone();
    const id = setTimeout(() => setPhase("off"), 1100);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase]);
  if (phase === "off") return null;
  return (
    <div aria-hidden className={cn("lp-intro fixed inset-0 z-[80] overflow-hidden bg-[#2F49FF] text-white", phase === "lift" && "is-lift")}>
      {[18, 34, 50, 66, 82].map((y, i) => <span key={`h${y}`} className="lp-rule-h" style={{ top: `${y}%`, animationDelay: `${i * 90}ms` }} />)}
      {[12, 30, 48, 66, 84].map((x, i) => <span key={`v${x}`} className="lp-rule-v" style={{ left: `${x}%`, animationDelay: `${120 + i * 90}ms` }} />)}
      <div className="absolute inset-x-6 bottom-8 md:inset-x-10 md:bottom-10">
        <div className="overflow-hidden">
          <div className="lp-wide lp-intro-word text-[clamp(3.6rem,15vw,15rem)] leading-[0.82]">StrataIQ</div>
        </div>
        <div className="mt-5 flex items-center gap-6">
          <div className="h-px flex-1 bg-white/25"><div className="h-px bg-white" style={{ width: `${n}%` }} /></div>
          <span className="lp-num lp-cond text-[15px]">{n}</span>
        </div>
      </div>
    </div>
  );
}

/** Headline set letter by letter when the page opens: the one orchestrated moment. */
function Rise({ text, go, delay = 0 }: { text: string; go: boolean; delay?: number }) {
  return (
    <span aria-label={text} className={cn("lp-rise", go && "is-go")}>
      {text.split("").map((c, i) => (
        <span key={i} aria-hidden style={{ transitionDelay: `${delay + i * 28}ms` }}>{c === " " ? " " : c}</span>
      ))}
    </span>
  );
}

function Wordmark() {
  return (
    <Link href="/" aria-label="StrataIQ home" className="flex items-center gap-2.5 text-white">
      <svg width="26" height="26" viewBox="0 0 32 32" fill="none" aria-hidden>
        <path d="M4 20.5 16 26l12-5.5" stroke="currentColor" strokeOpacity=".45" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M4 15.5 16 21l12-5.5" stroke="currentColor" strokeOpacity=".7" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M4 10.5 16 16l12-5.5L16 5 4 10.5Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
        <circle cx="16" cy="10.6" r="2.2" fill="currentColor" />
      </svg>
      <span className="lp-wide text-[17px] tracking-[-0.02em]">StrataIQ</span>
    </Link>
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
  const [opened, setOpened] = useState(false);
  const placeholder = useTypewriter(IDEAS);
  const { progress, scene } = useStoryProgress();
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
  const area = spot.label.split(",")[0];

  return (
    <div className="lp relative">
      <Intro onDone={() => setOpened(true)} />

      <header className="fixed inset-x-0 top-0 z-40">
        <nav className="mx-auto flex h-[72px] max-w-[1400px] items-center justify-between px-5 md:px-10">
          <Wordmark />
          <div className="hidden items-center gap-8 text-[14.5px] text-white/75 md:flex">
            <a href="#story" className="lp-link">How it works</a>
            <a href="#field" className="lp-link">Field research</a>
            <a href="#voice" className="lp-link">Voice</a>
            <Link href="/methodology" className="lp-link">Methodology</Link>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/sign-in" className="hidden h-10 items-center px-3 text-[14.5px] text-white/80 transition-colors hover:text-white sm:inline-flex">Sign in</Link>
            <Link href="/sign-up" className="inline-flex h-10 items-center rounded-full bg-white px-5 text-[14.5px] font-semibold text-[#2F49FF] transition-transform hover:scale-[1.03]">Start free</Link>
          </div>
        </nav>
      </header>

      <main>
        {/* ---------------- the stage: one pinned blueprint city under the hero and the story ---------------- */}
        <div className="relative">
          <div className="sticky top-0 h-[100svh] overflow-hidden">
            <HeroMap spot={spot} comps={comps} scene={scene} progress={progress} />
            <div aria-hidden className="lp-grid pointer-events-none absolute inset-0" />
            <div aria-hidden className={cn("pointer-events-none absolute inset-0 transition-opacity duration-700", scene === 0 ? "opacity-100" : "opacity-0")} style={{ background: "radial-gradient(90% 75% at 0% 100%, rgba(16,28,160,.9), rgba(16,28,160,.35) 45%, transparent 70%)" }} />
            <ol aria-hidden className={cn("pointer-events-none absolute right-5 top-1/2 hidden -translate-y-1/2 flex-col gap-3 transition-opacity duration-700 md:flex md:right-10", scene > 0 ? "opacity-100" : "opacity-0")}>
              {CHAPTERS.map((c, i) => (
                <li key={c.title} className={cn("h-px transition-all duration-500", scene === i + 1 ? "w-12 bg-white" : scene > i + 1 ? "w-6 bg-white/70" : "w-6 bg-white/30")} />
              ))}
            </ol>
            <div aria-hidden className="lp-num absolute bottom-5 right-5 hidden text-[12px] text-white/60 md:right-10 md:block">
              {spot.lat.toFixed(4)}° N&nbsp;&nbsp;{spot.lng.toFixed(4)}° E
            </div>
          </div>

          <div className="relative -mt-[100svh]">
            {/* ---------------- hero ---------------- */}
            <section data-scene={0} className="relative flex min-h-[100svh] flex-col justify-end pb-10 pt-28 md:pb-14">
              <div className="mx-auto grid w-full max-w-[1400px] items-end gap-10 px-5 md:px-10 lg:grid-cols-[1fr_380px]">
                <div>
                  <h1 className="lp-wide text-[clamp(3.4rem,10vw,10.5rem)] leading-[0.84] tracking-[-0.045em] text-white">
                    <Rise text="Test the" go={opened} />
                    <br />
                    <Rise text="street." go={opened} delay={220} />
                  </h1>
                  <p className={cn("lp-fade mt-7 max-w-[30rem] text-[clamp(1.15rem,1.6vw,1.45rem)] leading-[1.35] text-white", opened && "is-go")} style={{ transitionDelay: "600ms" }}>
                    Know if your shop will work, before you sign the lease.
                  </p>
                  <form
                    onSubmit={(e) => { e.preventDefault(); void simulate(idea || placeholder); }}
                    className={cn("lp-fade mt-7 flex max-w-[640px] flex-col gap-1.5 rounded-[10px] bg-white p-1.5 sm:flex-row", opened && "is-go")}
                    style={{ transitionDelay: "720ms" }}
                  >
                    <label htmlFor="idea" className="sr-only">Your business idea</label>
                    <input
                      id="idea"
                      value={idea}
                      onChange={(e) => setIdea(e.target.value)}
                      placeholder={placeholder || " "}
                      className="h-14 min-w-0 flex-1 bg-transparent px-4 text-[17px] text-black outline-none placeholder:text-black/40"
                    />
                    <button type="submit" className="inline-flex h-14 shrink-0 items-center justify-center gap-2 rounded-[7px] bg-black px-6 text-[16px] font-semibold text-white transition-colors hover:bg-[#1a1a1a]">
                      {busy === "idea" && <Loader2 className="h-4 w-4 animate-spin" />} Simulate my idea
                    </button>
                  </form>
                  <div className={cn("lp-fade mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 text-[14.5px] text-white/75", opened && "is-go")} style={{ transitionDelay: "820ms" }}>
                    <button onClick={liveDemo} className="inline-flex items-center gap-1.5 font-semibold text-white underline decoration-white/40 underline-offset-[5px] transition-colors hover:decoration-white">
                      {busy === "live" && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Open the live demo
                    </button>
                    <span className="inline-flex items-center gap-2"><Mic className="h-4 w-4" /> Or press <kbd className="rounded-[4px] border border-white/40 px-1.5 text-[12px] text-white">V</kbd> and say it in Hinglish</span>
                    {goErr && <span className="rounded bg-black px-2 py-0.5 text-white">{goErr}</span>}
                  </div>
                </div>

                {/* live billboard: the city above is this street, these rivals */}
                <aside className={cn("lp-fade w-full rounded-[6px] bg-black p-5 text-white", opened && "is-go")} style={{ transitionDelay: "900ms" }}>
                  <div className="flex items-center justify-between text-[13px] text-white/60">
                    <span className="flex items-center gap-2">
                      <span className={cn("h-1.5 w-1.5 rounded-full", loading ? "animate-pulse bg-white/60" : loadErr ? "bg-[#FF4B3E]" : "bg-white")} />
                      {loading ? "Loading live data" : loadErr ? "Live data offline" : "Live from OpenStreetMap"}
                    </span>
                    {loadErr && <button onClick={() => void load()} className="inline-flex items-center gap-1 text-white hover:underline"><RefreshCw className="h-3 w-3" /> Retry</button>}
                  </div>
                  <div className="mt-3 flex items-end gap-3">
                    <span className="lp-num lp-cond text-[88px] leading-[0.8]">{loading ? "··" : loadErr ? "?" : comps.length}</span>
                    <span className="pb-1 text-[15px] leading-tight text-white/80">{catLabel} around<br />{area}</span>
                  </div>
                  <div className="mt-5 grid gap-3 border-t border-white/15 pt-4 text-[13.5px]">
                    <div className="flex flex-wrap gap-x-4 gap-y-1">
                      {SPOTS.map((s) => (
                        <button key={s.key} onClick={() => setSpot(s)} aria-pressed={spot.key === s.key} className={cn("transition-colors", spot.key === s.key ? "text-white underline decoration-2 underline-offset-[6px]" : "text-white/50 hover:text-white")}>
                          {s.label.split(",")[0]}
                        </button>
                      ))}
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1">
                      {CATS.map((c) => (
                        <button key={c.key} onClick={() => setCat(c.key)} aria-pressed={cat === c.key} className={cn("transition-colors", cat === c.key ? "text-white underline decoration-2 underline-offset-[6px]" : "text-white/50 hover:text-white")}>
                          {c.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </aside>
              </div>
            </section>

            {/* ---------------- the story: scroll drives the camera over the same city ---------------- */}
            <div id="story">
              {CHAPTERS.map((c, i) => (
                <section key={c.title} data-scene={i + 1} className="flex min-h-[120svh] items-center px-5 md:px-10">
                  <div className={cn("mx-auto flex w-full max-w-[1400px]", i % 2 ? "justify-end" : "justify-start")}>
                    <article className={cn("lp-bb w-full max-w-[470px] rounded-[6px] bg-black p-7 text-white md:p-9", i % 2 && "lp-bb-r", scene === i + 1 && "is-on")}>
                      <div className="lp-num text-[13px] text-white/50">{i + 1} / {CHAPTERS.length}</div>
                      <h2 className="lp-wide mt-6 text-[clamp(1.9rem,3.2vw,2.9rem)] leading-[0.98] tracking-[-0.035em]">{c.title}</h2>
                      <p className="mt-4 text-[16.5px] leading-[1.55] text-white/70">{c.body}</p>
                      <ChapterFact i={i} area={area} comps={comps.length} loading={loading} catLabel={catLabel} on={scene === i + 1} />
                    </article>
                  </div>
                </section>
              ))}
            </div>
          </div>
        </div>

        {/* ---------------- field research ---------------- */}
        <section id="field" className="relative border-t border-white/15">
          <div className="mx-auto grid max-w-[1400px] items-center gap-16 px-5 py-28 md:px-10 md:py-40 lg:grid-cols-[1.15fr_0.85fr]">
            <div>
              <h2 className="lp-wide text-[clamp(2.4rem,5.4vw,5.4rem)] leading-[0.9] tracking-[-0.045em]">When the map runs out, someone walks the street.</h2>
              <p className="mt-8 max-w-[34rem] text-[18px] leading-[1.6] text-white/75">
                No data for your lane? Request a researcher from your own industry — a trainer for a gym, a chef for a café. They open a link on their phone, interview people, visit every rival and count footfall. Your simulation re-runs on what they find.
              </p>
              <dl className="mt-12 grid max-w-[34rem] grid-cols-2 gap-x-10 gap-y-7">
                {[
                  ["Interviews", "Who buys, how often, the most they'd pay"],
                  ["Rival visits", "Real prices, quality, unmapped shops"],
                  ["Footfall", "A tap counter at your site"],
                  ["Re-run", "The agents switch to street data"],
                ].map(([t, d]) => (
                  <div key={t} className="border-t border-white/30 pt-3">
                    <dt className="text-[16px] font-semibold">{t}</dt>
                    <dd className="mt-1 text-[14.5px] text-white/65">{d}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <PhoneMock />
          </div>
        </section>

        {/* ---------------- voice ---------------- */}
        <section id="voice" className="bg-black">
          <div className="mx-auto grid max-w-[1400px] gap-16 px-5 py-28 md:px-10 md:py-40 lg:grid-cols-2 lg:items-center">
            <div>
              <h2 className="lp-wide text-[clamp(2.6rem,6vw,6rem)] leading-[0.88] tracking-[-0.045em]">Don&apos;t click. Just talk.</h2>
              <Wave />
              <p className="mt-8 max-w-md text-[18px] leading-[1.6] text-white/70">
                Strata runs the whole app by voice — starts your project, loads the market, changes your rent, finds the best spot, sends a field researcher and builds the report. In proper Hinglish, with numbers only from the simulation.
              </p>
              <p className="mt-6 text-[15px] text-white/55">Press <kbd className="rounded-[4px] border border-white/30 px-1.5 text-[12px] text-white">V</kbd> anywhere to start.</p>
            </div>
            <Conversation />
          </div>
        </section>

        {/* ---------------- honesty ---------------- */}
        <section className="mx-auto max-w-[1400px] px-5 py-28 md:px-10 md:py-36">
          <div className="grid gap-12 lg:grid-cols-[1fr_1.5fr]">
            <h2 className="lp-wide text-[clamp(2.2rem,4.4vw,4.2rem)] leading-[0.92] tracking-[-0.045em]">What it won&apos;t pretend.</h2>
            <ul className="grid gap-x-12 gap-y-8 sm:grid-cols-2">
              {[
                ["Every shop", "Maps miss informal businesses. Gaps are flagged, and a field researcher can fill them."],
                ["Real people", "Simulated customers are a sample drawn from official data — never real individuals."],
                ["An accuracy score", "None is advertised, because none has been measured on real outcomes yet."],
                ["A promise", "Every forecast is a range under stated assumptions, not a guarantee of profit."],
              ].map(([t, d]) => (
                <li key={t} className="border-t border-white/30 pt-4">
                  <div className="text-[16px] font-semibold">{t}</div>
                  <p className="mt-1.5 text-[15px] leading-[1.55] text-white/70">{d}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ---------------- CTA ---------------- */}
        <section className="px-5 md:px-10">
          <div className="mx-auto max-w-[1400px] rounded-[6px] bg-white px-6 py-16 text-black md:px-14 md:py-24">
            <h2 className="lp-wide max-w-4xl text-[clamp(2.8rem,7.5vw,7.4rem)] leading-[0.86] tracking-[-0.05em]">Run the market first.</h2>
            <div className="mt-12 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
              <p className="max-w-md text-[18px] leading-[1.5] text-black/65">Three minutes and one line of text — before the deposit, before the fit-out.</p>
              <div className="flex flex-wrap gap-3">
                <Link href="/sign-up" className="inline-flex h-14 items-center gap-2 rounded-full bg-[#2F49FF] px-7 text-[16px] font-semibold text-white transition-transform hover:scale-[1.03]">
                  Start free <ArrowUpRight className="h-4 w-4" />
                </Link>
                <button onClick={liveDemo} className="inline-flex h-14 items-center gap-2 rounded-full border border-black/20 px-7 text-[16px] font-semibold transition-colors hover:border-black">
                  {busy === "live" && <Loader2 className="h-4 w-4 animate-spin" />} See the live demo
                </button>
              </div>
            </div>
          </div>
        </section>

        <footer className="mx-auto max-w-[1400px] px-5 pb-8 pt-20 md:px-10">
          <div className="flex flex-col gap-4 text-[13px] text-white/60 md:flex-row md:items-start md:justify-between">
            <p className="max-w-2xl">Map data © OpenStreetMap contributors (ODbL) · Places © Foursquare · Population © WorldPop (CC BY 4.0) · Tiles © OpenFreeMap / OpenMapTiles · Voice by ElevenLabs</p>
            <div className="flex shrink-0 gap-6 whitespace-nowrap">
              <Link href="/methodology" className="hover:text-white">Methodology & limitations</Link>
              <Link href="/sign-in" className="hover:text-white">Sign in</Link>
            </div>
          </div>
          <div aria-hidden className="lp-wide mt-14 select-none text-[19.5vw] leading-[0.8] tracking-[-0.06em] xl:text-[270px]">StrataIQ</div>
        </footer>
      </main>
    </div>
  );
}

/** One fact per chapter; colours match the map above. */
function ChapterFact({ i, area, comps, loading, catLabel, on }: { i: number; area: string; comps: number; loading: boolean; catLabel: string; on: boolean }) {
  const box = "mt-7 border-t border-white/15 pt-5";
  if (i === 0) return <div className={box}><div className="text-[13px] text-white/50">Now showing</div><div className="lp-wide mt-1 text-[26px] tracking-[-0.03em]">{area}</div></div>;
  if (i === 1)
    return (
      <div className={cn(box, "flex items-end gap-4")}>
        <span className="lp-num lp-cond text-[80px] leading-[0.8]">{loading ? "··" : <CountUp to={comps} run={on} />}</span>
        <span className="pb-1 text-[14.5px] leading-tight text-white/70">real {catLabel}, loaded<br />live around {area}</span>
      </div>
    );
  if (i === 2)
    return (
      <div className={cn(box, "flex items-end gap-4")}>
        <span className="lp-num lp-cond text-[80px] leading-[0.8] text-[#FF4B3E]"><CountUp to={10000} run={on} /></span>
        <span className="pb-1 text-[14.5px] leading-tight text-white/70">simulated customers<br />per run, from WorldPop</span>
      </div>
    );
  if (i === 3)
    return (
      <div className={box}>
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-[14.5px]">
          <span className="flex items-center gap-2"><span className="h-3 w-3 rounded-full bg-white" /> Chose you</span>
          <span className="flex items-center gap-2"><span className="h-3 w-3 rounded-full border border-white/70 bg-black" /> Chose a rival</span>
          <span className="flex items-center gap-2"><span className="h-3 w-3 rounded-full bg-[#AAB8FF]/60" /> Not buying today</span>
        </div>
        <p className="mt-3 text-[13px] text-white/50">The crowd on this page is an illustration. Your real run uses the calibrated choice model.</p>
      </div>
    );
  return (
    <ul className={cn(box, "space-y-2.5 text-[15.5px]")}>
      {["Profit in a bad, normal and good month", "Break-even customers and months", "The best spot in your catchment", "What would change the answer"].map((t) => (
        <li key={t} className="flex items-center gap-3"><span className="h-px w-4 bg-white/60" />{t}</li>
      ))}
    </ul>
  );
}

/** Counts up the first time its chapter is on screen (and again if the target changes). */
function CountUp({ to, run }: { to: number; run: boolean }) {
  const [v, setV] = useState(0);
  const shown = useRef<number | null>(null);
  useEffect(() => {
    if (!run || shown.current === to) return;
    shown.current = to;
    if (reduced()) return setV(to);
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / 1300);
      setV(to * (1 - Math.pow(1 - k, 4)));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [run, to]);
  return <>{Math.round(v).toLocaleString("en-IN")}</>;
}

function Wave() {
  return (
    <div aria-hidden className="mt-10 flex h-12 items-center gap-[5px]">
      {Array.from({ length: 34 }, (_, i) => (
        <span key={i} className="wave-bar w-[3px] rounded-full bg-white" style={{ animationDelay: `${(i * 73) % 900}ms`, height: `${25 + ((i * 37) % 75)}%` }} />
      ))}
    </div>
  );
}

/** The sample conversation plays line by line once it is scrolled into view. */
function Conversation() {
  const ref = useRef<HTMLDivElement>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reduced()) return setN(4);
    const timers: ReturnType<typeof setTimeout>[] = [];
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      [0, 1, 2, 3].forEach((k) => timers.push(setTimeout(() => setN(k + 1), 300 + k * 900)));
    }, { threshold: 0.4 });
    io.observe(el);
    return () => {
      io.disconnect();
      timers.forEach(clearTimeout);
    };
  }, []);
  const lines: [boolean, string][] = [
    [true, "Mujhe Indiranagar me café kholna hai, coffee 250 ki."],
    [false, "Theek hai, project bana raha hoon aur live market load kar raha hoon — ek minute."],
    [true, "Rent actually 90 hazaar hai, update kar do."],
    [false, "Update kar diya aur dobara simulate kiya. Rent badhne se profit kam hua — break-even ab zyada customers pe aayega. Best location bhi check karein?"],
  ];
  return (
    <div ref={ref} className="min-h-[340px] space-y-3 text-[16.5px]">
      {lines.map(([you, t], i) => (
        <div key={i} className={cn("lp-msg w-fit max-w-[88%] rounded-[18px] px-5 py-3.5 leading-snug", you ? "ml-auto rounded-br-[4px] bg-[#2F49FF] text-white" : "rounded-bl-[4px] bg-white text-black", i < n && "is-on")}>
          {t}
        </div>
      ))}
    </div>
  );
}

/** Illustration of the field researcher's phone app (not live data). */
function PhoneMock() {
  return (
    <div className="relative mx-auto w-full max-w-[320px]">
      <div className="phone-float relative rounded-[42px] bg-black p-2.5 shadow-[0_50px_100px_-30px_rgba(0,0,40,.6)]">
        <div className="rounded-[34px] bg-white p-5 text-black">
          <div className="flex items-center justify-between text-[11.5px] text-black/50">
            <span className="font-semibold text-black">StrataIQ Field</span>
            <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#2F49FF]" /> Collecting</span>
          </div>
          <div className="lp-wide mt-4 text-[19px] leading-tight tracking-[-0.03em]">Gym, Sector 18</div>
          <div className="mt-4 grid grid-cols-4 gap-1 rounded-[10px] bg-black/[0.06] p-1">
            {["Interview", "Rival", "Footfall", "Rent"].map((t, i) => (
              <div key={t} className={cn("rounded-[7px] py-1.5 text-center text-[10.5px]", i === 0 ? "bg-white font-semibold shadow-sm" : "text-black/50")}>{t}</div>
            ))}
          </div>
          <div className="mt-5 text-[13px]">Do you go to a gym now?</div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div className="rounded-[10px] bg-[#2F49FF] py-2.5 text-center text-[13px] font-semibold text-white">Yes</div>
            <div className="rounded-[10px] border border-black/15 py-2.5 text-center text-[13px] text-black/60">No</div>
          </div>
          <div className="mt-4 text-[13px]">Most you&apos;d pay a month?</div>
          <div className="mt-2 rounded-[10px] border-2 border-[#2F49FF] px-3 py-2.5 text-[14px] font-semibold">₹1,500<span className="ml-0.5 inline-block h-3.5 w-px animate-pulse bg-[#2F49FF] align-middle" /></div>
          <div className="mt-4 text-[13px]">How far do you travel?</div>
          <div className="mt-2 flex gap-1.5">
            {["1 km", "2 km", "3 km", "5 km"].map((t, i) => <span key={t} className={cn("rounded-full border px-2.5 py-1 text-[11px]", i === 1 ? "border-black bg-black text-white" : "border-black/15 text-black/55")}>{t}</span>)}
          </div>
          <div className="mt-5 rounded-[10px] bg-black py-3 text-center text-[13px] font-semibold text-white">Save interview (18 of 25)</div>
        </div>
      </div>
      <p className="mt-5 text-center text-[13px] text-white/55">Illustration of the field app</p>
    </div>
  );
}
