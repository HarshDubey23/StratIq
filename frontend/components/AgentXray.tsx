"use client";

import { Dna, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge, ErrorState, Spinner, cn } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { CHANNEL_LABEL, MECH_LABEL, ORIGIN_LABEL, fmtParam, getRegistry, pctColor } from "@/lib/genome";
import { money } from "@/lib/format";
import type { AgentXray as Xray, GenomeRegistry } from "@/lib/types";

const MODE_LABEL: Record<string, string> = { walk: "walks", two_wheeler: "two-wheeler", car: "car", auto: "auto", bus: "bus", metro: "metro", cycle: "cycle" };

function cellBg(v: number) {
  const a = Math.min(1, Math.abs(v) / 2);
  return v >= 0 ? `rgba(52,211,153,${0.08 + a * 0.5})` : `rgba(244,63,94,${0.08 + a * 0.5})`;
}

export default function AgentXray({ runId, agent, onClose, price, className }: { runId: string; agent: number; onClose: () => void; price?: number; className?: string }) {
  const [x, setX] = useState<Xray | null>(null);
  const [reg, setReg] = useState<GenomeRegistry | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    let live = true;
    setX(null);
    setErr(null);
    Promise.all([api<Xray>(`/simulation-runs/${runId}/agents/${agent}`), getRegistry()])
      .then(([a, r]) => {
        if (!live) return;
        setX(a);
        setReg(r);
      })
      .catch((e) => live && setErr(e instanceof ApiError ? e.message : "Could not load this agent"));
    return () => {
      live = false;
    };
  }, [runId, agent]);

  const blocks = useMemo(() => {
    if (!reg) return [];
    const out: { key: string; label: string; idx: number[] }[] = [];
    reg.params.forEach((p, i) => {
      let b = out.find((o) => o.key === p.block);
      if (!b) {
        b = { key: p.block, label: reg.blocks[p.block] || p.block, idx: [] };
        out.push(b);
      }
      b.idx.push(i);
    });
    return out;
  }, [reg]);

  const ql = q.trim().toLowerCase();
  const match = (i: number) => !ql || (reg?.params[i].label.toLowerCase().includes(ql) ?? false) || (reg?.params[i].key.includes(ql) ?? false);
  const hp = hover !== null && reg ? reg.params[hover] : undefined;

  const s = x?.summary;
  const choice = x ? x.final_choice : -1;
  const chosen = x?.options.find((o) => o.idx === choice);
  const you = x?.options.find((o) => o.idx === 0);
  const shown = x ? x.options.slice(0, 4) : [];
  if (x && you && !shown.find((o) => o.idx === 0)) shown[shown.length - 1] = you;
  const channels = Object.keys(CHANNEL_LABEL);

  return (
    <div className={cn("flex flex-col overflow-hidden rounded-xl border border-accent/40 bg-ink-950/95 shadow-2xl shadow-black/60 backdrop-blur", className)}>
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <div className="flex items-center gap-2">
          <Dna className="h-4 w-4 text-agent" />
          <div>
            <div className="text-sm font-semibold text-ink-100">Agent #{agent.toLocaleString("en-IN")} — decision X-ray</div>
            <div className="text-[11px] text-ink-400">615-parameter synthetic genome · not a real person</div>
          </div>
        </div>
        <button onClick={onClose} aria-label="Close agent X-ray" className="rounded p-1 text-ink-400 hover:bg-ink-800 hover:text-ink-100"><X className="h-4 w-4" /></button>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {err && <ErrorState message={err} />}
        {!x && !err && <Spinner label="Rebuilding this agent's genome…" />}
        {x && s && reg && (
          <>
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <Badge>{Math.round(s.age)} yrs · {s.female ? "female" : "male"}</Badge>
              <Badge>{x.segment}</Badge>
              <Badge>{MODE_LABEL[x.mode] || x.mode}</Badge>
              <Badge>{s.dist_km} km from you</Badge>
              {typeof s.mpce === "number" && <Badge>spends ₹{Math.round(s.mpce).toLocaleString("en-IN")}/month per person</Badge>}
              <Badge>WTP {money(s.wtp)}</Badge>
              {price !== undefined && <Badge tone={s.wtp >= price ? "ok" : "danger"}>{s.wtp >= price ? "can afford you" : "you're above their WTP"}</Badge>}
              <Badge tone={choice === 0 ? "accent" : choice > 0 ? "warn" : "neutral"}>
                {!s.in_market ? "not in this market" : choice === 0 ? "YOUR CUSTOMER" : choice > 0 ? `chose ${chosen?.name || "a competitor"}` : "chose nothing"}
              </Badge>
              {!s.aware && s.in_market ? <Badge tone="warn">never heard of you</Badge> : null}
            </div>

            {/* decision table */}
            <div>
              <div className="mb-1.5 text-xs font-medium text-ink-200">Why this choice — utility by channel</div>
              {shown.length ? (
                <div className="overflow-x-auto rounded-lg border border-white/[0.06]">
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="bg-ink-900 text-ink-400">
                        <th className="px-2 py-1.5 text-left font-medium">Channel</th>
                        {shown.map((o) => (
                          <th key={o.idx} className={cn("px-2 py-1.5 text-right font-medium", o.idx === 0 && "text-accent", o.idx === choice && o.idx !== 0 && "text-observed")}>
                            <div className="max-w-24 truncate" title={o.name}>{o.idx === 0 ? "You" : o.name}</div>
                            <div className="text-[10px] font-normal text-ink-500">{o.reachable ? `${o.time_min} min` : "out of range"}</div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {channels.map((c) => (
                        <tr key={c} className="border-t border-white/[0.06]/70">
                          <td className="px-2 py-1 text-ink-300">{CHANNEL_LABEL[c]}</td>
                          {shown.map((o) => (
                            <td key={o.idx} className="num px-2 py-1 text-right" style={{ background: cellBg(o.parts[c] ?? 0) }}>{(o.parts[c] ?? 0).toFixed(2)}</td>
                          ))}
                        </tr>
                      ))}
                      <tr className="border-t border-ink-600 font-semibold">
                        <td className="px-2 py-1.5 text-ink-100">Total utility</td>
                        {shown.map((o) => <td key={o.idx} className="num px-2 py-1.5 text-right text-ink-100">{o.utility?.toFixed(2) ?? "—"}</td>)}
                      </tr>
                    </tbody>
                  </table>
                  <div className="border-t border-white/[0.06] bg-ink-900 px-2 py-1.5 text-[10px] text-ink-400">
                    Buying nothing is worth <span className="num text-ink-200">{x.outside_utility.toFixed(2)}</span> to this agent; personal noise scale {x.noise_scale.toFixed(2)}.
                    Habit and awareness (dynamic) are added during the day-by-day run.
                  </div>
                </div>
              ) : (
                <p className="text-xs text-ink-400">No business is within this agent&apos;s travel range.</p>
              )}
            </div>

            {x.drivers_vs_you.length > 0 && choice !== 0 && (
              <div>
                <div className="mb-1.5 text-xs font-medium text-ink-200">Individual parameters pushing them {choice > 0 ? `towards ${chosen?.name || "the competitor"}` : "away"}</div>
                <div className="space-y-1">
                  {x.drivers_vs_you.slice(0, 6).map((d) => (
                    <div key={d.key} className="flex items-center gap-2 text-[11px]">
                      <span className="w-44 shrink-0 truncate text-ink-300" title={d.label}>{d.label}</span>
                      <div className="relative h-2 flex-1 rounded bg-ink-800">
                        <div className={cn("absolute top-0 h-2 rounded", d.effect > 0 ? "left-1/2 bg-observed" : "right-1/2 bg-accent")} style={{ width: `${Math.min(50, Math.abs(d.effect) * 120)}%` }} />
                      </div>
                      <span className="num w-12 text-right text-ink-400">{d.z >= 0 ? "+" : ""}{d.z}σ</span>
                    </div>
                  ))}
                </div>
                <p className="mt-1 text-[10px] text-ink-500">Amber = favours their choice over you; cyan = favours you. σ = how unusual this agent is on that parameter.</p>
              </div>
            )}

            {/* genome */}
            <div>
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-ink-200">Full genome · 615 parameters</span>
                <label className="flex items-center gap-1 rounded border border-white/[0.07] bg-ink-900 px-1.5">
                  <Search className="h-3 w-3 text-ink-500" />
                  <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="find a parameter" className="h-6 w-32 bg-transparent text-[11px] outline-none" aria-label="Find a parameter" />
                </label>
              </div>
              <div className="space-y-1.5" onMouseLeave={() => setHover(null)}>
                {blocks.map((b) => (
                  <div key={b.key}>
                    <div className="text-[10px] text-ink-500">{b.label} <span className="text-ink-600">· {b.idx.length}</span></div>
                    <div className="mt-0.5 flex flex-wrap gap-[2px]">
                      {b.idx.map((i) => (
                        <div
                          key={i}
                          onMouseEnter={() => setHover(i)}
                          className={cn("h-[9px] w-[9px] rounded-[1px] transition-opacity", hover === i && "ring-1 ring-white", !match(i) && "opacity-15")}
                          style={{ background: pctColor(x.percentile[i]) }}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-2 min-h-[52px] rounded-md border border-white/[0.06] bg-ink-900 p-2 text-[11px]">
                {hp && hover !== null ? (
                  <>
                    <div className="flex justify-between gap-2"><span className="font-medium text-ink-100">{hp.label}</span><span className="num text-ink-100">{fmtParam(hp, x.genome[hover])}</span></div>
                    <div className="mt-0.5 flex flex-wrap gap-x-3 text-ink-400">
                      <span>{x.percentile[hover]}th percentile of population</span>
                      <span>{ORIGIN_LABEL[hp.origin]}</span>
                      <span>→ {MECH_LABEL[hp.mechanism] || hp.mechanism}{hp.feat ? ` × ${hp.feat.replace("attr_", "")}` : ""}</span>
                    </div>
                  </>
                ) : (
                  <span className="text-ink-500">Hover a cell. Colour = where this agent sits in the population: <span className="text-blue-400">low</span> · median · <span className="text-orange-400">high</span>.</span>
                )}
              </div>
            </div>
            <p className="text-[10px] leading-relaxed text-ink-500">{x.note} One agent represents ≈{Math.round(x.scale)} residents.</p>
          </>
        )}
      </div>
    </div>
  );
}
