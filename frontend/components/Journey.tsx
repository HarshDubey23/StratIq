"use client";

/**
 * Guidance for people who have never done a market study: a five-step journey with the next step always one
 * click away, a short welcome tour, and a plain-language glossary of every term the app uses.
 */
import { BookA, Check, ChevronRight, Compass, Crosshair, Map as MapIcon, Mic, Scale, Users, Wand2, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { cn } from "@/components/ui";
import type { Project } from "@/lib/types";

const KEY = (id: string) => `siq-visited-${id}`;
function readVisited(id: string): string[] {
  try {
    return JSON.parse(localStorage.getItem(KEY(id)) || "[]");
  } catch {
    return [];
  }
}
function markVisited(id: string, seg: string) {
  try {
    const v = new Set(readVisited(id));
    v.add(seg);
    localStorage.setItem(KEY(id), JSON.stringify([...v]));
  } catch {
    /* storage unavailable: the journey still works, it just forgets */
  }
}

export const GLOSSARY: [string, string][] = [
  ["Catchment", "The area your customers realistically come from — the dashed circle on the map. People outside it are not counted."],
  ["Competitor (observed)", "A real business found in OpenStreetMap or Foursquare near you. Its price is unknown unless you enter it."],
  ["Agent", "One simulated person, placed where real people live. Each stands for many residents. Not a real individual."],
  ["615 parameters", "The numbers that describe one agent: budget, travel, free hours, tastes, media habits, loyalty and more."],
  ["In the market", "People who need what you sell right now (today, this month)."],
  ["Awareness", "Share of in-market people who know you exist. Ads, word of mouth and your signboard raise it."],
  ["Willingness to pay", "The highest price a person accepts. Each agent has its own."],
  ["Capacity", "The most you can serve — orders a day, seats, members, slots. Demand above it is turned away."],
  ["Turned away", "People who wanted to buy from you on a day you were already full."],
  ["Variable cost", "What each sale costs you: ingredients, packaging, delivery commission."],
  ["Fixed cost", "Monthly bills you pay even with zero sales: rent, salaries, utilities, marketing."],
  ["Operating profit", "Revenue minus variable and fixed costs, before tax, loan interest and depreciation."],
  ["Break-even", "Sales per month needed so revenue exactly covers costs. Below it you lose money."],
  ["Payback", "Months of profit needed to earn back your startup investment."],
  ["P10 / P90", "Bad case / good case. In 10% of the uncertainty runs profit was below P10; in 10% above P90."],
  ["Chance of a loss", "Share of the uncertainty runs where a month ends in a loss."],
  ["Scenario", "One version of your plan (price, costs, capacity, marketing). Make several and compare."],
  ["Baseline", "Your starting plan; everything else is compared against it."],
];

interface Step {
  key: string;
  label: string;
  hint: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  done: boolean;
}

export function Journey({ project }: { project: Project }) {
  const path = usePathname() || "";
  const base = `/app/projects/${project.id}`;
  const [visited, setVisited] = useState<string[]>([]);
  const [tour, setTour] = useState(false);
  const [words, setWords] = useState(false);

  useEffect(() => {
    const seg = path.slice(base.length).replace(/^\//, "") || "overview";
    const tab = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("tab") : null;
    markVisited(project.id, tab === "sites" ? "sites" : seg);
    setVisited(readVisited(project.id));
  }, [path, base, project.id]);
  useEffect(() => {
    const h = () => {
      markVisited(project.id, "sites");
      setVisited(readVisited(project.id));
    };
    window.addEventListener("strataiq:sites", h);
    const open = () => setTour(true);
    window.addEventListener("strataiq:tour", open);
    return () => {
      window.removeEventListener("strataiq:sites", h);
      window.removeEventListener("strataiq:tour", open);
    };
  }, [project.id]);
  useEffect(() => {
    let seen = true;
    try {
      seen = !!localStorage.getItem("siq-tour-seen");
    } catch {
      seen = true;
    }
    const welcome = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("welcome") === "1";
    if ((!seen || welcome) && !project.is_demo) setTour(true);
  }, [project.is_demo]);

  const hasData = !!project.snapshots && Object.values(project.snapshots).some(Boolean);
  const base0 = project.scenarios?.find((s) => s.is_baseline);
  const ran = !!base0?.latest_run;
  const explored = (project.scenarios || []).some((s) => s.name.startsWith("Strategy:") || s.name.startsWith("Voice:")) || project.locations.length > 1 || visited.includes("sites");
  const steps: Step[] = [
    { key: "market", label: "Load the real market", hint: "Real competitors and population around your place", href: `${base}/market`, icon: MapIcon, done: hasData },
    { key: "run", label: "Simulate customers", hint: "10,000 people decide between you, rivals or nothing", href: `${base}/market`, icon: Users, done: ran },
    { key: "live", label: "Watch the live market", hint: "Day by day: who comes, who goes to rivals, why", href: `${base}/live`, icon: Compass, done: visited.includes("live") },
    { key: "improve", label: "Find best site & strategy", hint: "Let StrataIQ search hundreds of options for you", href: `${base}/live`, icon: Wand2, done: explored },
    { key: "decide", label: "Get the verdict", hint: "Go / no-go, risks, and what to verify before you invest", href: `${base}/decisions`, icon: Scale, done: visited.includes("decisions") },
  ];
  const next = steps.find((s) => !s.done);
  const doneN = steps.filter((s) => s.done).length;

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-white/[0.06] bg-ink-950/60 px-4 py-2 text-xs md:px-8">
        <div className="flex items-center gap-1">
          {steps.map((s, i) => (
            <Link key={s.key} href={s.href} title={`${s.label} — ${s.hint}`} className="flex items-center gap-1">
              <span className={cn("flex h-5 w-5 items-center justify-center rounded-full border text-[10px]", s.done ? "border-model/60 bg-model/15 text-model" : s === next ? "border-accent bg-accent/15 text-accent" : "border-white/10 text-ink-500")}>
                {s.done ? <Check className="h-3 w-3" /> : i + 1}
              </span>
              {i < steps.length - 1 && <span className={cn("h-px w-4", s.done ? "bg-model/50" : "bg-white/10")} />}
            </Link>
          ))}
          <span className="num ml-2 text-ink-500">{doneN}/5</span>
        </div>
        {next ? (
          <Link href={next.href} className="group inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent/10 px-3 py-1 text-ink-100 hover:bg-accent/20">
            <span className="text-accent">Next:</span> {next.label} <span className="hidden text-ink-400 sm:inline">— {next.hint}</span>
            <ChevronRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
          </Link>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-model"><Check className="h-3.5 w-3.5" /> All steps done — share the Report or test another idea</span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <button onClick={() => setTour(true)} className="rounded-full px-2.5 py-1 text-ink-400 hover:bg-white/5 hover:text-ink-100">How it works</button>
          <button onClick={() => setWords(true)} className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-ink-400 hover:bg-white/5 hover:text-ink-100"><BookA className="h-3.5 w-3.5" /> Words explained</button>
        </div>
      </div>
      {tour && <Tour onClose={() => { setTour(false); try { localStorage.setItem("siq-tour-seen", "1"); } catch { /* ignore */ } }} base={base} />}
      {words && <Glossary onClose={() => setWords(false)} />}
    </>
  );
}

const SLIDES = [
  { icon: MapIcon, t: "1 · Your real market", d: "We load every real competitor near your place (OpenStreetMap + Foursquare) and how many people live around it (WorldPop). Blue pillars are rivals, the orange pillar is you, the dashed circle is where customers come from." },
  { icon: Users, t: "2 · 10,000 simulated people decide", d: "Each simulated person has a budget, a way to travel, free hours and tastes. Every day, those who need what you sell pick you, a rival or nothing — based on price, distance, hours and quality. That gives your orders, profit and risk." },
  { icon: Crosshair, t: "3 · Find the best place", d: "On the Market map, open \"Best sites\": we test your exact plan at every spot nearby and show where profit is highest. One click opens that spot with its own live data." },
  { icon: Wand2, t: "4 · Find the best strategy", d: "On the Live market, \"Find my best strategy\" tests hundreds of price, marketing and capacity combinations (extra costs included). Verify any of them with the 10,000 people on the map." },
  { icon: Mic, t: "5 · Just ask", d: "Press V and talk, in English or Hinglish: \"how can I grow?\", \"best location kahan hai?\", \"double the marketing\", \"what is break-even?\". Strata reads your screen and answers from the simulation." },
];

function Tour({ onClose, base }: { onClose: () => void; base: string }) {
  const [i, setI] = useState(0);
  const s = SLIDES[i];
  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-ink-950/70 p-4 backdrop-blur-sm" role="dialog" aria-label="How StrataIQ works">
      <div className="panel w-full max-w-lg rounded-3xl p-6">
        <div className="flex items-start justify-between">
          <s.icon className="h-7 w-7 text-accent" />
          <button onClick={onClose} aria-label="Close" className="rounded-full p-1 text-ink-400 hover:text-ink-100"><X className="h-4 w-4" /></button>
        </div>
        <h2 className="font-display mt-4 text-2xl font-semibold tracking-tight">{s.t}</h2>
        <p className="mt-2 text-[15px] leading-relaxed text-ink-300">{s.d}</p>
        <div className="mt-6 flex items-center gap-2">
          {SLIDES.map((_, k) => <button key={k} onClick={() => setI(k)} aria-label={`Slide ${k + 1}`} className={cn("h-1.5 rounded-full transition-all", k === i ? "w-6 bg-accent" : "w-1.5 bg-white/20")} />)}
          <div className="ml-auto flex gap-2">
            {i > 0 && <button onClick={() => setI(i - 1)} className="rounded-full px-4 py-2 text-sm text-ink-300 hover:text-ink-100">Back</button>}
            {i < SLIDES.length - 1 ? (
              <button onClick={() => setI(i + 1)} className="rounded-full bg-accent px-5 py-2 text-sm font-medium text-ink-950">Next</button>
            ) : (
              <Link href={`${base}/market`} onClick={onClose} className="rounded-full bg-accent px-5 py-2 text-sm font-medium text-ink-950">Start with the map</Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Glossary({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState("");
  const items = GLOSSARY.filter(([k, v]) => !q || (k + v).toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="fixed inset-0 z-[95] flex justify-end bg-ink-950/60 backdrop-blur-sm" role="dialog" aria-label="Words explained" onClick={onClose}>
      <div className="panel h-full w-full max-w-md overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="font-display text-xl font-semibold">Words explained</h2>
          <button onClick={onClose} aria-label="Close" className="rounded-full p-1 text-ink-400 hover:text-ink-100"><X className="h-4 w-4" /></button>
        </div>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search a word…" aria-label="Search a word" className="mt-4 h-10 w-full rounded-full border border-white/10 bg-white/[0.04] px-4 text-sm outline-none focus:border-accent/60" />
        <dl className="mt-4 space-y-4">
          {items.map(([k, v]) => (
            <div key={k}>
              <dt className="text-sm font-medium text-ink-100">{k}</dt>
              <dd className="mt-0.5 text-[13.5px] leading-relaxed text-ink-400">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-6 text-xs text-ink-500">Tip: you can also ask Strata — press V and say &quot;what is break-even?&quot;</p>
      </div>
    </div>
  );
}
