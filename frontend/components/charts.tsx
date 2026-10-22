"use client";

import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { money, num } from "@/lib/format";
import type { SimResult } from "@/lib/types";

const AX = { stroke: "#5d6b80", fontSize: 11 };
const GRID = "#1b2431";
const TT = { contentStyle: { background: "#131a24", border: "1px solid #263243", borderRadius: 6, fontSize: 12 }, labelStyle: { color: "#b8c2cf" } };

function compactMoney(v: number) {
  return money(v, { compact: true }).replace("₹", "");
}

export function PriceCurve({ data, current, unit }: { data: NonNullable<SimResult["sensitivity"]>["price_curve"]; current: number; unit: string }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={data} margin={{ top: 10, right: 16, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="price" tickFormatter={(v) => `₹${num(v)}`} {...AX} />
        <YAxis yAxisId="p" tickFormatter={compactMoney} {...AX} width={56} />
        <YAxis yAxisId="u" orientation="right" tickFormatter={(v) => num(v)} {...AX} width={44} />
        <Tooltip {...TT} formatter={(v, n) => (String(n) === "units" ? [num(Number(v)), unit] : [money(Number(v)), "Operating profit"])} labelFormatter={(l) => `Price ₹${num(Number(l))}`} />
        <ReferenceLine yAxisId="p" y={0} stroke="#5d6b80" strokeDasharray="3 3" />
        <ReferenceLine yAxisId="p" x={current} stroke="#22d3ee" strokeDasharray="4 3" label={{ value: "current", fill: "#22d3ee", fontSize: 10, position: "top" }} />
        <Line yAxisId="p" type="monotone" dataKey="profit" stroke="#34d399" strokeWidth={2} dot={false} />
        <Line yAxisId="u" type="monotone" dataKey="units" stroke="#8a97a9" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function MarketingCurve({ data, current }: { data: NonNullable<SimResult["sensitivity"]>["marketing_curve"]; current: number }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <ComposedChart data={data} margin={{ top: 10, right: 16, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="spend" tickFormatter={(v) => compactMoney(v)} {...AX} />
        <YAxis tickFormatter={compactMoney} {...AX} width={56} />
        <Tooltip {...TT} formatter={(v) => [money(Number(v)), "Operating profit"]} labelFormatter={(l) => `Marketing ${money(Number(l))}/mo`} />
        <ReferenceLine y={0} stroke="#5d6b80" strokeDasharray="3 3" />
        <ReferenceLine x={current} stroke="#22d3ee" strokeDasharray="4 3" />
        <Line type="monotone" dataKey="profit" stroke="#34d399" strokeWidth={2} dot={{ r: 2 }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function Tornado({ data, base }: { data: NonNullable<SimResult["sensitivity"]>["tornado"]; base: number }) {
  const rows = data.slice(0, 8).map((t) => {
    const lo = Math.min(t.profit_at_low, t.profit_at_high) - base;
    const hi = Math.max(t.profit_at_low, t.profit_at_high) - base;
    return { label: t.label, range: [lo, hi] as [number, number], raw: t };
  });
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 30 + 30)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tickFormatter={(v) => (v > 0 ? "+" : "") + compactMoney(v)} {...AX} />
        <YAxis type="category" dataKey="label" width={190} {...AX} tick={{ fill: "#b8c2cf", fontSize: 11 }} />
        <Tooltip
          {...TT}
          formatter={(_v, _n, p) => {
            const r = (p as { payload: (typeof rows)[number] }).payload.raw;
            return [`${money(r.profit_at_low)} at ${r.low_value} · ${money(r.profit_at_high)} at ${r.high_value}`, "Profit range"];
          }}
        />
        <ReferenceLine x={0} stroke="#8a97a9" />
        <Bar dataKey="range" fill="#22d3ee" radius={2}>
          {rows.map((r, i) => <Cell key={i} fill={r.raw.status === "user" ? "#a78bfa" : "#0e7490"} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ProfitHistogram({ mc }: { mc: NonNullable<SimResult["monte_carlo"]> }) {
  const { counts, edges } = mc.histogram;
  const data = counts.map((c, i) => ({ x: ((edges[i] ?? 0) + (edges[i + 1] ?? 0)) / 2, c }));
  return (
    <ResponsiveContainer width="100%" height={130}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 4 }} barCategoryGap={1}>
        <XAxis dataKey="x" tickFormatter={compactMoney} {...AX} interval="preserveStartEnd" minTickGap={30} />
        <Tooltip {...TT} formatter={(v) => [`${v} draws`, "Count"]} labelFormatter={(l) => `Profit ≈ ${money(Number(l))}`} />
        <Bar dataKey="c">
          {data.map((d, i) => <Cell key={i} fill={d.x < 0 ? "#f87171" : "#34d399"} fillOpacity={0.8} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
