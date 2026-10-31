"use client";

import { Check, ClipboardList, MapPin, Send } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { LogoMark } from "@/components/brand";
import { FieldRecorder, KIND_META, type RecordDraft } from "@/components/field/FieldRecorder";
import { cn, ErrorState, inputCls, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { FieldBrief } from "@/lib/types";

/** The field researcher's app: opened from a link on a phone, no login, can only add data to one project. */
export default function FieldApp() {
  const { token } = useParams<{ token: string }>();
  const [b, setB] = useState<FieldBrief | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [who, setWho] = useState("");
  const [tab, setTab] = useState<"record" | "brief">("record");
  const [sent, setSent] = useState(false);

  const load = useCallback(async () => {
    try {
      setB(await api<FieldBrief>(`/field/${token}`));
      setErr(null);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "This field link could not be opened");
    }
  }, [token]);
  useEffect(() => {
    void load();
    try {
      setWho(localStorage.getItem("siq-field-who") || "");
    } catch {
      /* storage blocked */
    }
  }, [load]);
  useEffect(() => {
    if (b && !who && b.request.researcher_name) setWho(b.request.researcher_name);
  }, [b, who]);

  async function save(d: RecordDraft) {
    try {
      localStorage.setItem("siq-field-who", who);
    } catch {
      /* ignore */
    }
    await api(`/field/${token}/records`, { method: "POST", json: { ...d, collected_by: who } });
    await load();
  }
  async function submit() {
    await api(`/field/${token}/submit`, { method: "POST" });
    setSent(true);
    await load();
  }

  if (err) return <div className="mx-auto max-w-md p-5 pt-16"><ErrorState message={err} onRetry={load} /></div>;
  if (!b) return <div className="mx-auto max-w-md space-y-3 p-5 pt-16"><Skeleton className="h-24" /><Skeleton className="h-96" /></div>;

  const done = b.checklist.filter((t) => (b.counts[t.kind] ?? 0) >= t.target).length;
  return (
    <div className="mx-auto min-h-screen max-w-md pb-16">
      <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-ink-950/90 px-5 pb-3 pt-4 backdrop-blur-xl">
        <div className="flex items-center gap-2.5">
          <LogoMark size={22} />
          <span className="text-[13px] font-medium">StrataIQ Field</span>
          <span className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-field/40 bg-field/10 px-2 py-0.5 text-[11px] text-field">
            <span className="h-1.5 w-1.5 rounded-full bg-field" /> {b.request.status === "submitted" ? "Submitted" : "Collecting"}
          </span>
        </div>
        <h1 className="font-display mt-3 text-[22px] font-medium leading-tight tracking-tight">{b.project.category} · {b.project.name}</h1>
        {b.location && (
          <a href={`https://www.google.com/maps/search/?api=1&query=${b.location.lat},${b.location.lng}`} target="_blank" rel="noreferrer" className="mt-1 flex items-center gap-1.5 text-xs text-ink-400 hover:text-ink-100">
            <MapPin className="h-3.5 w-3.5 text-accent" /> {b.location.address || `${b.location.lat.toFixed(4)}, ${b.location.lng.toFixed(4)}`}{b.location.radius_km ? ` · within ${b.location.radius_km} km` : ""}
          </a>
        )}
        <div className="mt-3 grid grid-cols-2 gap-1 rounded-lg bg-white/[0.04] p-1" role="tablist">
          {(["record", "brief"] as const).map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={cn("h-8 rounded-md text-[13px] transition-colors", tab === t ? "bg-ink-100 text-ink-950" : "text-ink-300")}>
              {t === "record" ? "Record" : `Brief · ${done}/${b.checklist.length}`}
            </button>
          ))}
        </div>
      </header>

      <main className="px-5 pt-5">
        {tab === "record" ? (
          <>
            <label className="mb-5 block space-y-1.5 text-xs text-ink-400">
              Your name
              <input className={inputCls} value={who} onChange={(e) => setWho(e.target.value)} placeholder="So the analyst knows who collected it" maxLength={120} />
            </label>
            <FieldRecorder category={b.project.category} priceLabel={b.project.price_label} site={b.location} counts={b.counts} onSave={save} who={who} />
          </>
        ) : (
          <div className="space-y-4">
            {b.request.brief && (
              <div className="rounded-xl border border-accent/30 bg-accent/[0.07] p-4 text-sm leading-relaxed text-ink-100">
                <p className="idx mb-1.5">FROM THE ANALYST</p>
                {b.request.brief}
              </div>
            )}
            {b.checklist.map((t, i) => {
              const n = b.counts[t.kind] ?? 0;
              const M = KIND_META[t.kind];
              return (
                <div key={t.kind} className="rounded-xl border border-white/[0.07] p-4">
                  <div className="flex items-center gap-2">
                    <span className="idx">0{i + 1}</span>
                    <M.icon className={cn("h-4 w-4", M.tint)} />
                    <span className="text-sm font-medium">{t.title}</span>
                    <span className={cn("num ml-auto font-mono text-xs", n >= t.target ? "text-field" : "text-ink-400")}>{n}/{t.target}</span>
                  </div>
                  <p className="mt-2 text-[13px] leading-relaxed text-ink-400">{t.how}</p>
                </div>
              );
            })}
            {b.recent.length > 0 && (
              <div>
                <p className="idx mb-2 flex items-center gap-1.5"><ClipboardList className="h-3.5 w-3.5" /> LATEST</p>
                <ul className="space-y-1 text-[13px] text-ink-300">
                  {b.recent.map((r) => <li key={r.id} className="flex gap-2"><span className={KIND_META[r.kind].tint}>●</span> {KIND_META[r.kind].label} · {r.collected_by}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}

        <div className="mt-10 border-t border-white/[0.06] pt-6">
          {sent || b.request.status === "submitted" ? (
            <p className="flex items-center gap-2 text-sm text-field"><Check className="h-4 w-4" /> Sent to the analyst. You can keep adding data from this link.</p>
          ) : (
            <button onClick={submit} className="flex h-12 w-full items-center justify-center gap-2 rounded-lg border border-field/50 text-[15px] font-medium text-field hover:bg-field/10">
              <Send className="h-4 w-4" /> I&apos;m done — send to analyst
            </button>
          )}
          <p className="mt-4 text-center text-[11px] leading-relaxed text-ink-500">This link only adds data to one StrataIQ project. Do not record personal details of the people you interview.</p>
        </div>
      </main>
    </div>
  );
}
