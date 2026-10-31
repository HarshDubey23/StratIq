"use client";

import { ArrowRight, ArrowUpRight, Loader2, Mic, RefreshCw } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Logo } from "@/components/brand";
import { cn } from "@/components/ui";
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
      lenis = new Lenis({ lerp: 0.1, wheelMultiplier: 0.95 }) as unknown as typeof lenis;
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
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
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
  const placeholder = useTypewriter(IDEAS);
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

  return (
    <div className="relative bg-ink-950 text-ink-100">
      {/* ---------------- nav ---------------- */}
      <header className="sticky top-0 z-40 border-b border-black/[0.06] bg-ink-950/80 backdrop-blur-xl">
        <nav className="mx-auto flex h-16 max-w-[1320px] items-center justify-between px-5 md:px-8">
          <Logo />
          <div className="hidden items-center gap-8 text-[14px] text-ink-300 md:flex">
            <a href="#how" className="transition-colors hover:text-ink-100">How it works</a>
            <a href="#field" className="transition-colors hover:text-ink-100">Field research</a>
            <a href="#voice" className="transition-colors hover:text-ink-100">Voice</a>
            <Link href="/methodology" className="transition-colors hover:text-ink-100">Methodology</Link>
          </div>
          <div className="flex items-center gap-1.5">
            <Link href="/sign-in" className="hidden h-9 items-center rounded-full px-4 text-[14px] text-ink-200 transition-colors hover:bg-black/[0.05] sm:inline-flex">Sign in</Link>
            <Link href="/sign-up" className="inline-flex h-9 items-center rounded-full bg-ink-100 px-4 text-[14px] font-medium text-white transition-colors hover:bg-black">Start free</Link>
          </div>
        </nav>
      </header>

      <main>
        {/* ---------------- hero ---------------- */}
        <section className="mx-auto max-w-[1320px] px-5 pb-10 pt-16 md:px-8 md:pt-24">
          <div className="max-w-[980px]">
            <p data-reveal className="inline-flex items-center gap-2 rounded-full border border-black/[0.08] bg-white px-3 py-1.5 text-[13px] text-ink-300">
              <span className="relative flex h-1.5 w-1.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ok opacity-60" /><span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-ok" /></span>
              Live market data for any street in India
            </p>
            <h1 className="reveal-lines mt-7 font-display text-[clamp(2.9rem,7.4vw,7rem)] font-medium leading-[0.95] tracking-[-0.055em]">
              <span className="line-mask"><span style={{ transitionDelay: "80ms" }}>Know if your shop will <span className="serif text-accent">work</span>,</span></span>
              <span className="line-mask"><span style={{ transitionDelay: "190ms" }}>before you sign the lease.</span></span>
            </h1>
            <p data-reveal style={{ transitionDelay: "300ms" }} className="mt-7 max-w-[34rem] text-[18px] leading-[1.55] text-ink-300">
              Type your idea. StrataIQ maps every real competitor, places 10,000 simulated customers where people actually live, and tells you profit, risk and the best spot.
            </p>
          </div>

          {/* one line in, a whole market study out */}
          <form
            data-reveal
            style={{ transitionDelay: "380ms" }}
            onSubmit={(e) => { e.preventDefault(); void simulate(idea || placeholder); }}
            className="mt-10 flex max-w-[760px] flex-col gap-2 rounded-2xl border border-black/[0.08] bg-white p-2 shadow-[0_1px_2px_rgba(20,18,10,.04),0_24px_60px_-28px_rgba(20,18,10,.28)] sm:flex-row"
          >
            <label htmlFor="idea" className="sr-only">Your business idea</label>
            <input
              id="idea"
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              placeholder={placeholder || " "}
              className="h-14 min-w-0 flex-1 rounded-xl bg-transparent px-4 text-[17px] outline-none placeholder:text-ink-500"
            />
            <button type="submit" className="sheen inline-flex h-14 shrink-0 items-center justify-center gap-2 rounded-xl bg-accent px-6 text-[16px] font-medium text-white transition-colors hover:bg-[#2238e0]">
              {busy === "idea" ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Simulate my idea <ArrowRight className="h-4 w-4" />
            </button>
          </form>
          <div data-reveal style={{ transitionDelay: "440ms" }} className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-[14px] text-ink-400">
            <button onClick={liveDemo} className="inline-flex items-center gap-1.5 text-ink-100 underline decoration-black/20 underline-offset-4 transition-colors hover:decoration-black">
              {busy === "live" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null} Or open the live demo
            </button>
            <span className="inline-flex items-center gap-1.5"><Mic className="h-3.5 w-3.5 text-accent" /> or press <kbd className="rounded border border-black/15 bg-white px-1.5 font-mono text-[11px] text-ink-200">V</kbd> and say it in Hinglish</span>
            {goErr && <span className="text-danger">{goErr}</span>}
          </div>

          {/* the product, live */}
          <div data-reveal style={{ transitionDelay: "520ms" }} className="mt-16 overflow-hidden rounded-[28px] border border-black/[0.08] bg-white shadow-[0_2px_4px_rgba(20,18,10,.04),0_50px_100px_-40px_rgba(20,18,10,.35)]">
            <div className="flex flex-wrap items-center gap-3 border-b border-black/[0.06] px-4 py-3">
              <div className="flex gap-1.5" aria-hidden>
                <span className="h-2.5 w-2.5 rounded-full bg-black/10" />
                <span className="h-2.5 w-2.5 rounded-full bg-black/10" />
                <span className="h-2.5 w-2.5 rounded-full bg-black/10" />
              </div>
              <div className="flex flex-wrap gap-1">
                {SPOTS.map((s) => (
                  <button key={s.key} onClick={() => setSpot(s)} className={cn("h-8 rounded-full px-3 text-[13px] transition-colors", spot.key === s.key ? "bg-ink-100 text-white" : "text-ink-300 hover:bg-black/[0.05]")}>
                    {s.label.split(",")[0]}
                  </button>
                ))}
              </div>
              <div className="ml-auto flex flex-wrap gap-1">
                {CATS.map((c) => (
                  <button key={c.key} onClick={() => setCat(c.key)} className={cn("h-8 rounded-full border px-3 text-[13px] transition-colors", cat === c.key ? "border-accent bg-accent-dim text-accent" : "border-transparent text-ink-300 hover:bg-black/[0.05]")}>
                    {c.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="relative h-[460px] md:h-[600px]">
              <HeroMap spot={spot} comps={comps} chapter={0} showTrips={!loading} framed />
              <div className="panel absolute left-4 top-4 w-[250px] rounded-2xl p-4 md:left-6 md:top-6">
                <div className="flex items-center gap-2 text-[12px] text-ink-400">
                  <span className={cn("h-1.5 w-1.5 rounded-full", loading ? "bg-warn" : loadErr ? "bg-danger" : "bg-ok")} />
                  {loading ? "Fetching live…" : loadErr ? "Live data offline" : "Live from OpenStreetMap + Foursquare"}
                </div>
                <div className="mt-2 flex items-end gap-2">
                  <span className="num font-display text-[56px] font-medium leading-none tracking-[-0.05em]">{loading ? "—" : loadErr ? "?" : comps.length}</span>
                  <span className="pb-1.5 text-[14px] leading-tight text-ink-300">real {catLabel}<br />within {((preview?.radius_m || 1600) / 1000).toFixed(1)} km</span>
                </div>
                {loadErr && (
                  <button onClick={() => void load()} className="mt-2 inline-flex items-center gap-1.5 text-xs text-ink-300 hover:text-ink-100"><RefreshCw className="h-3.5 w-3.5" /> Retry</button>
                )}
              </div>
              <div className="panel absolute bottom-4 left-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-full px-4 py-2 text-[12px] text-ink-300 md:bottom-6 md:left-6">
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-accent" /> Your site</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#F59E0B]" /> Real competitors</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-agent" /> Simulated customers</span>
              </div>
            </div>
          </div>
        </section>

        {/* ---------------- how it works ---------------- */}
        <section id="how" className="mx-auto max-w-[1320px] px-5 py-28 md:px-8 md:py-36">
          <div className="grid gap-10 md:grid-cols-[1fr_1.4fr]">
            <h2 data-reveal className="font-display text-[clamp(2.2rem,4.6vw,4rem)] font-medium leading-[1] tracking-[-0.05em]">
              A market study in <span className="serif">three</span> minutes, not three weeks.
            </h2>
            <ol className="divide-y divide-black/[0.08] border-y border-black/[0.08]">
              {[
                ["Describe it", "One line is enough: the business, the place, a price if you know it. English or Hinglish."],
                ["Watch the street", "Real shops load on a 3D map. 10,000 simulated people with real budgets choose you, a rival, or nothing — every day for 12 weeks."],
                ["Decide", "Profit in a bad, normal and good month. Break-even. The best spot nearby. And what could make the answer wrong."],
              ].map(([t, d], i) => (
                <li key={t} data-reveal style={{ transitionDelay: `${i * 90}ms` }} className="grid grid-cols-[56px_1fr] gap-4 py-7">
                  <span className="serif text-[40px] leading-none text-ink-400">{i + 1}</span>
                  <div>
                    <h3 className="text-[20px] font-medium tracking-[-0.02em]">{t}</h3>
                    <p className="mt-1.5 max-w-lg text-[15.5px] leading-relaxed text-ink-300">{d}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* ---------------- field research ---------------- */}
        <section id="field" className="border-y border-black/[0.06] bg-white">
          <div className="mx-auto grid max-w-[1320px] items-center gap-14 px-5 py-28 md:px-8 lg:grid-cols-[1.1fr_0.9fr]">
            <div>
              <p data-reveal className="text-[14px] font-medium text-field">Field research</p>
              <h2 data-reveal className="mt-4 font-display text-[clamp(2.2rem,4.6vw,4rem)] font-medium leading-[1] tracking-[-0.05em]">
                When the map runs out, a person <span className="serif">walks</span> the street.
              </h2>
              <p data-reveal className="mt-6 max-w-lg text-[17px] leading-relaxed text-ink-300">
                No data for your lane? Request a researcher from your own industry — a trainer for a gym, a chef for a café. They open a link on their phone, interview people, visit every rival and count footfall. Your simulation re-runs on what they find.
              </p>
              <dl data-reveal className="mt-10 grid max-w-lg grid-cols-2 gap-x-8 gap-y-6">
                {[
                  ["Interviews", "who buys, how often, the most they'd pay"],
                  ["Rival visits", "real prices, quality, unmapped shops"],
                  ["Footfall", "a tap counter at your site"],
                  ["Re-run", "agents switch to street data"],
                ].map(([t, d]) => (
                  <div key={t} className="border-t border-black/[0.08] pt-3">
                    <dt className="text-[15px] font-medium">{t}</dt>
                    <dd className="mt-1 text-[14px] text-ink-400">{d}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <PhoneMock />
          </div>
        </section>

        {/* ---------------- voice ---------------- */}
        <section id="voice" className="bg-ink-100 text-white">
          <div className="mx-auto grid max-w-[1320px] gap-14 px-5 py-28 md:px-8 lg:grid-cols-2 lg:items-center">
            <div>
              <p className="text-[14px] font-medium text-[#8a9bff]">Strata, the voice analyst</p>
              <h2 data-reveal className="mt-4 font-display text-[clamp(2.2rem,4.6vw,4rem)] font-medium leading-[1] tracking-[-0.05em]">
                Don&apos;t click. Just <span className="serif text-[#8a9bff]">talk.</span>
              </h2>
              <p data-reveal className="mt-6 max-w-md text-[17px] leading-relaxed text-white/60">
                Strata runs the whole app by voice — starts your project, loads the market, changes your rent, finds the best spot, sends a field researcher and builds the report. In proper Hinglish, with numbers only from the simulation.
              </p>
              <p data-reveal className="mt-8 text-[14px] text-white/50">Press <kbd className="rounded border border-white/20 px-1.5 font-mono text-[12px] text-white">V</kbd> anywhere to start.</p>
            </div>
            <div data-reveal className="space-y-3 text-[16px]">
              <Bubble you>Mujhe Indiranagar me café kholna hai, coffee 250 ki.</Bubble>
              <Bubble>Theek hai, project bana raha hoon aur live market load kar raha hoon — ek minute.</Bubble>
              <Bubble you>Rent actually 90 hazaar hai, update kar do.</Bubble>
              <Bubble>Update kar diya aur dobara simulate kiya. Rent badhne se profit kam hua — break-even ab zyada customers pe aayega. Best location bhi check karein?</Bubble>
            </div>
          </div>
        </section>

        {/* ---------------- honesty ---------------- */}
        <section className="mx-auto max-w-[1320px] px-5 py-28 md:px-8">
          <div className="grid gap-10 md:grid-cols-[1fr_1.4fr]">
            <h2 data-reveal className="font-display text-[clamp(2rem,3.6vw,3rem)] font-medium leading-[1.02] tracking-[-0.045em]">What it won&apos;t pretend.</h2>
            <ul className="grid gap-x-10 gap-y-6 sm:grid-cols-2">
              {[
                ["Every shop", "Maps miss informal businesses. Gaps are flagged, and a field researcher can fill them."],
                ["Real people", "Simulated customers are a sample drawn from official data — never real individuals."],
                ["An accuracy score", "None is advertised, because none has been measured on real outcomes yet."],
                ["A promise", "Every forecast is a range under stated assumptions, not a guarantee of profit."],
              ].map(([t, d]) => (
                <li key={t} data-reveal className="border-t border-black/[0.08] pt-4">
                  <div className="text-[15px] font-medium">{t}</div>
                  <p className="mt-1 text-[14.5px] leading-relaxed text-ink-400">{d}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ---------------- CTA ---------------- */}
        <section className="mx-auto max-w-[1320px] px-5 pb-12 md:px-8">
          <div className="relative overflow-hidden rounded-[32px] bg-accent px-6 py-20 text-white md:px-16 md:py-28">
            <div aria-hidden className="grid-bg pointer-events-none absolute inset-0 opacity-40 [mask-image:radial-gradient(70%_80%_at_80%_20%,black,transparent)]" style={{ backgroundImage: "linear-gradient(to right, rgba(255,255,255,.12) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,.12) 1px, transparent 1px)" }} />
            <h2 data-reveal className="relative max-w-3xl font-display text-[clamp(2.6rem,6vw,5.6rem)] font-medium leading-[0.95] tracking-[-0.055em]">
              Run the market <span className="serif">first.</span>
            </h2>
            <div className="relative mt-10 flex flex-wrap gap-3">
              <Link href="/sign-up" className="inline-flex h-14 items-center gap-2 rounded-full bg-white px-7 text-[16px] font-medium text-accent transition-transform hover:-translate-y-0.5">
                Start free <ArrowUpRight className="h-4 w-4" />
              </Link>
              <button onClick={liveDemo} className="inline-flex h-14 items-center gap-2 rounded-full border border-white/30 px-7 text-[16px] text-white transition-colors hover:bg-white/10">
                {busy === "live" ? <Loader2 className="h-4 w-4 animate-spin" /> : null} See the live demo
              </button>
            </div>
          </div>

          <footer className="mt-16 flex flex-col gap-4 border-t border-black/[0.08] pt-6 text-[12.5px] text-ink-400 md:flex-row md:items-center md:justify-between">
            <Logo />
            <p className="max-w-2xl">Map data © OpenStreetMap contributors (ODbL) · Places © Foursquare · Population © WorldPop (CC BY 4.0) · Tiles © OpenFreeMap / OpenMapTiles · Voice by ElevenLabs</p>
            <Link href="/methodology" className="hover:text-ink-100">Methodology & limitations</Link>
          </footer>
        </section>
      </main>
    </div>
  );
}

function Bubble({ you, children }: { you?: boolean; children: React.ReactNode }) {
  return (
    <div className={cn("w-fit max-w-[88%] rounded-3xl px-5 py-3.5 leading-snug", you ? "ml-auto rounded-br-md bg-white/10 text-white" : "rounded-bl-md bg-white text-ink-100")}>
      {children}
    </div>
  );
}

/** Illustration of the field researcher's phone app (not live data). */
function PhoneMock() {
  return (
    <div data-reveal className="relative mx-auto w-full max-w-[330px]">
      <div className="relative rounded-[40px] border border-black/[0.08] bg-ink-800 p-2.5 shadow-[0_40px_90px_-40px_rgba(20,18,10,.45)]">
        <div className="rounded-[32px] bg-white p-5">
          <div className="flex items-center justify-between text-[11px] text-ink-400">
            <span className="font-medium text-ink-200">StrataIQ Field</span>
            <span className="flex items-center gap-1.5 text-field"><span className="h-1.5 w-1.5 rounded-full bg-field" /> collecting</span>
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
