/** Purely illustrative, static market visual for the landing page. Contains no real data. */

function rng(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

export function MarketPreview() {
  const r = rng(7);
  const cx = 300;
  const cy = 210;
  const agents = Array.from({ length: 260 }, () => {
    const a = r() * Math.PI * 2;
    const d = Math.sqrt(r()) * 175;
    const cluster = r() < 0.5 ? { x: -60, y: -40 } : { x: 70, y: 50 };
    const t = r() < 0.65;
    return { x: cx + (t ? cluster.x * 0.6 : 0) + Math.cos(a) * d * (t ? 0.55 : 1), y: cy + (t ? cluster.y * 0.6 : 0) + Math.sin(a) * d * (t ? 0.55 : 1), you: r() < 0.22 };
  });
  const comps = [
    { x: 410, y: 140 },
    { x: 180, y: 300 },
    { x: 220, y: 120 },
    { x: 440, y: 300 },
  ];
  const roads: string[] = [];
  for (let i = 0; i < 9; i++) {
    roads.push(`M ${-20 + i * 80} 0 L ${40 + i * 70} 420`);
    roads.push(`M 0 ${30 + i * 50} L 600 ${10 + i * 52}`);
  }
  return (
    <div className="relative overflow-hidden rounded-xl border border-white/[0.07] bg-ink-900 shadow-2xl shadow-black/40">
      <div className="flex items-center justify-between border-b border-white/[0.07] px-4 py-2 text-[11px] text-ink-300">
        <span className="font-medium text-ink-200">Market Reality Map</span>
        <span className="rounded border border-warn/40 bg-warn/10 px-1.5 py-px font-medium text-warn">Illustrative preview — not real data</span>
      </div>
      <div className="grid md:grid-cols-[1.45fr_1fr]">
        <svg viewBox="0 0 600 420" className="h-full w-full bg-[#0a0e14]" role="img" aria-label="Illustrative map of a local market with a candidate location, competitors and synthetic customers">
          <g style={{ transform: "perspective(900px) rotateX(18deg)", transformOrigin: "50% 60%" }}>
            {roads.map((d, i) => (
              <path key={i} d={d} stroke="#1c2633" strokeWidth={i % 3 === 0 ? 3 : 1.2} fill="none" />
            ))}
            {Array.from({ length: 34 }, (_, i) => {
              const x = (i * 97) % 560 + 10;
              const y = (i * 53) % 380 + 15;
              return <rect key={i} x={x} y={y} width={18 + (i % 4) * 6} height={12 + (i % 3) * 6} fill="#121a25" stroke="#1d2836" />;
            })}
            <circle cx={cx} cy={cy} r={178} fill="rgba(34,211,238,0.05)" stroke="rgba(34,211,238,0.5)" strokeDasharray="5 5" />
            {agents.map((a, i) => (
              <circle key={i} cx={a.x} cy={a.y} r={1.9} fill={a.you ? "#FF9F2E" : "#FF4F64"} opacity={a.you ? 0.95 : 0.7} />
            ))}
            {comps.map((c, i) => (
              <g key={i}>
                <circle cx={c.x} cy={c.y} r={9} fill="rgba(245,158,11,0.2)" />
                <circle cx={c.x} cy={c.y} r={5} fill="#6F8CFF" stroke="#0a0e14" strokeWidth={1.5} />
              </g>
            ))}
            <circle cx={cx} cy={cy} r={16} fill="rgba(34,211,238,0.18)" />
            <circle cx={cx} cy={cy} r={7} fill="#FF9F2E" stroke="#0a0e14" strokeWidth={2} />
          </g>
        </svg>
        <div className="space-y-4 border-t border-white/[0.07] p-4 md:border-l md:border-t-0">
          <div>
            <div className="text-[11px] text-ink-400">Scenario comparison (illustrative)</div>
            <div className="mt-2 space-y-2">
              {[
                { n: "Baseline ₹1,800", w: 46, c: "bg-ink-400" },
                { n: "Lower price ₹1,500", w: 63, c: "bg-accent" },
                { n: "Location B", w: 38, c: "bg-ink-500" },
              ].map((b) => (
                <div key={b.n}>
                  <div className="flex justify-between text-[11px] text-ink-300">
                    <span>{b.n}</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded bg-ink-800">
                    <div className={`h-1.5 rounded ${b.c}`} style={{ width: `${b.w}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="text-[11px] text-ink-400">Affordability by segment (illustrative)</div>
            <div className="mt-2 flex items-end gap-2">
              {[38, 62, 88].map((h, i) => (
                <div key={i} className="flex flex-1 flex-col items-center gap-1">
                  <div className="flex h-16 w-full items-end">
                    <div className="w-full rounded-t bg-model/70" style={{ height: `${h}%` }} />
                  </div>
                  <span className="text-[10px] text-ink-400">{["Budget", "Mainstream", "Premium"][i]}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="space-y-1.5 text-[11px] text-ink-300">
            <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-accent" /> Candidate location / customers choosing it</div>
            <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-observed" /> Competitors from map data</div>
            <div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-agent" /> Synthetic customers (simulated, not real people)</div>
          </div>
        </div>
      </div>
    </div>
  );
}
