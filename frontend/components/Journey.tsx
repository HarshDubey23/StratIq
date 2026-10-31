"use client";

/**
 * Guidance for people who have never done a market study: a five-step journey with the next step always one
 * click away, a short welcome tour, and a plain-language glossary of every term the app uses.
 */
import { BookA, Check, ChevronDown, ChevronRight, Crosshair, Footprints, Map as MapIcon, Mic, Users, X } from "lucide-react";
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
  ["Field-verified", "Collected on the street by a field researcher from your industry: interviews, real competitor prices, footfall, rent. It outranks map data and assumptions."],
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
  seg: string;
  label: string;
  hint: string;
  done: boolean;
}

const MORE = [
  { seg: "", label: "Overview" },
  { seg: "/genome", label: "Market DNA" },
  { seg: "/factors", label: "615 factors" },
  { seg: "/monitor", label: "Monitoring" },
];

/** The project's whole navigation: six numbered steps with their progress, the next step, and help. */
export function Journey({ project }: { project: Project }) {
  const path = usePathname() || "";
  const base = `/app/projects/${project.id}`;
  const [visited, setVisited] = useState<string[]>([]);
  const [tour, setTour] = useState(false);
  const [words, setWords] = useState(false);
  const [more, setMore] = useState(false);

  useEffect(() => {
    const seg = path.slice(base.length).replace(/^\//, "") || "overview";
    const tab = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("tab") : null;
    markVisited(project.id, tab === "sites" ? "sites" : seg);
    setVisited(readVisited(project.id));
    setMore(false);
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
  const explored = (project.scenarios || []).some((s) => s.name.startsWith("Strategy:") || s.name.startsWith("Voice:")) || project.locations.length > 1 || visited.includes("sites") || visited.includes("simulation");
  const steps: Step[] = [
    { key: "market", seg: "/market", label: "Market map", hint: "Real competitors and people around your place", done: hasData },
    { key: "field", seg: "/field", label: "Field data", hint: "A researcher checks the street for what maps miss", done: (project.field?.records ?? 0) > 0 },
    { key: "live", seg: "/live", label: "Live market", hint: "10,000 agents choose you, a rival or nothing", done: ran && visited.includes("live") },
    { key: "lab", seg: "/simulation", label: "Simulation lab", hint: "Try prices, sites and budgets side by side", done: explored },
    { key: "decide", seg: "/decisions", label: "Decisions", hint: "Go / no-go and what could make it wrong", done: visited.includes("decisions") },
    { key: "report", seg: "/report", label: "Report", hint: "Share a feasibility report", done: visited.includes("report") },
  ];
  const next = steps.find((s) => !s.done);
  const doneN = steps.filter((s) => s.done).length;
  const moreActive = MORE.find((m) => (m.seg === "" ? path === base : path.startsWith(base + m.seg)));

  return (
    <>
      <div className="mt-4 flex items-center gap-3">
        <nav aria-label="Project" className="-mb-px flex min-w-0 flex-1 items-stretch overflow-x-auto">
          {steps.map((s, i) => {
            const active = path.startsWith(base + s.seg);
            return (
              <Link
                key={s.key}
                href={base + s.seg}
                title={s.hint}
                className={cn("group relative flex shrink-0 items-center gap-2 px-3 pb-3 pt-1.5 text-[13px] transition-colors", active ? "text-ink-100" : "text-ink-400 hover:text-ink-100")}
              >
                <span
                  className={cn(
                    "num flex h-5 w-5 items-center justify-center rounded-md font-mono text-[10px] transition-colors",
                    active ? "bg-accent text-white" : s.done ? "bg-field/15 text-field" : "bg-black/[0.06] text-ink-400 group-hover:bg-black/10",
                  )}
                >
                  {s.done && !active ? <Check className="h-3 w-3" /> : i + 1}
                </span>
                {s.label}
                {s.key === "field" && (project.field?.records ?? 0) > 0 && <span className="num rounded bg-field/15 px-1 font-mono text-[10px] text-field">{project.field?.records}</span>}
                <span className={cn("absolute inset-x-3 -bottom-px h-[2px] rounded-full bg-accent transition-transform duration-500", active ? "scale-x-100" : "scale-x-0")} style={{ transitionTimingFunction: "cubic-bezier(.16,1,.3,1)" }} />
              </Link>
            );
          })}
          <div className="relative shrink-0">
            <button onClick={() => setMore((m) => !m)} aria-expanded={more} className={cn("flex items-center gap-1 px-3 pb-3 pt-1.5 text-[13px]", moreActive ? "text-ink-100" : "text-ink-400 hover:text-ink-100")}>
              {moreActive?.label || "More"} <ChevronDown className="h-3.5 w-3.5" />
            </button>
            {more && (
              <div className="panel rise absolute left-0 top-full z-50 w-44 rounded-lg p-1">
                {MORE.map((m) => (
                  <Link key={m.label} href={base + m.seg} className="block rounded-md px-3 py-2 text-[13px] text-ink-200 hover:bg-black/[0.06] hover:text-ink-100">{m.label}</Link>
                ))}
              </div>
            )}
          </div>
        </nav>
        <div className="mb-2 hidden shrink-0 items-center gap-1 lg:flex">
          <span className="num mr-1 font-mono text-[11px] text-ink-500">{doneN}/6</span>
          <button onClick={() => setTour(true)} className="rounded-md px-2.5 py-1.5 text-xs text-ink-400 hover:bg-black/5 hover:text-ink-100">How it works</button>
          <button onClick={() => setWords(true)} className="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-xs text-ink-400 hover:bg-black/5 hover:text-ink-100"><BookA className="h-3.5 w-3.5" /> Glossary</button>
          {next && (
            <Link href={base + next.seg} className="sheen group ml-1 inline-flex h-8 items-center gap-1.5 rounded-lg bg-accent px-3 text-xs font-medium text-white hover:bg-[#2238e0]" title={next.hint}>
              Next: {next.label} <ChevronRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </Link>
          )}
        </div>
      </div>
      {tour && <Tour onClose={() => { setTour(false); try { localStorage.setItem("siq-tour-seen", "1"); } catch { /* ignore */ } }} base={base} />}
      {words && <Glossary onClose={() => setWords(false)} />}
    </>
  );
}

const SLIDES = [
  { icon: MapIcon, t: "1 · Your real market", d: "We load every real competitor near your place (OpenStreetMap + Foursquare) and how many people live around it (WorldPop). Amber pillars are rivals, the blue pillar is you, the dashed circle is where customers come from." },
  { icon: Footprints, t: "2 · Check the street", d: "Maps miss informal shops and real prices. Request a field researcher from your industry: they open a link on their phone, interview people, visit every rival and count footfall. The agents switch to that ground data." },
  { icon: Users, t: "3 · 10,000 simulated people decide", d: "Each simulated person has a budget, a way to travel, free hours and tastes. Every day, those who need what you sell pick you, a rival or nothing. That gives your orders, profit and risk." },
  { icon: Crosshair, t: "4 · Try other plans", d: "In the Simulation lab change price, rent, marketing or the site and run again. \"Best sites\" on the map tests your plan at every spot nearby." },
  { icon: Mic, t: "5 · Just ask", d: "Press V and talk, in English or Hinglish: \"how can I grow?\", \"best location kahan hai?\", \"what is break-even?\". Strata answers from the simulation." },
]

function Tour({ onClose, base }: { onClose: () => void; base: string }) {
  const [i, setI] = useState(0);
  const s = SLIDES[i];
  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-ink-950/70 p-4 backdrop-blur-sm" role="dialog" aria-label="How StrataIQ works">
      <div className="panel rise w-full max-w-lg rounded-xl p-6">
        <div className="flex items-start justify-between">
          <s.icon className="h-7 w-7 text-accent" />
          <button onClick={onClose} aria-label="Close" className="rounded-full p-1 text-ink-400 hover:text-ink-100"><X className="h-4 w-4" /></button>
        </div>
        <h2 className="font-display mt-4 text-2xl font-medium tracking-tight">{s.t}</h2>
        <p className="mt-2 text-[15px] leading-relaxed text-ink-300">{s.d}</p>
        <div className="mt-6 flex items-center gap-2">
          {SLIDES.map((_, k) => <button key={k} onClick={() => setI(k)} aria-label={`Slide ${k + 1}`} className={cn("h-1.5 rounded-full transition-all", k === i ? "w-6 bg-accent" : "w-1.5 bg-black/20")} />)}
          <div className="ml-auto flex gap-2">
            {i > 0 && <button onClick={() => setI(i - 1)} className="rounded-lg px-4 py-2 text-sm text-ink-300 hover:text-ink-100">Back</button>}
            {i < SLIDES.length - 1 ? (
              <button onClick={() => setI(i + 1)} className="rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white">Next</button>
            ) : (
              <Link href={`${base}/market`} onClick={onClose} className="rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white">Start with the map</Link>
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
          <h2 className="font-display text-xl font-medium">Words explained</h2>
          <button onClick={onClose} aria-label="Close" className="rounded-full p-1 text-ink-400 hover:text-ink-100"><X className="h-4 w-4" /></button>
        </div>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search a word…" aria-label="Search a word" className="mt-4 h-10 w-full rounded-lg border border-black/10 bg-black/[0.04] px-4 text-sm outline-none focus:border-accent/60" />
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
