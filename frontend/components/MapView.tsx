"use client";

import maplibregl, { type GeoJSONSource, type Map as MLMap } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

const STYLE_DARK = "https://tiles.openfreemap.org/styles/dark";
const STYLE_FALLBACK = "https://tiles.openfreemap.org/styles/positron";

export type LayerKey = "catchment" | "zones" | "competitors" | "agents" | "activity" | "buildings3d";

export interface MapCompetitor {
  id: string;
  name: string;
  lat: number;
  lng: number;
  kind: "osm" | "user" | "hypothetical" | "demo";
  inactive?: boolean;
}

export interface MapCandidate {
  id: string;
  label: string;
  lat: number;
  lng: number;
  active?: boolean;
}

export interface MapZone {
  lat: number;
  lng: number;
  value: number;
}

interface Props {
  center: [number, number]; // [lng, lat]
  zoom?: number;
  catchment?: { type: "Polygon"; coordinates: number[][][] } | null;
  zones?: MapZone[];
  zoneLabel?: string;
  competitors?: MapCompetitor[];
  candidates?: MapCandidate[];
  activity?: { lat: number; lng: number; name: string; kind: string }[];
  agents?: [number, number, number, number][];
  agentColor?: "red" | "choice";
  layers?: Partial<Record<LayerKey, boolean>>;
  selectedCompetitorId?: string | null;
  onCompetitorClick?: (id: string) => void;
  onCandidateClick?: (id: string) => void;
  onMapClick?: (lat: number, lng: number) => void;
  crosshair?: boolean;
  fitKey?: string;
  className?: string;
  pitch?: number;
}

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

function fc(features: GeoJSON.Feature[]): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features };
}

function pt(lng: number, lat: number, props: Record<string, unknown>): GeoJSON.Feature {
  return { type: "Feature", geometry: { type: "Point", coordinates: [lng, lat] }, properties: props };
}

export default function MapView(props: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const handlers = useRef(props);
  handlers.current = props;
  const [ready, setReady] = useState(false);
  const [styleNote, setStyleNote] = useState<string | null>(null);

  // ---- create map once ----
  useEffect(() => {
    let cancelled = false;
    let m: MLMap | null = null;
    (async () => {
      let style = STYLE_DARK;
      try {
        const r = await fetch(STYLE_DARK, { method: "GET" });
        if (!r.ok) style = STYLE_FALLBACK;
      } catch {
        style = STYLE_FALLBACK;
      }
      if (cancelled || !el.current) return;
      m = new maplibregl.Map({
        container: el.current,
        style,
        center: props.center,
        zoom: props.zoom ?? 13.2,
        pitch: props.pitch ?? 45,
        bearing: -12,
        attributionControl: { compact: true },
        maxPitch: 70,
      });
      map.current = m;
      m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
      m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
      m.on("error", (e) => {
        const msg = String((e as { error?: { message?: string } }).error?.message || "");
        if (msg.includes("style")) setStyleNote("Base map tiles could not be loaded. Data layers still work.");
      });
      m.on("load", () => {
        if (!m) return;
        const layers = m.getStyle().layers || [];
        const firstSymbol = layers.find((l) => l.type === "symbol")?.id;
        if (m.getSource("openmaptiles")) {
          try {
            m.addLayer(
              {
                id: "siq-buildings-3d",
                source: "openmaptiles",
                "source-layer": "building",
                type: "fill-extrusion",
                minzoom: 13.5,
                paint: {
                  "fill-extrusion-color": "#1a2330",
                  "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6],
                  "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
                  "fill-extrusion-opacity": 0.75,
                },
              },
              firstSymbol,
            );
          } catch {
            /* building layer not in this style */
          }
        }
        m.addSource("siq-catchment", { type: "geojson", data: EMPTY });
        m.addSource("siq-zones", { type: "geojson", data: EMPTY });
        m.addSource("siq-activity", { type: "geojson", data: EMPTY });
        m.addSource("siq-agents", { type: "geojson", data: EMPTY });
        m.addSource("siq-comps", { type: "geojson", data: EMPTY });
        m.addLayer({ id: "siq-catchment-fill", type: "fill", source: "siq-catchment", paint: { "fill-color": "#22d3ee", "fill-opacity": 0.05 } });
        m.addLayer({ id: "siq-catchment-line", type: "line", source: "siq-catchment", paint: { "line-color": "#22d3ee", "line-width": 1.5, "line-dasharray": [2, 2], "line-opacity": 0.8 } });
        m.addLayer({
          id: "siq-zones",
          type: "circle",
          source: "siq-zones",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 4, 14, 14, 16, 34],
            "circle-color": ["interpolate", ["linear"], ["get", "v"], 0, "#0b1a24", 0.25, "#0e4f5e", 0.5, "#0e7490", 0.75, "#22a9c4", 1, "#67e8f9"],
            "circle-opacity": 0.45,
            "circle-blur": 0.6,
          },
        });
        m.addLayer({
          id: "siq-activity",
          type: "circle",
          source: "siq-activity",
          paint: { "circle-radius": 3, "circle-color": "#94a3b8", "circle-opacity": 0.8, "circle-stroke-color": "#0b0f15", "circle-stroke-width": 1 },
        });
        m.addLayer({
          id: "siq-agents",
          type: "circle",
          source: "siq-agents",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 1.2, 15, 2.6],
            "circle-color": ["get", "c"],
            "circle-opacity": 0.85,
          },
        });
        m.addLayer({
          id: "siq-comps-halo",
          type: "circle",
          source: "siq-comps",
          paint: {
            "circle-radius": ["case", ["boolean", ["get", "sel"], false], 16, 10],
            "circle-color": ["get", "c"],
            "circle-opacity": ["case", ["boolean", ["get", "sel"], false], 0.35, 0.18],
          },
        });
        m.addLayer({
          id: "siq-comps",
          type: "circle",
          source: "siq-comps",
          paint: {
            "circle-radius": 5.5,
            "circle-color": ["get", "c"],
            "circle-stroke-color": ["case", ["boolean", ["get", "hyp"], false], "#ffffff", "#0b0f15"],
            "circle-stroke-width": ["case", ["boolean", ["get", "hyp"], false], 2, 1.5],
            "circle-opacity": ["case", ["boolean", ["get", "off"], false], 0.35, 1],
          },
        });
        const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10 });
        m.on("mouseenter", "siq-comps", (e) => {
          m!.getCanvas().style.cursor = "pointer";
          const f = e.features?.[0];
          if (f && f.geometry.type === "Point") {
            const k = String(f.properties?.k);
            const tag = k === "osm" ? "Observed (OpenStreetMap)" : k === "user" ? "User-entered" : k === "hypothetical" ? "Hypothetical" : "Demo";
            const div = document.createElement("div");
            const b = document.createElement("div");
            b.style.fontWeight = "600";
            b.textContent = String(f.properties?.name || "Unnamed");
            const s = document.createElement("div");
            s.style.opacity = "0.7";
            s.textContent = tag;
            div.append(b, s);
            popup.setLngLat(f.geometry.coordinates as [number, number]).setDOMContent(div).addTo(m!);
          }
        });
        m.on("mouseleave", "siq-comps", () => {
          m!.getCanvas().style.cursor = handlers.current.crosshair ? "crosshair" : "";
          popup.remove();
        });
        m.on("click", (e) => {
          const hit = m!.queryRenderedFeatures(e.point, { layers: ["siq-comps"] });
          if (hit.length && handlers.current.onCompetitorClick) {
            handlers.current.onCompetitorClick(String(hit[0].properties?.id));
            return;
          }
          handlers.current.onMapClick?.(e.lngLat.lat, e.lngLat.lng);
        });
        setReady(true);
      });
    })();
    return () => {
      cancelled = true;
      markers.current.forEach((mk) => mk.remove());
      m?.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- data updates ----
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    (m.getSource("siq-catchment") as GeoJSONSource).setData(props.catchment ? fc([{ type: "Feature", geometry: props.catchment, properties: {} }]) : EMPTY);
  }, [ready, props.catchment]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const zs = props.zones || [];
    const max = Math.max(1e-9, ...zs.map((z) => z.value));
    (m.getSource("siq-zones") as GeoJSONSource).setData(fc(zs.map((z) => pt(z.lng, z.lat, { v: z.value / max }))));
  }, [ready, props.zones]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    (m.getSource("siq-activity") as GeoJSONSource).setData(fc((props.activity || []).map((a) => pt(a.lng, a.lat, { name: a.name, kind: a.kind }))));
  }, [ready, props.activity]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const mode = props.agentColor || "red";
    const color = (choice: number) => (mode === "red" ? "#f43f5e" : choice === 0 ? "#22d3ee" : choice < 0 ? "#475569" : "#f43f5e");
    (m.getSource("siq-agents") as GeoJSONSource).setData(fc((props.agents || []).map(([lat, lng, seg, ch]) => pt(lng, lat, { c: color(ch), s: seg, ch }))));
  }, [ready, props.agents, props.agentColor]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const col = { osm: "#f59e0b", user: "#a78bfa", hypothetical: "#a78bfa", demo: "#fbbf24" };
    (m.getSource("siq-comps") as GeoJSONSource).setData(
      fc(
        (props.competitors || []).map((c) =>
          pt(c.lng, c.lat, { id: c.id, name: c.name, k: c.kind, c: col[c.kind], hyp: c.kind === "hypothetical", off: !!c.inactive, sel: c.id === props.selectedCompetitorId }),
        ),
      ),
    );
  }, [ready, props.competitors, props.selectedCompetitorId]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    markers.current.forEach((mk) => mk.remove());
    markers.current = (props.candidates || []).map((c) => {
      const d = document.createElement("button");
      d.type = "button";
      d.setAttribute("aria-label", `Candidate ${c.label}`);
      d.style.cssText = `display:flex;align-items:center;gap:6px;padding:3px 8px 3px 4px;border-radius:999px;font:600 11px Inter,sans-serif;cursor:pointer;
        background:${c.active ? "#22d3ee" : "#0f141c"};color:${c.active ? "#07090d" : "#e2e7ee"};border:1px solid ${c.active ? "#67e8f9" : "#3a485c"};box-shadow:0 2px 10px rgba(0,0,0,.5)`;
      const dot = document.createElement("span");
      dot.style.cssText = `width:10px;height:10px;border-radius:999px;background:${c.active ? "#07090d" : "#22d3ee"}`;
      const t = document.createElement("span");
      t.textContent = c.label;
      d.append(dot, t);
      d.addEventListener("click", (e) => {
        e.stopPropagation();
        handlers.current.onCandidateClick?.(c.id);
      });
      return new maplibregl.Marker({ element: d, anchor: "left", offset: [-9, 0] }).setLngLat([c.lng, c.lat]).addTo(m);
    });
  }, [ready, props.candidates]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const vis = (id: string, on: boolean | undefined) => m.getLayer(id) && m.setLayoutProperty(id, "visibility", on === false ? "none" : "visible");
    const L = props.layers || {};
    vis("siq-catchment-fill", L.catchment);
    vis("siq-catchment-line", L.catchment);
    vis("siq-zones", L.zones);
    vis("siq-comps", L.competitors);
    vis("siq-comps-halo", L.competitors);
    vis("siq-agents", L.agents);
    vis("siq-activity", L.activity);
    vis("siq-buildings-3d", L.buildings3d);
  }, [ready, props.layers]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    m.getCanvas().style.cursor = props.crosshair ? "crosshair" : "";
  }, [ready, props.crosshair]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const ring = props.catchment?.coordinates?.[0];
    if (ring && ring.length) {
      const b = new maplibregl.LngLatBounds(ring[0] as [number, number], ring[0] as [number, number]);
      ring.forEach((c) => b.extend(c as [number, number]));
      m.fitBounds(b, { padding: 40, duration: 900, pitch: props.pitch ?? 45 });
    } else {
      m.flyTo({ center: props.center, zoom: props.zoom ?? 13.2, duration: 800 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, props.fitKey]);

  return (
    <div className={`relative ${props.className || ""}`}>
      <div ref={el} className="absolute inset-0" />
      {!ready && <div className="absolute inset-0 flex items-center justify-center bg-ink-900 text-sm text-ink-400">Loading map…</div>}
      {styleNote && <div className="absolute left-2 top-2 rounded bg-ink-900/90 px-2 py-1 text-xs text-amber-200">{styleNote}</div>}
    </div>
  );
}
