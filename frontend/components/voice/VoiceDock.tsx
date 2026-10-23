"use client";

/**
 * Strata — the always-listening voice analyst.
 *
 * Two engines, same tools:
 *  - Realtime: ElevenLabs conversational agent (full-duplex, barge-in, natural voice). The agent's
 *    "client tools" run here in the browser and fetch real numbers from the StrataIQ API.
 *  - Browser: Web Speech API (continuous recognition) + the backend intent router + speech synthesis.
 *    Works without any third-party account; used automatically if the realtime engine can't start.
 *
 * Neither engine invents numbers: every figure comes from /assistant/facts or a real simulation run.
 */
import { ConversationProvider, useConversation } from "@elevenlabs/react";
import { AudioLines, Keyboard, Mic, MicOff, Send, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode } from "react";
import { cn } from "@/components/ui";
import { readScreen, sendStrategy } from "@/lib/screen";

const AGENT_ID = process.env.NEXT_PUBLIC_ELEVENLABS_AGENT_ID || "agent_3201m5jvb75gfymtmw8m34wck59b";

type Engine = "realtime" | "browser";
type Phase = "idle" | "connecting" | "listening" | "thinking" | "speaking";
interface Turn {
  who: "you" | "strata";
  text: string;
  ts: number;
}

const PAGES = ["overview", "market", "live", "genome", "simulation", "decisions", "report", "factors", "monitor"] as const;

function projectIdFrom(path: string): string | null {
  const m = path.match(/^\/app\/projects\/([0-9a-f-]{16,})/i);
  return m ? m[1] : null;
}

async function jfetch<T>(url: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const r = await fetch(url, {
    ...init,
    credentials: "include",
    headers: init?.json !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: init?.json !== undefined ? JSON.stringify(init.json) : init?.body,
  });
  const text = await r.text();
  const body = text ? JSON.parse(text) : null;
  if (!r.ok) throw new Error((body && (body.detail?.message || body.detail)) || `HTTP ${r.status}`);
  return body as T;
}

const SUGGESTIONS = {
  project: ["What do you see on this screen?", "How can I grow?", "Double the marketing", "How do agents decide?", "Kitne competitors hain?", "Try price ₹399"],
  general: ["What does StrataIQ do?", "Open the live demo", "Is the data real?"],
};

function VoiceDockInner() {
  const path = usePathname() || "/";
  const router = useRouter();
  const projectId = projectIdFrom(path);
  const pidRef = useRef(projectId);
  pidRef.current = projectId;
  const pathRef = useRef(path);
  pathRef.current = path;

  const [open, setOpen] = useState(false);
  const [engine, setEngine] = useState<Engine>("realtime");
  const [phase, setPhase] = useState<Phase>("idle");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [interim, setInterim] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");
  const [level, setLevel] = useState(0);
  const active = phase !== "idle";

  const push = useCallback((who: Turn["who"], text: string) => {
    if (!text?.trim()) return;
    setTurns((t) => [...t.slice(-7), { who, text: text.trim(), ts: Date.now() }]);
  }, []);

  // ---------------------------------------------------------------- shared tools (real data only)
  const tools = useMemo(
    () => ({
      get_market_facts: async () => {
        const pid = pidRef.current;
        if (!pid) return JSON.stringify({ no_project: true, product: "StrataIQ: real OSM competitors + WorldPop population + 10,000 synthetic agents + financial model" });
        try {
          return JSON.stringify(await jfetch(`/api/v1/projects/${pid}/assistant/facts`));
        } catch (e) {
          return JSON.stringify({ error: e instanceof Error ? e.message : "facts unavailable" });
        }
      },
      get_screen: async () => JSON.stringify(readScreen() || { page: pathRef.current, note: "This page publishes no numbers; use get_market_facts." }),
      get_insights: async () => {
        const pid = pidRef.current;
        if (!pid) return JSON.stringify({ error: "Open a project first." });
        const sc = readScreen();
        try {
          return JSON.stringify(await jfetch(`/api/v1/projects/${pid}/insights${sc?.scenario_id ? `?scenario_id=${sc.scenario_id}` : ""}`));
        } catch (e) {
          return JSON.stringify({ error: e instanceof Error ? e.message : "insights unavailable" });
        }
      },
      test_strategy: async (args: { price?: number; marketing_spend?: number; quality?: number; capacity_scale?: number; open_hour?: number; close_hour?: number }) => {
        const pid = pidRef.current;
        if (!pid) return JSON.stringify({ error: "Open a project first." });
        const sc = readScreen();
        const body: Record<string, number | string> = {};
        for (const [k, v] of Object.entries(args || {})) if (v !== null && v !== undefined && v !== "" && !Number.isNaN(Number(v))) body[k] = Number(v);
        if (sc?.scenario_id) body.from_scenario_id = String(sc.scenario_id);
        try {
          const out = await jfetch<{ scenario: { id: string } }>(`/api/v1/projects/${pid}/strategy`, { method: "POST", json: body });
          const onLive = pathRef.current.endsWith("/live");
          if (!onLive) router.push(`/app/projects/${pid}/live`);
          sendStrategy({ scenario_id: out.scenario.id, result: out });
          return JSON.stringify(out);
        } catch (e) {
          return JSON.stringify({ error: e instanceof Error ? e.message : "simulation failed" });
        }
      },
      test_price: async ({ price }: { price: number }) => {
        const pid = pidRef.current;
        if (!pid) return JSON.stringify({ error: "Open a project first." });
        try {
          const out = await jfetch<Record<string, unknown>>(`/api/v1/projects/${pid}/assistant/try-price`, { method: "POST", json: { price: Number(price) } });
          window.dispatchEvent(new CustomEvent("strataiq:refresh"));
          return JSON.stringify(out);
        } catch (e) {
          return JSON.stringify({ error: e instanceof Error ? e.message : "simulation failed" });
        }
      },
      navigate: async ({ page }: { page: string }) => {
        const pid = pidRef.current;
        if (!pid) return "No project is open.";
        const seg = PAGES.includes(page as (typeof PAGES)[number]) ? page : "overview";
        router.push(seg === "overview" ? `/app/projects/${pid}` : `/app/projects/${pid}/${seg}`);
        return `Opened ${seg}.`;
      },
      start_demo: async () => {
        try {
          const p = await jfetch<{ id: string }>(`/api/v1/demo/live`, { method: "POST" });
          router.push(`/app/projects/${p.id}/market`);
          return "Opened a live demo: a specialty café near Connaught Place with real OpenStreetMap competitors and WorldPop population.";
        } catch {
          router.push(`/sign-up?next=${encodeURIComponent("/app")}`);
          return "The user needs to create a free account first; I opened the sign-up page.";
        }
      },
    }),
    [router],
  );

  // ---------------------------------------------------------------- realtime engine (ElevenLabs)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const convo: any = useConversation({
    clientTools: tools,
    onConnect: () => setPhase("listening"),
    onDisconnect: () => setPhase("idle"),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onMessage: (m: any) => {
      const text = m?.message ?? m?.text;
      const src = m?.source ?? m?.role;
      if (text) push(src === "user" ? "you" : "strata", String(text));
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (e: any) => setErr(typeof e === "string" ? e : e?.message || "Voice connection error"),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);

  useEffect(() => {
    if (engine !== "realtime" || !active || phase === "connecting") return;
    setPhase(convo?.isSpeaking ? "speaking" : "listening");
  }, [convo?.isSpeaking, engine, active, phase]);

  // ---------------------------------------------------------------- browser engine (Web Speech)
  const recRef = useRef<{ stop: () => void; start: () => void; abort: () => void } | null>(null);
  const wantRec = useRef(false);
  const speakingRef = useRef(false);

  const speak = useCallback((text: string) => {
    return new Promise<void>((resolve) => {
      if (typeof window === "undefined" || !("speechSynthesis" in window)) return resolve();
      const u = new SpeechSynthesisUtterance(text.replace(/₹/g, "rupees "));
      const voices = window.speechSynthesis.getVoices();
      u.voice = voices.find((v) => v.lang === "en-IN") || voices.find((v) => v.lang.startsWith("en-GB")) || voices.find((v) => v.lang.startsWith("en")) || null;
      u.rate = 1.02;
      speakingRef.current = true;
      setPhase("speaking");
      try {
        recRef.current?.stop();
      } catch {
        /* not running */
      }
      u.onend = u.onerror = () => {
        speakingRef.current = false;
        if (wantRec.current) {
          setPhase("listening");
          try {
            recRef.current?.start();
          } catch {
            /* already running */
          }
        }
        resolve();
      };
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
    });
  }, []);

  const askBackend = useCallback(
    async (q: string) => {
      push("you", q);
      setPhase("thinking");
      const pid = pidRef.current;
      try {
        const out = await jfetch<{ answer: string; result?: unknown; actions?: { type: string; to?: string; scenario_id?: string }[] }>(pid ? `/api/v1/projects/${pid}/assistant/ask` : `/api/v1/assistant/ask`, {
          method: "POST",
          json: { question: q, page: path, screen: readScreen() },
        });
        push("strata", out.answer);
        const onLive = path.endsWith("/live");
        for (const a of out.actions || []) {
          if (a.type === "strategy") {
            sendStrategy({ scenario_id: a.scenario_id, result: out.result });
            continue;
          }
          if (a.type === "navigate" && a.to === "live" && onLive) continue;
          if (a.type === "refresh") window.dispatchEvent(new CustomEvent("strataiq:refresh"));
          if (a.type === "navigate" && a.to) router.push(a.to.startsWith("/") ? a.to : pid ? `/app/projects/${pid}/${a.to}` : "/app");
          if (a.type === "demo") void tools.start_demo();
        }
        await speak(out.answer);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "I couldn't reach the server.";
        push("strata", msg);
        await speak(msg);
      }
    },
    [path, push, router, speak, tools],
  );

  const startBrowser = useCallback(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const W = window as any;
    const SR = W.SpeechRecognition || W.webkitSpeechRecognition;
    if (!SR) {
      setErr("This browser has no speech recognition. Use Chrome or Edge, or type your question.");
      setTyping(true);
      setPhase("listening");
      return;
    }
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-IN";
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rec.onresult = (ev: any) => {
      let fin = "";
      let tmp = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const r = ev.results[i];
        if (r.isFinal) fin += r[0].transcript;
        else tmp += r[0].transcript;
      }
      setInterim(tmp);
      if (fin.trim() && !speakingRef.current) {
        setInterim("");
        void askBackend(fin.trim());
      }
    };
    rec.onend = () => {
      if (wantRec.current && !speakingRef.current) {
        try {
          rec.start();
        } catch {
          /* restarting too fast */
        }
      }
    };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    rec.onerror = (e: any) => {
      if (e?.error === "not-allowed") {
        setErr("Microphone permission was denied. Allow the mic in the address bar, or type instead.");
        wantRec.current = false;
        setTyping(true);
      }
    };
    recRef.current = rec;
    wantRec.current = true;
    rec.start();
    setPhase("listening");
  }, [askBackend]);

  const stopBrowser = useCallback(() => {
    wantRec.current = false;
    try {
      recRef.current?.abort();
    } catch {
      /* ignore */
    }
    recRef.current = null;
    if (typeof window !== "undefined") window.speechSynthesis?.cancel();
  }, []);

  // ---------------------------------------------------------------- mic level meter (both engines)
  const meter = useRef<{ ctx: AudioContext; stream: MediaStream; raf: number } | null>(null);
  const startMeter = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const ctx = new AudioContext();
      const an = ctx.createAnalyser();
      an.fftSize = 256;
      ctx.createMediaStreamSource(stream).connect(an);
      const buf = new Uint8Array(an.frequencyBinCount);
      const loop = () => {
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += (v - 128) ** 2;
        const rms = Math.sqrt(sum / buf.length) / 64;
        let out = 0;
        try {
          out = Number(convo?.getOutputVolume?.() || 0);
        } catch {
          out = 0;
        }
        setLevel((l) => l * 0.7 + Math.min(1, Math.max(rms, out, speakingRef.current ? 0.35 + 0.25 * Math.random() : 0)) * 0.3);
        if (meter.current) meter.current.raf = requestAnimationFrame(loop);
      };
      meter.current = { ctx, stream, raf: requestAnimationFrame(loop) };
      return true;
    } catch {
      return false;
    }
  }, [convo]);
  const stopMeter = useCallback(() => {
    const m = meter.current;
    if (!m) return;
    cancelAnimationFrame(m.raf);
    m.stream.getTracks().forEach((t) => t.stop());
    void m.ctx.close();
    meter.current = null;
    setLevel(0);
  }, []);

  // ---------------------------------------------------------------- start / stop
  const start = useCallback(
    async (which: Engine = engine) => {
      setErr(null);
      setOpen(true);
      setPhase("connecting");
      const micOk = await startMeter();
      if (!micOk) {
        setErr("No microphone access. Allow the mic, or type your question below.");
        setTyping(true);
        setPhase("listening");
        return;
      }
      if (which === "realtime") {
        try {
          await convo.startSession({ agentId: AGENT_ID, connectionType: "webrtc" });
          setEngine("realtime");
          return;
        } catch (e) {
          console.warn("realtime voice failed, falling back to browser voice", e);
          setErr("Realtime voice unavailable right now; switched to browser voice.");
        }
      }
      setEngine("browser");
      startBrowser();
    },
    [convo, engine, startBrowser, startMeter],
  );

  const stop = useCallback(async () => {
    try {
      if (engine === "realtime") await convo.endSession();
    } catch {
      /* already closed */
    }
    stopBrowser();
    stopMeter();
    setPhase("idle");
    setInterim("");
  }, [convo, engine, stopBrowser, stopMeter]);

  useEffect(() => () => {
    stopBrowser();
    stopMeter();
  }, [stopBrowser, stopMeter]);

  // keyboard: press V to talk / stop (outside inputs)
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      if (e.key.toLowerCase() === "v" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        if (active) void stop();
        else void start();
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [active, start, stop]);

  const sendTyped = async () => {
    const q = draft.trim();
    if (!q) return;
    setDraft("");
    if (engine === "realtime" && convo?.status === "connected" && typeof convo.sendUserMessage === "function") {
      push("you", q);
      convo.sendUserMessage(q);
    } else {
      await askBackend(q);
    }
  };

  const statusText: Record<Phase, string> = {
    idle: "Ask Strata",
    connecting: "Connecting",
    listening: "Listening",
    thinking: "Checking the numbers",
    speaking: "Speaking",
  };
  const hidden = path.startsWith("/r/") || path === "/sign-in" || path === "/sign-up";
  if (hidden) return null;

  return (
    <div className="no-print pointer-events-none fixed bottom-5 right-5 z-[90] flex flex-col items-end gap-3">
      {open && (
        <div className="panel pointer-events-auto w-[min(380px,calc(100vw-2.5rem))] overflow-hidden rounded-3xl" role="dialog" aria-label="Strata voice analyst">
          <div className="flex items-center gap-4 px-5 pt-5">
            <Orb level={level} phase={phase} size={64} />
            <div className="min-w-0 flex-1">
              <div className="font-display text-xl font-semibold tracking-tight" aria-live="polite">{statusText[phase]}</div>
              <div className="mt-0.5 text-xs text-ink-400">
                {engine === "realtime" ? "Realtime voice" : "Browser voice"} · {projectId ? "reading this project's live data" : "no project open"}
              </div>
            </div>
            <button onClick={() => { void stop(); setOpen(false); }} className="rounded-full p-1.5 text-ink-400 hover:bg-white/5 hover:text-ink-100" aria-label="Close voice analyst">
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-4 max-h-64 space-y-2.5 overflow-y-auto px-5 pb-1 text-[13.5px] leading-relaxed">
            {turns.length === 0 && !interim && (
              <p className="text-ink-400">
                Speak naturally, in English or Hinglish. Strata keeps listening and answers from the real model output, never from guesses.
              </p>
            )}
            {turns.map((t) => (
              <div key={t.ts + t.who} className={cn("flex", t.who === "you" ? "justify-end" : "justify-start")}>
                <div className={cn("max-w-[85%] rounded-2xl px-3.5 py-2", t.who === "you" ? "bg-white/[0.07] text-ink-100" : "bg-accent/10 text-ink-100 ring-1 ring-accent/25")}>{t.text}</div>
              </div>
            ))}
            {interim && (
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl bg-white/[0.04] px-3.5 py-2 italic text-ink-300">{interim}</div>
              </div>
            )}
          </div>

          {err && <p className="mx-5 mt-2 rounded-xl bg-warn/10 px-3 py-2 text-xs text-warn">{err}</p>}

          <div className="flex flex-wrap gap-1.5 px-5 pt-3">
            {(projectId ? SUGGESTIONS.project : SUGGESTIONS.general).map((s) => (
              <button
                key={s}
                onClick={() => (engine === "realtime" && convo?.status === "connected" && convo.sendUserMessage ? (push("you", s), convo.sendUserMessage(s)) : void askBackend(s))}
                className="rounded-full border border-white/10 px-2.5 py-1 text-[11.5px] text-ink-200 transition-colors hover:border-accent/50 hover:text-ink-100"
              >
                {s}
              </button>
            ))}
          </div>

          <div className="mt-4 flex items-center gap-2 border-t border-white/[0.06] px-3 py-3">
            {typing ? (
              <form className="flex flex-1 items-center gap-2" onSubmit={(e) => { e.preventDefault(); void sendTyped(); }}>
                <input
                  autoFocus
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Type a question…"
                  aria-label="Type a question"
                  className="h-10 flex-1 rounded-full border border-white/10 bg-white/[0.04] px-4 text-sm outline-none focus:border-accent/60"
                />
                <button type="submit" className="flex h-10 w-10 items-center justify-center rounded-full bg-accent text-ink-950" aria-label="Send"><Send className="h-4 w-4" /></button>
              </form>
            ) : (
              <div className="flex flex-1 items-center gap-2 px-2 text-xs text-ink-400">
                <AudioLines className="h-4 w-4 text-accent" /> Always listening while open · press V to stop
              </div>
            )}
            <button onClick={() => setTyping((x) => !x)} className="rounded-full p-2 text-ink-300 hover:bg-white/5 hover:text-ink-100" aria-label="Toggle keyboard input"><Keyboard className="h-4 w-4" /></button>
            <button
              onClick={() => (active ? void stop() : void start())}
              className={cn("flex h-10 items-center gap-1.5 rounded-full px-4 text-xs font-medium", active ? "bg-white/10 text-ink-100 hover:bg-white/15" : "bg-accent text-ink-950")}
            >
              {active ? <><MicOff className="h-3.5 w-3.5" /> Stop</> : <><Mic className="h-3.5 w-3.5" /> Talk</>}
            </button>
          </div>
          <div className="flex items-center justify-between px-5 pb-3 text-[11px] text-ink-500">
            <span>Engine</span>
            <div className="flex gap-1">
              {(["realtime", "browser"] as Engine[]).map((e) => (
                <button key={e} disabled={active} onClick={() => setEngine(e)} className={cn("rounded-full px-2 py-0.5", engine === e ? "bg-white/10 text-ink-100" : "hover:text-ink-200", active && "opacity-50")}>
                  {e === "realtime" ? "Realtime" : "Browser"}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <button
        onClick={() => (open ? (active ? void stop() : void start()) : (setOpen(true), void start()))}
        className="group pointer-events-auto flex items-center gap-3 rounded-full border border-white/10 bg-ink-900/80 py-2 pl-2 pr-5 shadow-[0_20px_60px_-20px_rgba(0,0,0,.9)] backdrop-blur-xl transition-[border-color,transform] duration-500 hover:-translate-y-0.5 hover:border-accent/40"
        aria-label={active ? "Stop voice analyst" : "Talk to Strata, the voice analyst"}
      >
        <Orb level={level} phase={phase} size={40} />
        <span className="text-left">
          <span className="block text-[13px] font-medium text-ink-100">{active ? statusText[phase] : "Talk to Strata"}</span>
          <span className="block text-[11px] text-ink-400">{active ? "tap to stop" : "voice analyst · press V"}</span>
        </span>
      </button>
    </div>
  );
}

function Orb({ level, phase, size }: { level: number; phase: Phase; size: number }) {
  const s = 1 + Math.min(0.35, level * 0.6);
  const busy = phase === "thinking" || phase === "connecting";
  return (
    <span className="relative inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }} aria-hidden>
      {phase === "listening" && <span className="absolute inset-0 rounded-full bg-accent/30" style={{ animation: "ping-soft 2.4s cubic-bezier(0,0,.2,1) infinite" }} />}
      <span
        className="absolute inset-0 rounded-full"
        style={{
          transform: `scale(${s})`,
          transition: "transform 90ms linear",
          background: "conic-gradient(from 210deg, #ff9f2e, #ff4f64, #6f8cff, #45e0a8, #ff9f2e)",
          filter: "blur(6px)",
          opacity: phase === "idle" ? 0.55 : 0.95,
          animation: busy ? "orb-spin 1.6s linear infinite" : "orb-spin 9s linear infinite",
        }}
      />
      <span
        className="absolute rounded-full"
        style={{
          inset: size * 0.12,
          background: "radial-gradient(circle at 35% 30%, #fff7ea 0%, #ffcf8f 18%, #ff9f2e 45%, #3a2a6a 85%, #0c111c 100%)",
          boxShadow: "inset 0 -6px 14px rgba(0,0,0,.45), 0 0 24px rgba(255,159,46,.45)",
          animation: phase === "idle" ? "orb-breathe 4s ease-in-out infinite" : undefined,
        }}
      />
    </span>
  );
}

/** Newer ElevenLabs SDKs require every conversation hook to live inside a ConversationProvider. */
export default function VoiceDock() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const Provider = ConversationProvider as unknown as ComponentType<{ children: ReactNode }> | undefined;
  if (!Provider) return <VoiceDockInner />;
  return (
    <Provider>
      <VoiceDockInner />
    </Provider>
  );
}
