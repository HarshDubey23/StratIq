"use client";

/**
 * Quick start for people who don't know the jargon: write the idea in one sentence (English or Hinglish),
 * see the plan StrataIQ understood — with every guessed number labelled — fix anything, and go.
 */
import { ArrowRight, Check, Lightbulb, MapPin, Pencil, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LocationPicker, type PickedPlace } from "@/components/LocationPicker";
import { Button, cn, Notice, NumberInput } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";

const EXAMPLES = [
  "A café in Indiranagar, Bengaluru, coffee at ₹250",
  "Gym in Bandra West Mumbai, fees ₹2,000 a month, budget 30 lakh",
  "Mujhe Koramangala mein pizza shop kholna hai",
  "Dental clinic near Saket, Delhi",
];

export interface Plan {
  parsed: { text: string; business: string; place: string | null; price: number | null; budget: number | null };
  category: { key: string; label: string; archetype: string };
  archetype: { key: string; label: string; unit: string; price_label: string };
  place: { name: string; display_name: string; lat: number; lng: number } | null;
  price: number;
  costs: Record<string, number>;
  assumptions: string[];
  questions: string[];
  name: string;
  ready: boolean;
  radius_km: number;
}

export async function ensureSession(): Promise<void> {
  const me = await fetch("/api/v1/auth/me", { credentials: "include" });
  if (me.ok) return;
  const g = await fetch("/api/v1/auth/guest", { method: "POST", credentials: "include" });
  if (!g.ok) throw new Error("The server is waking up. Try again in a few seconds.");
}

/** Plan + create + start loading live data. Used by the form and by the voice analyst. */
export async function quickCreate(text: string, place?: PickedPlace | null, edits?: { price?: number | null; startup_cost?: number | null; rent?: number | null }): Promise<{ id: string; plan: Plan }> {
  await ensureSession();
  const plan = await api<Plan>("/quickstart/plan", { method: "POST", json: { text, ...(place ? { lat: place.lat, lng: place.lng, place_label: place.address } : {}) } });
  if (!plan.ready) throw Object.assign(new Error(plan.questions[0] || "Where should it be?"), { plan });
  const p = await api<{ id: string; locations: { id: string }[] }>("/quickstart/create", {
    method: "POST",
    json: { plan, price: edits?.price ?? null, startup_cost: edits?.startup_cost ?? null, rent: edits?.rent ?? null },
  });
  void api(`/projects/${p.id}/locations/${p.locations[0].id}/refresh`, { method: "POST" }).catch(() => undefined);
  return { id: p.id, plan };
}

export function QuickStart({ compact = false, autoFocus = false }: { compact?: boolean; autoFocus?: boolean }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [place, setPlace] = useState<PickedPlace | null>(null);
  const [price, setPrice] = useState<number | null>(null);
  const [budget, setBudget] = useState<number | null>(null);
  const [rent, setRent] = useState<number | null>(null);
  const [busy, setBusy] = useState<"plan" | "create" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editPlace, setEditPlace] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("idea");
    if (q) {
      setText(q);
      void understand(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function understand(t = text) {
    if (t.trim().length < 3) return;
    setBusy("plan");
    setErr(null);
    try {
      await ensureSession();
      const pl = await api<Plan>("/quickstart/plan", { method: "POST", json: { text: t } });
      setPlan(pl);
      setPrice(pl.price);
      setBudget(pl.costs.startup_cost ?? null);
      setRent(pl.costs.rent ?? null);
      setPlace(pl.place ? { lat: pl.place.lat, lng: pl.place.lng, address: pl.place.display_name || pl.place.name } : null);
      setEditPlace(!pl.place);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "I couldn't read that — try 'a café in Indiranagar'");
    } finally {
      setBusy(null);
    }
  }

  async function go() {
    if (!plan || !place) return;
    setBusy("create");
    setErr(null);
    try {
      const pl = { ...plan, place: { name: place.address.split(",")[0], display_name: place.address, lat: place.lat, lng: place.lng }, ready: true };
      const p = await api<{ id: string; locations: { id: string }[] }>("/quickstart/create", { method: "POST", json: { plan: pl, price, startup_cost: budget, rent } });
      void api(`/projects/${p.id}/locations/${p.locations[0].id}/refresh`, { method: "POST" }).catch(() => undefined);
      router.push(`/app/projects/${p.id}/market?welcome=1`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not create the analysis");
      setBusy(null);
    }
  }

  return (
    <div className={cn("relative overflow-hidden rounded-xl border border-accent/35 bg-[linear-gradient(135deg,rgba(79,108,255,.14),rgba(79,108,255,.02)_55%,transparent)]", compact ? "p-4" : "p-5 sm:p-7")}>
      <div className="flex items-center gap-2 text-sm font-medium text-ink-100"><Sparkles className="h-4 w-4 text-accent" /> Describe your idea in one line</div>
      <p className="mt-1 text-xs text-ink-400">English or Hinglish. Business type and place are enough — I&apos;ll fill the rest with typical numbers you can change.</p>
      <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); void understand(); }}>
        <input autoFocus={autoFocus} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. A café in Indiranagar, Bengaluru, coffee at ₹250" aria-label="Your business idea"
          className="h-12 flex-1 rounded-lg border border-white/10 bg-ink-950/70 px-4 text-[15px] outline-none transition-[border-color,box-shadow] placeholder:text-ink-500 focus:border-accent focus:shadow-[0_0_0_3px_rgba(79,108,255,.2)]" />
        <Button type="submit" variant="primary" size="lg" loading={busy === "plan"}>Understand it <ArrowRight className="h-4 w-4" /></Button>
      </form>
      {!plan && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {EXAMPLES.map((x) => (
            <button key={x} onClick={() => { setText(x); void understand(x); }} className="rounded-md border border-white/10 px-2.5 py-1 text-[11.5px] text-ink-300 transition-colors hover:border-accent/60 hover:text-ink-100">{x}</button>
          ))}
        </div>
      )}
      {err && <div className="mt-3"><Notice tone="warn">{err}</Notice></div>}
      {plan && (
        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_1fr]">
          <div className="space-y-3 text-sm">
            <Row icon={<Check className="h-3.5 w-3.5 text-model" />} k="Business" v={<>{plan.category.label} <span className="text-ink-500">· {plan.archetype.label} model, sells {plan.archetype.unit}</span></>} />
            <Row icon={<MapPin className="h-3.5 w-3.5 text-accent" />} k="Place" v={place ? <span>{place.address.split(",").slice(0, 3).join(",")} <button onClick={() => setEditPlace((x) => !x)} className="ml-1 text-xs text-[#9fb0ff]"><Pencil className="inline h-3 w-3" /> change</button></span> : <span className="text-warn">pick on the map →</span>} />
            <div className="grid grid-cols-3 gap-2">
              <Edit label={plan.archetype.price_label} v={price} set={setPrice} />
              <Edit label="Budget to start" v={budget} set={setBudget} />
              <Edit label="Rent / month" v={rent} set={setRent} />
            </div>
            <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] p-3 text-xs">
              <div className="mb-1 flex items-center gap-1.5 font-medium text-ink-200"><Lightbulb className="h-3.5 w-3.5 text-warn" /> Starter assumptions (change any later)</div>
              <ul className="list-disc space-y-0.5 pl-4 text-ink-400">{plan.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
            </div>
            <Button variant="primary" size="lg" className="w-full" disabled={!place} loading={busy === "create"} onClick={go}>
              {busy === "create" ? "Creating…" : "Analyse this idea with live data"} <ArrowRight className="h-4 w-4" />
            </Button>
            <p className="text-[11px] text-ink-500">Next: I load the real competitors and population around the place, run 10,000 simulated customers, and show you profit, risk and the best strategy.</p>
          </div>
          {(editPlace || !place) && (
            <div>
              {plan.questions.map((q) => <p key={q} className="mb-2 text-xs text-warn">{q}</p>)}
              <LocationPicker value={place} onChange={(pl) => setPlace(pl)} radiusKm={plan.radius_km} initialQuery={plan.parsed.place || ""} height="h-72" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ icon, k, v }: { icon: React.ReactNode; k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-1">{icon}</span>
      <div><div className="text-[11px] text-ink-500">{k}</div><div className="text-ink-100">{v}</div></div>
    </div>
  );
}

function Edit({ label, v, set }: { label: string; v: number | null; set: (x: number | null) => void }) {
  return (
    <label className="block text-[11px] text-ink-500">
      {label}
      <NumberInput value={v} onChange={set} prefix="₹" allowEmpty placeholder="0" />
      {v ? <span className="num text-[10px] text-ink-500">{money(v, { compact: true })}</span> : null}
    </label>
  );
}
