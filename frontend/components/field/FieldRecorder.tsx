"use client";

/**
 * The field researcher's recorder: four quick forms (interview, competitor visit, footfall count, rent quote) built for
 * a phone held in one hand on a busy street. Used both on the researcher's no-login link and on the owner's field page.
 */
import { Check, Crosshair, Footprints, Home, Loader2, MessageSquareText, Minus, Pause, Play, Plus, RotateCcw, Store } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn, inputCls, NumberInput } from "@/components/ui";
import type { FieldKind } from "@/lib/types";

export interface RecordDraft {
  kind: FieldKind;
  data: Record<string, unknown>;
  lat?: number | null;
  lng?: number | null;
  collected_by?: string;
}

export const KIND_META: Record<FieldKind, { label: string; icon: typeof Store; tint: string }> = {
  interview: { label: "Interview", icon: MessageSquareText, tint: "text-field" },
  competitor: { label: "Competitor", icon: Store, tint: "text-observed" },
  footfall: { label: "Footfall", icon: Footprints, tint: "text-accent" },
  rent: { label: "Rent", icon: Home, tint: "text-userdata" },
};

function Chips<T extends string | number>({ value, options, onChange, label }: { value: T | null; options: { v: T; l: string }[]; onChange: (v: T | null) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
      {options.map((o) => (
        <button
          type="button"
          key={String(o.v)}
          role="radio"
          aria-checked={value === o.v}
          onClick={() => onChange(value === o.v ? null : o.v)}
          className={cn(
            "h-9 rounded-lg border px-3 text-[13px] transition-colors",
            value === o.v ? "border-accent bg-accent text-white" : "border-black/10 bg-black/[0.03] text-ink-200 hover:border-black/25",
          )}
        >
          {o.l}
        </button>
      ))}
    </div>
  );
}

function Q({ n, label, children }: { n: string; label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2 text-[13.5px] text-ink-100">
        <span className="idx">{n}</span>
        <span>{label}</span>
      </div>
      {children}
    </div>
  );
}

export function FieldRecorder({
  category,
  priceLabel,
  site,
  onSave,
  counts,
  who,
}: {
  category: string;
  priceLabel: string;
  site: { lat: number; lng: number } | null;
  onSave: (d: RecordDraft) => Promise<void>;
  counts: Partial<Record<FieldKind, number>>;
  who?: string;
}) {
  const [kind, setKind] = useState<FieldKind>("interview");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  async function save(d: RecordDraft) {
    setBusy(true);
    setErr(null);
    try {
      await onSave({ ...d, collected_by: who });
      setFlash(`${KIND_META[d.kind].label} saved`);
      setNonce((x) => x + 1);
      setTimeout(() => setFlash(null), 2200);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not save. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div role="tablist" aria-label="What are you recording?" className="grid grid-cols-4 gap-1.5">
        {(Object.keys(KIND_META) as FieldKind[]).map((k) => {
          const M = KIND_META[k];
          return (
            <button
              key={k}
              role="tab"
              aria-selected={kind === k}
              onClick={() => setKind(k)}
              className={cn(
                "flex flex-col items-center gap-1 rounded-lg border px-1 py-2.5 text-[12px] transition-colors",
                kind === k ? "border-black/25 bg-black/[0.07] text-ink-100" : "border-black/[0.06] text-ink-400 hover:text-ink-100",
              )}
            >
              <M.icon className={cn("h-4.5 w-4.5", kind === k && M.tint)} />
              {M.label}
              <span className="num font-mono text-[10px] text-ink-500">{counts[k] ?? 0}</span>
            </button>
          );
        })}
      </div>
      <div className="mt-5" key={`${kind}-${nonce}`}>
        {kind === "interview" && <InterviewForm category={category} priceLabel={priceLabel} busy={busy} onSave={save} />}
        {kind === "competitor" && <CompetitorForm site={site} priceLabel={priceLabel} busy={busy} onSave={save} />}
        {kind === "footfall" && <FootfallForm busy={busy} onSave={save} />}
        {kind === "rent" && <RentForm busy={busy} onSave={save} />}
      </div>
      <div aria-live="polite" className="mt-3 min-h-5 text-sm">
        {flash && <span className="rise inline-flex items-center gap-1.5 text-field"><Check className="h-4 w-4" /> {flash}</span>}
        {err && <span className="text-red-700">{err}</span>}
      </div>
    </div>
  );
}

function SaveBtn({ busy, disabled, children }: { busy: boolean; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy || disabled}
      className="sheen flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-accent text-[15px] font-medium text-white transition-colors hover:bg-[#2238e0] disabled:opacity-40"
    >
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} {children}
    </button>
  );
}

function InterviewForm({ category, priceLabel, busy, onSave }: { category: string; priceLabel: string; busy: boolean; onSave: (d: RecordDraft) => void }) {
  const [uses, setUses] = useState<"yes" | "no" | null>(null);
  const [visits, setVisits] = useState<number | null>(null);
  const [price, setPrice] = useState<number | null>(null);
  const [km, setKm] = useState<number | null>(null);
  const [mode, setMode] = useState<string | null>(null);
  const [age, setAge] = useState<string | null>(null);
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!uses) return;
        onSave({ kind: "interview", data: { uses_category: uses === "yes", visits_per_month: visits, max_price: price, travel_km: km, travel_mode: mode, age_band: age } });
      }}
    >
      <Q n="01" label={<>Do you currently use <b className="font-medium">{category.toLowerCase()}</b>?</>}>
        <div className="grid grid-cols-2 gap-2">
          {(["yes", "no"] as const).map((v) => (
            <button
              type="button"
              key={v}
              onClick={() => setUses(v)}
              className={cn("h-12 rounded-lg border text-[15px] font-medium capitalize transition-colors", uses === v ? (v === "yes" ? "border-field bg-field text-ink-950" : "border-ink-200 bg-ink-100 text-ink-950") : "border-black/10 text-ink-200")}
            >
              {v}
            </button>
          ))}
        </div>
      </Q>
      {uses === "yes" && (
        <>
          <Q n="02" label="How many times a month?">
            <Chips label="Visits per month" value={visits} onChange={setVisits} options={[1, 2, 4, 8, 12, 20].map((v) => ({ v, l: v === 20 ? "20+" : String(v) }))} />
          </Q>
          <Q n="03" label="How far do you travel for it?">
            <Chips label="Travel distance" value={km} onChange={setKm} options={[0.5, 1, 2, 3, 5, 8].map((v) => ({ v, l: v === 8 ? "8+ km" : `${v} km` }))} />
          </Q>
          <Q n="04" label="How do you usually get there?">
            <Chips label="Travel mode" value={mode} onChange={setMode} options={[{ v: "walk", l: "Walk" }, { v: "two_wheeler", l: "Two-wheeler" }, { v: "auto", l: "Auto" }, { v: "bus_metro", l: "Bus / metro" }, { v: "car", l: "Car" }]} />
          </Q>
        </>
      )}
      {uses && (
        <>
          <Q n={uses === "yes" ? "05" : "02"} label={<>The most you would pay — <span className="text-ink-400">{priceLabel.toLowerCase()}</span></>}>
            <NumberInput value={price} onChange={setPrice} prefix="₹" placeholder="e.g. 1500" allowEmpty min={1} />
          </Q>
          <Q n={uses === "yes" ? "06" : "03"} label="Age group (optional)">
            <Chips label="Age group" value={age} onChange={setAge} options={[{ v: "18_24", l: "18–24" }, { v: "25_34", l: "25–34" }, { v: "35_49", l: "35–49" }, { v: "50_plus", l: "50+" }]} />
          </Q>
        </>
      )}
      <SaveBtn busy={busy} disabled={!uses}>Save interview</SaveBtn>
      <p className="text-[11.5px] leading-relaxed text-ink-500">Never record names, phone numbers or faces. Answers are anonymous.</p>
    </form>
  );
}

function CompetitorForm({ site, priceLabel, busy, onSave }: { site: { lat: number; lng: number } | null; priceLabel: string; busy: boolean; onSave: (d: RecordDraft) => void }) {
  const [name, setName] = useState("");
  const [price, setPrice] = useState<number | null>(null);
  const [q, setQ] = useState<number | null>(null);
  const [vph, setVph] = useState<number | null>(null);
  const [hours, setHours] = useState("");
  const [pos, setPos] = useState<{ lat: number; lng: number } | null>(null);
  const [gps, setGps] = useState<"idle" | "busy" | "err">("idle");
  function locate() {
    if (!navigator.geolocation) return setGps("err");
    setGps("busy");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setPos({ lat: +p.coords.latitude.toFixed(6), lng: +p.coords.longitude.toFixed(6) });
        setGps("idle");
      },
      () => setGps("err"),
      { enableHighAccuracy: true, timeout: 15000 },
    );
  }
  const loc = pos ?? site;
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!name.trim() || !loc) return;
        onSave({ kind: "competitor", lat: loc.lat, lng: loc.lng, data: { name: name.trim(), price, quality: q, visitors_per_hour: vph, open_hours: hours } });
      }}
    >
      <Q n="01" label="Shop name (as on the signboard)">
        <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Iron Den Fitness" maxLength={200} />
      </Q>
      <Q n="02" label="Where is it?">
        <div className="flex items-center gap-2">
          <button type="button" onClick={locate} className="inline-flex h-10 items-center gap-2 rounded-lg border border-black/15 px-3 text-[13px] text-ink-100 hover:border-black/30">
            {gps === "busy" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Crosshair className="h-4 w-4 text-field" />} Use my GPS here
          </button>
          <span className="num font-mono text-[11px] text-ink-400">
            {loc ? `${loc.lat.toFixed(5)}, ${loc.lng.toFixed(5)}` : "—"} {pos ? "· GPS" : site ? "· site (stand at the shop and tap GPS)" : ""}
          </span>
        </div>
        {gps === "err" && <p className="text-xs text-warn">Location permission was denied. Allow it in the browser, or stand at the site.</p>}
      </Q>
      <Q n="03" label={<>Real price you saw — <span className="text-ink-400">{priceLabel.toLowerCase()}</span></>}>
        <NumberInput value={price} onChange={setPrice} prefix="₹" placeholder="from the menu / board / staff" allowEmpty min={1} />
      </Q>
      <Q n="04" label="Your rating of the place">
        <div className="flex gap-1.5" role="radiogroup" aria-label="Rating">
          {[1, 2, 3, 4, 5].map((v) => (
            <button type="button" key={v} role="radio" aria-checked={q === v} onClick={() => setQ(q === v ? null : v)} className={cn("h-11 flex-1 rounded-lg border text-[15px] transition-colors", q !== null && v <= q ? "border-observed bg-observed text-ink-950" : "border-black/10 text-ink-300")}>
              {v}
            </button>
          ))}
        </div>
        <p className="text-[11.5px] text-ink-500">1 = poor, 3 = average for the area, 5 = best in the area</p>
      </Q>
      <div className="grid grid-cols-2 gap-3">
        <Q n="05" label="Visitors / hour">
          <NumberInput value={vph} onChange={setVph} placeholder="count 10 min × 6" allowEmpty min={0} />
        </Q>
        <Q n="06" label="Opening hours">
          <input className={inputCls} value={hours} onChange={(e) => setHours(e.target.value)} placeholder="6am–10pm" maxLength={80} />
        </Q>
      </div>
      <SaveBtn busy={busy} disabled={!name.trim() || !loc}>Save competitor</SaveBtn>
    </form>
  );
}

function FootfallForm({ busy, onSave }: { busy: boolean; onSave: (d: RecordDraft) => void }) {
  const [count, setCount] = useState(0);
  const [running, setRunning] = useState(false);
  const [secs, setSecs] = useState(0);
  const [tod, setTod] = useState<string | null>(() => {
    const h = new Date().getHours();
    return h < 12 ? "morning" : h < 17 ? "afternoon" : h < 21 ? "evening" : "night";
  });
  const [weekend, setWeekend] = useState(() => [0, 6].includes(new Date().getDay()));
  const t = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (!running) return;
    t.current = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => {
      if (t.current) clearInterval(t.current);
    };
  }, [running]);
  const mins = Math.max(1, Math.round(secs / 60));
  const mm = String(Math.floor(secs / 60)).padStart(2, "0");
  const ss = String(secs % 60).padStart(2, "0");
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!tod || secs < 60) return;
        onSave({ kind: "footfall", data: { count, minutes: mins, time_of_day: tod, weekend } });
      }}
    >
      <div className="rounded-xl border border-black/[0.08] bg-black/[0.02] p-4">
        <div className="flex items-center justify-between">
          <span className="num font-mono text-2xl text-ink-100">{mm}:{ss}</span>
          <div className="flex gap-1.5">
            <button type="button" onClick={() => setRunning((r) => !r)} aria-label={running ? "Pause timer" : "Start timer"} className="flex h-10 w-10 items-center justify-center rounded-lg bg-black/[0.07] text-ink-100">
              {running ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            <button type="button" onClick={() => { setRunning(false); setSecs(0); setCount(0); }} aria-label="Reset" className="flex h-10 w-10 items-center justify-center rounded-lg bg-black/[0.04] text-ink-400">
              <RotateCcw className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <button type="button" onClick={() => setCount((c) => Math.max(0, c - 1))} aria-label="Minus one" className="flex h-16 w-16 items-center justify-center rounded-xl border border-black/10 text-ink-300"><Minus className="h-5 w-5" /></button>
          <button
            type="button"
            onClick={() => { setCount((c) => c + 1); if (!running) setRunning(true); }}
            className="flex h-16 flex-1 items-center justify-center gap-3 rounded-xl bg-accent text-white active:scale-[0.98]"
            aria-label="Count one person"
          >
            <Plus className="h-5 w-5" />
            <span className="num font-mono text-3xl">{count}</span>
          </button>
        </div>
        <p className="mt-3 text-[11.5px] text-ink-500">Stand at the site. Tap once per person walking past. Count for about 15 minutes.</p>
      </div>
      <Q n="01" label="Time of day">
        <Chips label="Time of day" value={tod} onChange={setTod} options={[{ v: "morning", l: "Morning" }, { v: "afternoon", l: "Afternoon" }, { v: "evening", l: "Evening" }, { v: "night", l: "Night" }]} />
      </Q>
      <label className="flex items-center gap-2 text-[13.5px] text-ink-200">
        <input type="checkbox" checked={weekend} onChange={(e) => setWeekend(e.target.checked)} className="h-4 w-4 accent-[var(--color-accent)]" /> Weekend
      </label>
      <SaveBtn busy={busy} disabled={secs < 60 || !tod}>{secs < 60 ? "Count for at least a minute" : `Save ${count} people in ${mins} min`}</SaveBtn>
    </form>
  );
}

function RentForm({ busy, onSave }: { busy: boolean; onSave: (d: RecordDraft) => void }) {
  const [rent, setRent] = useState<number | null>(null);
  const [dep, setDep] = useState<number | null>(null);
  const [area, setArea] = useState<number | null>(null);
  const [notes, setNotes] = useState("");
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (!rent) return;
        onSave({ kind: "rent", data: { monthly_rent: rent, deposit: dep, area_sqft: area, notes } });
      }}
    >
      <Q n="01" label="Monthly rent quoted">
        <NumberInput value={rent} onChange={setRent} prefix="₹" placeholder="e.g. 65000" allowEmpty min={1} />
      </Q>
      <div className="grid grid-cols-2 gap-3">
        <Q n="02" label="Deposit">
          <NumberInput value={dep} onChange={setDep} prefix="₹" placeholder="optional" allowEmpty min={0} />
        </Q>
        <Q n="03" label="Area">
          <NumberInput value={area} onChange={setArea} suffix="sq ft" placeholder="optional" allowEmpty min={1} />
        </Q>
      </div>
      <Q n="04" label="Who quoted it?">
        <input className={inputCls} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="owner / broker, floor, frontage…" maxLength={500} />
      </Q>
      <SaveBtn busy={busy} disabled={!rent}>Save rent quote</SaveBtn>
    </form>
  );
}
