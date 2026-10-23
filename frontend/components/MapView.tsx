"use client";

import maplibregl, { type GeoJSONSource, type Map as MLMap } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { attachDeck, C, enhanceMap, metersPerZoneRadius, pickStyle, popColor, type DeckHandle } from "@/lib/mapkit";

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
  /** Fill the nearest positioned ancestor (absolute, inset 0). */
  fill?: boolean;
  /** Real-depth layers: population as 3D hex columns, competitors as pillars (height = modeled customers). */
  depth?: boolean;
  zoneSpacingKm?: number | null;
  competitorWeight?: Record<string, number>;
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
  const deck = useRef<DeckHandle | null>(null);
  const [deckReady, setDeckReady] = useState(false);

  // ---- create map once ----
  useEffect(() => {
    let cancelled = false;
    let m: MLMap | null = null;
    (async () => {
      const style = await pickStyle();
      if (cancelled || !el.current) return;
      try {
      m = new maplibregl.Map({
        container: el.current,
        style,
        center: props.center,
        zoom: props.zoom ?? 13.2,
        pitch: props.pitch ?? 55,
        bearing: -18,
        attributionControl: { compact: true },
        maxPitch: 78,
      });
      } catch (err) {
        setStyleNote(`The map could not start in this browser (${err instanceof Error ? err.message : "WebGL unavailable"}). Data panels still work.`);
        return;
      }
      map.current = m;
      m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
      m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
      m.on("error", (e) => {
        const msg = String((e as { error?: { message?: string } }).error?.message || "");
        if (msg.includes("style")) setStyleNote("Base map tiles could not be loaded. Data layers still work.");
      });
      m.on("load", () => {
        if (!m) return;
        enhanceMap(m);
        attachDeck(m).then((d) => {
          if (cancelled || !d) return;
          deck.current = d;
          d.setTooltip((info) => {
            const o = info.object as { tip?: string } | undefined;
            return o?.tip ?? null;
          });
          setDeckReady(true);
        });
        m.addSource("siq-catchment", { type: "geojson", data: EMPTY });
        m.addSource("siq-zones", { type: "geojson", data: EMPTY });
        m.addSource("siq-activity", { type: "geojson", data: EMPTY });
        m.addSource("siq-agents", { type: "geojson", data: EMPTY });
        m.addSource("siq-comps", { type: "geojson", data: EMPTY });
        m.addLayer({ id: "siq-catchment-fill", type: "fill", source: "siq-catchment", paint: { "fill-color": "#FF9F2E", "fill-opacity": 0.035 } });
        m.addLayer({ id: "siq-catchment-line", type: "line", source: "siq-catchment", paint: { "line-color": "#FF9F2E", "line-width": 1.5, "line-dasharray": [2, 2], "line-opacity": 0.8 } });
        m.addLayer({
          id: "siq-zones",
          type: "circle",
          source: "siq-zones",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 4, 14, 14, 16, 34],
            "circle-color": ["interpolate", ["linear"], ["get", "v"], 0, "#0b1a24", 0.25, "#0e4f5e", 0.5, "#8A4B0F", 0.75, "#E0801C", 1, "#FFC27A"],
            "circle-opacity": 0.45,
            "circle-blur": 0.6,
          },
        });
        m.addLayer({
          id: "siq-activity",
          type: "circle",
          source: "siq-activity",
          paint: { "circle-radius": 3, "circle-color": "#94a3b8", "circle-opacity": 0.8, "circle-stroke-color": "#080C15", "circle-stroke-width": 1 },
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
            "circle-stroke-color": ["case", ["boolean", ["get", "hyp"], false], "#ffffff", "#080C15"],
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
      deck.current?.destroy();
      deck.current = null;
      m?.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- data updates ----
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const ok = props.catchment && Array.isArray(props.catchment.coordinates) && props.catchment.coordinates.length > 0;
    (m.getSource("siq-catchment") as GeoJSONSource).setData(ok ? fc([{ type: "Feature", geometry: props.catchment!, properties: {} }]) : EMPTY);
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
    const color = (choice: number) => (mode === "red" ? "#FF4F64" : choice === 0 ? "#FF9F2E" : choice < 0 ? "#475569" : "#FF4F64");
    (m.getSource("siq-agents") as GeoJSONSource).setData(fc((props.agents || []).map(([lat, lng, seg, ch]) => pt(lng, lat, { c: color(ch), s: seg, ch }))));
  }, [ready, props.agents, props.agentColor]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const col = { osm: "#6F8CFF", user: "#C59BFF", hypothetical: "#C59BFF", demo: "#fbbf24" };
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
      d.style.cssText = `display:flex;align-items:center;gap:6px;padding:3px 8px 3px 4px;border-radius:999px;font:600 11px Geist,sans-serif;cursor:pointer;
        background:${c.active ? "#FF9F2E" : "#0C111C"};color:${c.active ? "#04060B" : "#ECEFF5"};border:1px solid ${c.active ? "#FFC27A" : "#39475F"};box-shadow:0 2px 10px rgba(0,0,0,.5)`;
      const dot = document.createElement("span");
      dot.style.cssText = `width:10px;height:10px;border-radius:999px;background:${c.active ? "#04060B" : "#FF9F2E"}`;
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
    vis("siq-zones", props.depth === false ? L.zones : false);
    vis("siq-comps", L.competitors);
    vis("siq-comps-halo", L.competitors);
    vis("siq-agents", L.agents);
    vis("siq-activity", L.activity);
    vis("siq-3d-buildings", L.buildings3d);
  }, [ready, props.layers]);

  // ---- deck.gl depth layers ----
  useEffect(() => {
    const d = deck.current;
    if (!deckReady || !d) return;
    const L = props.layers || {};
    const depth = props.depth !== false;
    const zs = props.zones || [];
    const max = Math.max(1e-9, ...zs.map((z) => z.value));
    const radius = metersPerZoneRadius(props.zoneSpacingKm);
    const w = props.competitorWeight || {};
    const wmax = Math.max(1e-9, ...Object.values(w));
    const comps = (props.competitors || []).filter((c) => !c.inactive);
    d.setLayers((DL) => [
      depth && L.zones !== false && zs.length > 0 &&
        new DL.ColumnLayer({
          id: "pop-columns", data: zs, diskResolution: 6, radius, extruded: true, coverage: 0.92, angle: 30,
          getPosition: (z: MapZone) => [z.lng, z.lat], getElevation: (z: MapZone) => 15 + (z.value / max) * 520,
          getFillColor: (z: MapZone) => popColor(z.value / max, 120), pickable: true, material: { ambient: 0.5, diffuse: 0.6, shininess: 20 },
          transitions: { getElevation: { duration: 900 } },
          updateTriggers: { getElevation: [max], getFillColor: [max] },
        }),
      depth && L.competitors !== false &&
        new DL.ColumnLayer({
          id: "comp-pillars", data: comps.map((c) => ({ ...c, tip: `${c.name || "Unnamed"} — ${c.kind === "osm" ? "observed in OpenStreetMap" : c.kind === "user" ? "entered by you" : c.kind}${w[c.id] ? `\nmodeled ${Math.round(w[c.id])} customers/mo` : ""}` })),
          diskResolution: 20, radius: 16, extruded: true,
          getPosition: (c: MapCompetitor) => [c.lng, c.lat], getElevation: (c: MapCompetitor) => 90 + ((w[c.id] || 0) / wmax) * 760,
          getFillColor: (c: MapCompetitor) => (c.kind === "osm" ? [...C.comp, 235] : [...C.user, 235]) as [number, number, number, number],
          pickable: true, onClick: (info: { object?: MapCompetitor }) => { if (info.object) handlers.current.onCompetitorClick?.(info.object.id); },
          transitions: { getElevation: { duration: 900 } }, updateTriggers: { getElevation: [wmax, Object.keys(w).length] },
        }),
      depth && (props.candidates || []).length > 0 &&
        new DL.ColumnLayer({
          id: "site-beacon", data: (props.candidates || []).map((c) => ({ ...c, tip: `${c.label} — your candidate site` })), diskResolution: 32, radius: 24, extruded: true,
          getPosition: (c: MapCandidate) => [c.lng, c.lat], getElevation: (c: MapCandidate) => (c.active === false ? 300 : 900),
          getFillColor: (c: MapCandidate) => (c.active === false ? [...C.youSoft, 150] : [...C.you, 255]) as [number, number, number, number], pickable: true,
        }),
    ].filter(Boolean));
  }, [deckReady, props.zones, props.competitors, props.candidates, props.layers, props.depth, props.zoneSpacingKm, props.competitorWeight]);

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
    <div className={props.className} style={{ position: props.fill ? "absolute" : "relative", ...(props.fill ? { inset: 0 } : {}) }} data-testid="map">
      {/* inline style: maplibre's .maplibregl-map sets position:relative, which would override a utility class */}
      <div ref={el} style={{ position: "absolute", inset: 0 }} />
      {!ready && !styleNote && <div className="absolute inset-0 flex items-center justify-center bg-ink-900 text-sm text-ink-400">Loading map…</div>}
      {styleNote && <div className="absolute left-2 top-2 rounded bg-ink-900/90 px-2 py-1 text-xs text-amber-200">{styleNote}</div>}
    </div>
  );
}
