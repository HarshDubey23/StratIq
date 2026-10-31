"use client";

import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { money, num } from "@/lib/format";
import type { SimResult } from "@/lib/types";

const AX = { stroke: "#75716A", fontSize: 11 };
const GRID = "#E7E4DC";
const TT = { contentStyle: { background: "#FFFFFF", border: "1px solid #E7E4DC", borderRadius: 6, fontSize: 12 }, labelStyle: { color: "#34322E" } };

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
        <ReferenceLine yAxisId="p" y={0} stroke="#75716A" strokeDasharray="3 3" />
        <ReferenceLine yAxisId="p" x={current} stroke="#2F49FF" strokeDasharray="4 3" label={{ value: "current", fill: "#2F49FF", fontSize: 10, position: "top" }} />
        <Line yAxisId="p" type="monotone" dataKey="profit" stroke="#0F766E" strokeWidth={2} dot={false} />
        <Line yAxisId="u" type="monotone" dataKey="units" stroke="#A9A59B" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
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
        <ReferenceLine y={0} stroke="#75716A" strokeDasharray="3 3" />
        <ReferenceLine x={current} stroke="#2F49FF" strokeDasharray="4 3" />
        <Line type="monotone" dataKey="profit" stroke="#0F766E" strokeWidth={2} dot={{ r: 2 }} />
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
        <YAxis type="category" dataKey="label" width={190} {...AX} tick={{ fill: "#34322E", fontSize: 11 }} />
        <Tooltip
          {...TT}
          formatter={(_v, _n, p) => {
            const r = (p as { payload: (typeof rows)[number] }).payload.raw;
            return [`${money(r.profit_at_low)} at ${r.low_value} · ${money(r.profit_at_high)} at ${r.high_value}`, "Profit range"];
          }}
        />
        <ReferenceLine x={0} stroke="#A9A59B" />
        <Bar dataKey="range" fill="#2F49FF" radius={2}>
          {rows.map((r, i) => <Cell key={i} fill={r.raw.status === "user" ? "#7C3AED" : "#9AA8FF"} />)}
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
          {data.map((d, i) => <Cell key={i} fill={d.x < 0 ? "#E5484D" : "#0F766E"} fillOpacity={0.8} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
