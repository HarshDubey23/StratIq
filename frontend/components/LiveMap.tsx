"use client";

import maplibregl, { type GeoJSONSource, type Map as MLMap } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Abm } from "@/lib/types";
import { attachDeck, C, enhanceMap, pickStyle, popColor, type DeckHandle } from "@/lib/mapkit";
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

const SEG_COLORS = ["#E5484D", "#D97706", "#7C3AED"];
const MODE_COLORS = ["#16A34A", "#0284C7", "#DB2777", "#CA8A04", "#EA580C", "#9333EA", "#65A30D"];

function ageColor(a: number) {
  if (a < 15) return "#60A5FA";
  if (a < 30) return "#2F49FF";
  if (a < 50) return "#D97706";
  return "#E5484D";
}

export default function LiveMap(p: LiveMapProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const props = useRef(p);
  props.current = p;
  const [ready, setReady] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const deck = useRef<DeckHandle | null>(null);
  const [deckReady, setDeckReady] = useState(false);
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
      const style = await pickStyle();
      if (cancelled || !el.current) return;
      let m: MLMap;
      try {
        m = new maplibregl.Map({ container: el.current, style, center: p.center, zoom: 13.6, pitch: 58, bearing: -22, attributionControl: { compact: true }, maxPitch: 78 });
      } catch (e) {
        setNote(`Map could not start: ${e instanceof Error ? e.message : "WebGL unavailable"}`);
        return;
      }
      map.current = m;
      m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
      m.on("load", () => {
        enhanceMap(m, { buildingOpacity: 0.85 });
        attachDeck(m).then((d) => {
          if (cancelled || !d) return;
          deck.current = d;
          d.setTooltip((info) => (info.object as { tip?: string } | undefined)?.tip ?? null);
          setDeckReady(true);
        });
        for (const id of ["catch", "heat", "trails", "moving", "sel"]) m.addSource(id, { type: "geojson", data: EMPTY });
        m.addSource("idle", { type: "geojson", data: EMPTY, promoteId: "i" });
        m.addLayer({ id: "catch-line", type: "line", source: "catch", paint: { "line-color": "#2F49FF", "line-width": 1.4, "line-dasharray": [2, 2], "line-opacity": 0.7 } });
        m.addLayer({ id: "heat", type: "heatmap", source: "heat", paint: {
          "heatmap-weight": ["get", "w"], "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 11, 0.6, 15, 1.4],
          "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 11, 14, 14, 38, 16, 70],
          "heatmap-opacity": 0.4,
          "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.2, "rgba(150,165,255,0.22)", 0.45, "rgba(110,130,255,0.32)", 0.7, "rgba(229,72,77,0.32)", 1, "rgba(229,72,77,0.5)"],
        } });
        m.addLayer({ id: "trails", type: "line", source: "trails", paint: { "line-color": ["get", "c"], "line-width": 0.7, "line-opacity": 0.22 } });
        m.addLayer({ id: "idle", type: "circle", source: "idle", paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, ["case", ["boolean", ["feature-state", "cust"], false], 2.2, 1.3], 14, ["case", ["boolean", ["feature-state", "cust"], false], 3.8, 2.5], 16, ["case", ["boolean", ["feature-state", "cust"], false], 5.5, 3.8]],
          "circle-color": ["case", ["boolean", ["feature-state", "cust"], false], "#2F49FF", ["get", "c"]],
          "circle-opacity": ["case", ["boolean", ["feature-state", "cust"], false], 0.95, ["get", "o"]],
        } });
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
      deck.current?.destroy();
      deck.current = null;
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
    m.setLayoutProperty("trails", "visibility", "none");
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
      d.style.cssText = `width:${sz}px;height:${sz}px;border-radius:999px;background:${you ? "#2F49FF" : "#F59E0B"};border:2px solid #F5F3EE;box-shadow:0 0 0 ${you ? 6 : 3}px ${you ? "rgba(47,73,255,.28)" : "rgba(245,158,11,.28)"};${you ? "animation:siqpulse 1.6s infinite" : ""}`;
      return new maplibregl.Marker({ element: d }).setLngLat([b.lng, b.lat]).addTo(m);
    });
  }, [ready, p.abm]);

  // idle agents: static geometry, set once per run / colouring (10k points). Customer status is GPU feature-state.
  const lastFi = useRef(-1);
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const rows = p.abm.agents.rows;
    const color = (r: number[]) => {
      if (p.colorMode === "segment") return SEG_COLORS[r[ci.segment]] || "#E5484D";
      if (p.colorMode === "mode") return MODE_COLORS[r[ci.mode]] || "#E5484D";
      if (p.colorMode === "age") return ageColor(r[ci.age]);
      return r[ci.in_market] ? "#E5484D" : "#f4a3a6";
    };
    (m.getSource("idle") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: rows.map((r, i) => ({ type: "Feature", geometry: { type: "Point", coordinates: [r[ci.lng], r[ci.lat]] }, properties: { i, c: color(r), o: r[ci.in_market] ? 0.95 : 0.45 } })),
    });
    lastFi.current = -1;
  }, [ready, p.abm, p.colorMode, ci]);

  // per frame: only agents whose customer status changed get a feature-state update; trips redrawn
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const fi = p.frameIdx;
    const showCust = p.colorMode === "choice";
    const n = p.abm.n_agents;
    if (!showCust || fi < lastFi.current) {
      m.removeFeatureState({ source: "idle" });
      lastFi.current = -1;
    }
    if (showCust) {
      for (let i = 0; i < n; i++) {
        const cf = customerFrom[i];
        if (cf <= fi && cf > lastFi.current) m.setFeatureState({ source: "idle", id: i }, { cust: true });
      }
      lastFi.current = fi;
    }
    const rows = p.abm.agents.rows;
    const f = p.abm.frames[fi];
    const biz = p.abm.businesses;
    (m.getSource("trails") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: f
        ? f.a.map((a, k): GeoJSON.Feature => {
            const b = biz[f.c[k]] || biz[0];
            return { type: "Feature", geometry: { type: "LineString", coordinates: [[rows[a][ci.lng], rows[a][ci.lat]], [b.lng, b.lat]] }, properties: { c: f.c[k] === 0 ? "#2F49FF" : "#F59E0B" } };
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
          feats[k] = { type: "Feature", geometry: { type: "Point", coordinates: [lng, lat] }, properties: { i: f.a[k], c: f.c[k] === 0 ? "#8A9BFF" : "#D97706" } };
        }
        (m.getSource("moving") as GeoJSONSource).setData({ type: "FeatureCollection", features: feats });
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [ready, ci]);

  // deck.gl depth: business pillars (height = modeled share), faint population columns, demand arcs for this frame
  useEffect(() => {
    const d = deck.current;
    if (!deckReady || !d) return;
    const shares = p.abm.metrics.competitor_shares || [];
    const smax = Math.max(0.02, ...shares);
    const rows = p.abm.agents.rows;
    const f = p.abm.frames[p.frameIdx];
    const biz = p.abm.businesses;
    const zs = p.zones;
    const maxp = Math.max(1, ...zs.map((z) => z.population));
    const arcs = f && p.showTrails ? f.a.slice(0, 900).map((a, k) => ({ from: [rows[a][ci.lng], rows[a][ci.lat]], to: [(biz[f.c[k]] || biz[0]).lng, (biz[f.c[k]] || biz[0]).lat], you: f.c[k] === 0 })) : [];
    d.setLayers((DL) => [
      p.showHeat && new DL.ColumnLayer({
        id: "live-pop", data: zs, diskResolution: 6, radius: 130, extruded: true, coverage: 0.9, angle: 30,
        getPosition: (z: { lng: number; lat: number }) => [z.lng, z.lat], getElevation: (z: { population: number }) => 8 + (z.population / maxp) * 260,
        getFillColor: (z: { population: number }) => popColor(z.population / maxp, 70), updateTriggers: { getElevation: [maxp] },
      }),
      new DL.ArcLayer({
        id: "live-arcs", data: arcs, getSourcePosition: (x: { from: number[] }) => x.from as [number, number], getTargetPosition: (x: { to: number[] }) => x.to as [number, number],
        getSourceColor: (x: { you: boolean }) => (x.you ? [...C.you, 40] : [...C.comp, 30]) as [number, number, number, number],
        getTargetColor: (x: { you: boolean }) => (x.you ? [...C.you, 230] : [...C.comp, 180]) as [number, number, number, number],
        getWidth: (x: { you: boolean }) => (x.you ? 1.6 : 1), getHeight: 0.35, greatCircle: false,
      }),
      new DL.ColumnLayer({
        id: "live-biz", data: biz.map((b) => ({ ...b, tip: b.idx === 0 ? "Your business" : `${b.name} — modeled share ${Math.round((shares[b.idx - 1] || 0) * 100)}%` })),
        diskResolution: 24, radius: 20, extruded: true, pickable: true,
        getPosition: (b: { lng: number; lat: number }) => [b.lng, b.lat],
        getElevation: (b: { idx: number }) => (b.idx === 0 ? 1100 : 120 + ((shares[b.idx - 1] || 0) / smax) * 800),
        getFillColor: (b: { idx: number }) => (b.idx === 0 ? [...C.you, 255] : [...C.comp, 235]) as [number, number, number, number],
        updateTriggers: { getElevation: [smax] },
      }),
    ].filter(Boolean));
  }, [deckReady, p.abm, p.frameIdx, p.zones, p.showHeat, p.showTrails, ci]);

  // selected agent ring
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const r = p.selectedAgent !== null ? p.abm.agents.rows[p.selectedAgent] : null;
    (m.getSource("sel") as GeoJSONSource).setData(r ? { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Point", coordinates: [r[ci.lng], r[ci.lat]] }, properties: {} }] } : EMPTY);
  }, [ready, p.selectedAgent, p.abm, ci]);

  return (
    <div style={{ position: "absolute", inset: 0 }} data-testid="map">
      <style>{"@keyframes siqpulse{0%{box-shadow:0 0 0 0 rgba(47,73,255,.6)}70%{box-shadow:0 0 0 18px rgba(47,73,255,0)}100%{box-shadow:0 0 0 0 rgba(47,73,255,0)}}"}</style>
      <div ref={el} style={{ position: "absolute", inset: 0 }} />
      {!ready && !note && <div className="absolute inset-0 flex items-center justify-center bg-ink-950 text-sm text-ink-400">Loading live market…</div>}
      {note && <div className="absolute left-3 top-3 rounded bg-ink-900/90 px-2 py-1 text-xs text-amber-800">{note}</div>}
    </div>
  );
}
