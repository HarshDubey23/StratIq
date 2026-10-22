"use client";

import maplibregl, { type GeoJSONSource, type Map as MLMap } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Abm } from "@/lib/types";

const STYLE_DARK = "https://tiles.openfreemap.org/styles/dark";
const STYLE_FALLBACK = "https://tiles.openfreemap.org/styles/positron";
const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export interface LiveMapProps {
  center: [number, number];
  catchment?: { type: "Polygon"; coordinates: number[][][] } | null;
  zones: { lat: number; lng: number; population: number }[];
  abm: Abm;
  frameIdx: number;
  playing: boolean;
  speed: number;
  onFrame: (idx: number) => void;
  onAgent: (idx: number) => void;
  selectedAgent: number | null;
  showHeat: boolean;
  showTrails: boolean;
  colorMode: "choice" | "segment" | "mode" | "age";
}

const SEG_COLORS = ["#fb7185", "#fbbf24", "#a78bfa"];
const MODE_COLORS = ["#4ade80", "#38bdf8", "#f472b6", "#facc15", "#fb923c", "#c084fc", "#a3e635"];

function ageColor(a: number) {
  if (a < 15) return "#93c5fd";
  if (a < 30) return "#22d3ee";
  if (a < 50) return "#fbbf24";
  return "#f87171";
}

export default function LiveMap(p: LiveMapProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const props = useRef(p);
  props.current = p;
  const [ready, setReady] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const cols = p.abm.agents.columns;
  const ci = useMemo(() => Object.fromEntries(cols.map((c, i) => [c, i])) as Record<string, number>, [cols]);

  // first frame in which each agent chose you (to tint existing customers)
  const customerFrom = useMemo(() => {
    const arr = new Int32Array(p.abm.n_agents).fill(1e9);
    p.abm.frames.forEach((f, fi) => f.a.forEach((a, k) => { if (f.c[k] === 0 && arr[a] > fi) arr[a] = fi; }));
    return arr;
  }, [p.abm]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let style = STYLE_DARK;
      try {
        const r = await fetch(STYLE_DARK);
        if (!r.ok) style = STYLE_FALLBACK;
      } catch {
        style = STYLE_FALLBACK;
      }
      if (cancelled || !el.current) return;
      let m: MLMap;
      try {
        m = new maplibregl.Map({ container: el.current, style, center: p.center, zoom: 13.4, pitch: 52, bearing: -18, attributionControl: { compact: true }, maxPitch: 75 });
      } catch (e) {
        setNote(`Map could not start: ${e instanceof Error ? e.message : "WebGL unavailable"}`);
        return;
      }
      map.current = m;
      m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
      m.on("load", () => {
        const layers = m.getStyle().layers || [];
        const firstSymbol = layers.find((l) => l.type === "symbol")?.id;
        if (m.getSource("openmaptiles")) {
          try {
            m.addLayer({ id: "b3d", source: "openmaptiles", "source-layer": "building", type: "fill-extrusion", minzoom: 13,
              paint: { "fill-extrusion-color": "#18212d", "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6], "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0], "fill-extrusion-opacity": 0.8 } }, firstSymbol);
          } catch { /* style without buildings */ }
        }
        for (const id of ["catch", "heat", "trails", "idle", "moving", "sel"]) m.addSource(id, { type: "geojson", data: EMPTY });
        m.addLayer({ id: "catch-line", type: "line", source: "catch", paint: { "line-color": "#22d3ee", "line-width": 1.4, "line-dasharray": [2, 2], "line-opacity": 0.7 } });
        m.addLayer({ id: "heat", type: "heatmap", source: "heat", paint: {
          "heatmap-weight": ["get", "w"], "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 11, 0.6, 15, 1.4],
          "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 11, 14, 14, 38, 16, 70],
          "heatmap-opacity": 0.55,
          "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.2, "rgba(14,116,144,0.35)", 0.45, "rgba(34,211,238,0.5)", 0.7, "rgba(251,191,36,0.6)", 1, "rgba(244,63,94,0.75)"],
        } });
        m.addLayer({ id: "trails", type: "line", source: "trails", paint: { "line-color": ["get", "c"], "line-width": 0.7, "line-opacity": 0.22 } });
        m.addLayer({ id: "idle", type: "circle", source: "idle", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 1.1, 14, 2.2, 16, 3.5], "circle-color": ["get", "c"], "circle-opacity": ["get", "o"] } });
        m.addLayer({ id: "moving", type: "circle", source: "moving", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 1.8, 14, 3.2, 16, 5], "circle-color": ["get", "c"], "circle-opacity": 0.95, "circle-blur": 0.15 } });
        m.addLayer({ id: "sel", type: "circle", source: "sel", paint: { "circle-radius": 9, "circle-color": "rgba(255,255,255,0)", "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
        m.on("click", (e) => {
          const box: [maplibregl.PointLike, maplibregl.PointLike] = [[e.point.x - 5, e.point.y - 5], [e.point.x + 5, e.point.y + 5]];
          const hit = m.queryRenderedFeatures(box, { layers: ["moving", "idle"] });
          if (hit.length) props.current.onAgent(Number(hit[0].properties?.i));
        });
        m.on("mouseenter", "idle", () => (m.getCanvas().style.cursor = "pointer"));
        m.on("mouseleave", "idle", () => (m.getCanvas().style.cursor = ""));
        setReady(true);
      });
    })();
    return () => {
      cancelled = true;
      markers.current.forEach((x) => x.remove());
      map.current?.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // static layers
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const ok = p.catchment && Array.isArray(p.catchment.coordinates) && p.catchment.coordinates.length > 0;
    (m.getSource("catch") as GeoJSONSource).setData(ok ? { type: "FeatureCollection", features: [{ type: "Feature", geometry: p.catchment!, properties: {} }] } : EMPTY);
    const maxp = Math.max(1, ...p.zones.map((z) => z.population));
    (m.getSource("heat") as GeoJSONSource).setData({ type: "FeatureCollection", features: p.zones.map((z) => ({ type: "Feature", geometry: { type: "Point", coordinates: [z.lng, z.lat] }, properties: { w: z.population / maxp } })) });
    m.setLayoutProperty("heat", "visibility", p.showHeat ? "visible" : "none");
    m.setLayoutProperty("trails", "visibility", p.showTrails ? "visible" : "none");
    const ring = p.catchment?.coordinates?.[0];
    if (ring?.length) {
      const b = new maplibregl.LngLatBounds(ring[0] as [number, number], ring[0] as [number, number]);
      ring.forEach((c) => b.extend(c as [number, number]));
      m.fitBounds(b, { padding: 30, pitch: 52, duration: 0 });
    }
  }, [ready, p.catchment, p.zones, p.showHeat, p.showTrails]);

  // business markers
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    markers.current.forEach((x) => x.remove());
    const shares = p.abm.metrics.competitor_shares || [];
    markers.current = p.abm.businesses.map((b) => {
      const you = b.idx === 0;
      const d = document.createElement("div");
      const sz = you ? 22 : 10 + Math.min(14, (shares[b.idx - 1] || 0) * 60);
      d.title = you ? "Your business" : `${b.name} (modeled share ${Math.round((shares[b.idx - 1] || 0) * 100)}%)`;
      d.style.cssText = `width:${sz}px;height:${sz}px;border-radius:999px;background:${you ? "#22d3ee" : "#f59e0b"};border:2px solid #07090d;box-shadow:0 0 0 ${you ? 6 : 3}px ${you ? "rgba(34,211,238,.25)" : "rgba(245,158,11,.25)"};${you ? "animation:siqpulse 1.6s infinite" : ""}`;
      return new maplibregl.Marker({ element: d }).setLngLat([b.lng, b.lat]).addTo(m);
    });
  }, [ready, p.abm]);

  // idle agents + trails, recomputed per frame (and when colouring changes)
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const rows = p.abm.agents.rows;
    const fi = p.frameIdx;
    const color = (r: number[], i: number) => {
      if (p.colorMode === "segment") return SEG_COLORS[r[ci.segment]] || "#fb7185";
      if (p.colorMode === "mode") return MODE_COLORS[r[ci.mode]] || "#fb7185";
      if (p.colorMode === "age") return ageColor(r[ci.age]);
      if (customerFrom[i] <= fi) return "#22d3ee";
      return r[ci.in_market] ? "#f43f5e" : "#7f1d1d";
    };
    (m.getSource("idle") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: rows.map((r, i) => ({ type: "Feature", geometry: { type: "Point", coordinates: [r[ci.lng], r[ci.lat]] }, properties: { i, c: color(r, i), o: r[ci.in_market] ? 0.75 : 0.35 } })),
    });
    const f = p.abm.frames[fi];
    const biz = p.abm.businesses;
    (m.getSource("trails") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: f
        ? f.a.map((a, k): GeoJSON.Feature => {
            const b = biz[f.c[k]] || biz[0];
            return { type: "Feature", geometry: { type: "LineString", coordinates: [[rows[a][ci.lng], rows[a][ci.lat]], [b.lng, b.lat]] }, properties: { c: f.c[k] === 0 ? "#22d3ee" : "#f59e0b" } };
          })
        : [],
    });
  }, [ready, p.frameIdx, p.abm, p.colorMode, ci, customerFrom]);

  // moving agents: animation loop
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    let raf = 0;
    let start = performance.now();
    let fi = props.current.frameIdx;
    const frameMs = () => 900 / props.current.speed;
    const tick = (now: number) => {
      const P = props.current;
      if (P.frameIdx !== fi) {
        fi = P.frameIdx;
        start = now;
      }
      let t = (now - start) / frameMs();
      if (t >= 1 && P.playing) {
        const next = (fi + 1) % P.abm.frames.length;
        P.onFrame(next);
        fi = next;
        start = now;
        t = 0;
      }
      t = Math.min(1, t);
      const e = Math.sin(Math.PI * t);
      const f = P.abm.frames[fi];
      const rows = P.abm.agents.rows;
      const biz = P.abm.businesses;
      if (f) {
        const feats: GeoJSON.Feature[] = new Array(f.a.length);
        for (let k = 0; k < f.a.length; k++) {
          const r = rows[f.a[k]];
          const b = biz[f.c[k]] || biz[0];
          const lng = r[ci.lng] + (b.lng - r[ci.lng]) * e;
          const lat = r[ci.lat] + (b.lat - r[ci.lat]) * e;
          feats[k] = { type: "Feature", geometry: { type: "Point", coordinates: [lng, lat] }, properties: { i: f.a[k], c: f.c[k] === 0 ? "#67e8f9" : "#fbbf24" } };
        }
        (m.getSource("moving") as GeoJSONSource).setData({ type: "FeatureCollection", features: feats });
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [ready, ci]);

  // selected agent ring
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const r = p.selectedAgent !== null ? p.abm.agents.rows[p.selectedAgent] : null;
    (m.getSource("sel") as GeoJSONSource).setData(r ? { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Point", coordinates: [r[ci.lng], r[ci.lat]] }, properties: {} }] } : EMPTY);
  }, [ready, p.selectedAgent, p.abm, ci]);

  return (
    <div style={{ position: "absolute", inset: 0 }} data-testid="map">
      <style>{"@keyframes siqpulse{0%{box-shadow:0 0 0 0 rgba(34,211,238,.6)}70%{box-shadow:0 0 0 18px rgba(34,211,238,0)}100%{box-shadow:0 0 0 0 rgba(34,211,238,0)}}"}</style>
      <div ref={el} style={{ position: "absolute", inset: 0 }} />
      {!ready && !note && <div className="absolute inset-0 flex items-center justify-center bg-ink-950 text-sm text-ink-400">Loading live market…</div>}
      {note && <div className="absolute left-3 top-3 rounded bg-ink-900/90 px-2 py-1 text-xs text-amber-200">{note}</div>}
    </div>
  );
}
