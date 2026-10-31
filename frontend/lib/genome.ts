import { api } from "@/lib/api";
import type { GenomeParam, GenomeRegistry } from "@/lib/types";

let registryPromise: Promise<GenomeRegistry> | null = null;

/** The 615-parameter registry is static per deployment: fetch once per page load. */
export function getRegistry(): Promise<GenomeRegistry> {
  if (!registryPromise) {
    registryPromise = api<GenomeRegistry>("/genome/registry").catch((e) => {
      registryPromise = null;
      throw e;
    });
  }
  return registryPromise;
}

export const CHANNEL_LABEL: Record<string, string> = {
  price: "Price vs their WTP",
  quality: "Quality",
  travel: "Travel & distance",
  time_fit: "Opening-hours fit",
  attributes: "What they value (40 attributes)",
  expectation: "Below their minimums",
  trust_novelty: "Trust vs novelty",
  lifestyle_fit: "Lifestyle & habits",
};

export const MECH_LABEL: Record<string, string> = {
  utility: "Choice utility",
  price: "Price channel",
  travel: "Travel channel",
  time_fit: "Opening-hours fit",
  expectation: "Expectation gap",
  participation: "Being in the market",
  outside: "Outside option",
  awareness: "Awareness",
  social: "Word of mouth",
  retention: "Retention & churn",
  noise: "Decision noise",
  placement: "Placement",
};

export const GROUP_COLOR: Record<string, string> = {
  you: "#2F49FF",
  competitor: "#F59E0B",
  none: "#64748b",
  not_in_market: "#D8D4CA",
};
export const GROUP_LABEL: Record<string, string> = {
  you: "Chose you",
  competitor: "Chose a competitor",
  none: "In market, chose nothing",
  not_in_market: "Not in this market",
};

/** Diverging palette for percentiles 0-100: deep blue (low) -> near-black (median) -> amber/rose (high). */
export function pctRGB(p: number): [number, number, number] {
  const t = Math.max(0, Math.min(100, p)) / 100;
  const lo: [number, number, number] = [37, 99, 235];
  const mid: [number, number, number] = [246, 244, 239];
  const hi: [number, number, number] = [251, 146, 60];
  const top: [number, number, number] = [244, 63, 94];
  if (t < 0.5) {
    const k = t / 0.5;
    return [lo[0] + (mid[0] - lo[0]) * k, lo[1] + (mid[1] - lo[1]) * k, lo[2] + (mid[2] - lo[2]) * k];
  }
  const k = (t - 0.5) / 0.5;
  if (k < 0.75) {
    const q = k / 0.75;
    return [mid[0] + (hi[0] - mid[0]) * q, mid[1] + (hi[1] - mid[1]) * q, mid[2] + (hi[2] - mid[2]) * q];
  }
  const q = (k - 0.75) / 0.25;
  return [hi[0] + (top[0] - hi[0]) * q, hi[1] + (top[1] - hi[1]) * q, hi[2] + (top[2] - hi[2]) * q];
}

export function pctColor(p: number): string {
  const [r, g, b] = pctRGB(p);
  return `rgb(${Math.round(r)},${Math.round(g)},${Math.round(b)})`;
}

export function fmtParam(p: GenomeParam | undefined, v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  if (!p) return String(v);
  if (p.key === "ev_female" || p.key === "ev_in_market" || p.key === "ev_reach_site") return v ? "yes" : "no";
  if (p.key === "ev_lat" || p.key === "ev_lng") return v.toFixed(5);
  if (p.unit === "id" || p.unit === "count" || p.unit === "rank" || p.unit === "people") return Math.round(v).toLocaleString("en-IN");
  if (p.unit === "0-1" || p.unit === "share") return `${Math.round(v * 100)}%`;
  if (p.unit === "z") return (v >= 0 ? "+" : "") + v.toFixed(2) + "σ";
  if (p.unit === "×") return v.toFixed(2) + "×";
  if (p.unit === "km") return v.toFixed(2) + " km";
  if (p.unit === "min") return v.toFixed(1) + " min";
  if (p.unit === "years") return Math.round(v) + " yrs";
  if (p.unit.startsWith("₹")) return "₹" + Math.round(v).toLocaleString("en-IN") + p.unit.slice(1);
  return Math.abs(v) >= 100 ? Math.round(v).toLocaleString("en-IN") : v.toFixed(2);
}

export const ORIGIN_LABEL: Record<string, string> = {
  evidence: "Measured from real geography",
  latent: "Latent trait (correlated draw)",
  generated: "Generated from traits + noise",
};
