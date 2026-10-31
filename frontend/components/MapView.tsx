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
  kind: "osm" | "fsq" | "user" | "hypothetical" | "demo" | "field";
  inactive?: boolean;
}

export interface MapCandidate {
  id: string;
  label: string;
  lat: number;
  lng: number;
  active?: boolean;
}

/** A scored candidate site from the location finder: score 0-1 (relative profit), rank 1..5 for the shortlist. */
export interface MapOpportunity {
  lat: number;
  lng: number;
  score: number;
  rank?: number;
  label?: string;
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
  opportunity?: MapOpportunity[] | null;
  /** Fly the camera to this point whenever `key` changes. */
  focus?: { lat: number; lng: number; key: string } | null;
  onOpportunityClick?: (o: MapOpportunity) => void;
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
  const introDone = useRef(false);

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
        // start high and flat; the first fit below is a slow descent into the catchment
        zoom: (props.zoom ?? 13.2) - 1.8,
        pitch: 0,
        bearing: -60,
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
        m.addLayer({ id: "siq-catchment-fill", type: "fill", source: "siq-catchment", paint: { "fill-color": "#2F49FF", "fill-opacity": 0.035 } });
        m.addLayer({ id: "siq-catchment-line", type: "line", source: "siq-catchment", paint: { "line-color": "#2F49FF", "line-width": 1.5, "line-dasharray": [2, 2], "line-opacity": 0.8 } });
        m.addLayer({
          id: "siq-zones",
          type: "circle",
          source: "siq-zones",
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 4, 14, 14, 16, 34],
            "circle-color": ["interpolate", ["linear"], ["get", "v"], 0, "#dfe4ff", 0.25, "#b9c3ff", 0.5, "#8a9bff", 0.75, "#5a72ff", 1, "#2f49ff"],
            "circle-opacity": 0.5,
            "circle-blur": 0.6,
          },
        });
        m.addLayer({
          id: "siq-activity",
          type: "circle",
          source: "siq-activity",
          paint: { "circle-radius": 3, "circle-color": "#a9a59b", "circle-opacity": 0.8, "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 1 },
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
            "circle-stroke-color": ["case", ["boolean", ["get", "hyp"], false], "#ffffff", "#FFFFFF"],
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
            const tag = k === "osm" ? "Observed (OpenStreetMap)" : k === "fsq" ? "Observed (Foursquare Places)" : k === "user" ? "User-entered" : k === "hypothetical" ? "Hypothetical" : "Demo";
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
    const color = (choice: number) => (mode === "red" ? "#E5484D" : choice === 0 ? "#2F49FF" : choice < 0 ? "#A9A59B" : "#E5484D");
    (m.getSource("siq-agents") as GeoJSONSource).setData(fc((props.agents || []).map(([lat, lng, seg, ch]) => pt(lng, lat, { c: color(ch), s: seg, ch }))));
  }, [ready, props.agents, props.agentColor]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !props.agents?.length) return;
    m.setPaintProperty("siq-agents", "circle-opacity-transition", { duration: 0, delay: 0 });
    m.setPaintProperty("siq-agents", "circle-opacity", 0);
    const id = setTimeout(() => {
      m.setPaintProperty("siq-agents", "circle-opacity-transition", { duration: 1600, delay: 0 });
      m.setPaintProperty("siq-agents", "circle-opacity", 0.85);
    }, 60);
    return () => clearTimeout(id);
  }, [ready, props.agents]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const col = { osm: "#F59E0B", fsq: "#F59E0B", user: "#7C3AED", hypothetical: "#7C3AED", demo: "#D97706", field: "#65A30D" };
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
      d.style.cssText = `display:flex;align-items:center;gap:6px;padding:3px 8px 3px 4px;border-radius:999px;font:600 11px var(--font-inter-tight),sans-serif;cursor:pointer;
        background:${c.active ? "#2F49FF" : "#FFFFFF"};color:${c.active ? "#F5F3EE" : "#131312"};border:1px solid ${c.active ? "#8A9BFF" : "#D8D4CA"};box-shadow:0 6px 16px -6px rgba(20,18,10,.35)`;
      const dot = document.createElement("span");
      dot.style.cssText = `width:10px;height:10px;border-radius:999px;background:${c.active ? "#F5F3EE" : "#2F49FF"}`;
      const t = document.createElement("span");
      t.textContent = c.label;
      if (c.active) {
        dot.style.position = "relative";
        const ring = document.createElement("span");
        ring.style.cssText = "position:absolute;inset:-4px;border-radius:999px;border:2px solid #F5F3EE;animation:ping-soft 1.8s cubic-bezier(.16,1,.3,1) infinite";
        dot.append(ring);
      }
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
          getPosition: (z: MapZone) => [z.lng, z.lat], getElevation: (z: MapZone) => 6 + (z.value / max) * 240,
          getFillColor: (z: MapZone) => popColor(z.value / max, 85), pickable: true, material: { ambient: 0.5, diffuse: 0.6, shininess: 20 },
          transitions: { getElevation: { duration: 1400, easing: easeOut, enter: () => [0] } },
          updateTriggers: { getElevation: [max], getFillColor: [max] },
        }),
      depth && L.competitors !== false &&
        new DL.ColumnLayer({
          id: "comp-pillars", data: comps.map((c) => ({ ...c, tip: `${c.name || "Unnamed"} — ${c.kind === "osm" ? "observed in OpenStreetMap" : c.kind === "fsq" ? "observed in Foursquare Places" : c.kind === "user" ? "entered by you" : c.kind === "field" ? "verified on the ground by a field researcher" : c.kind}${w[c.id] ? `\nmodeled ${Math.round(w[c.id])} customers/mo` : ""}` })),
          diskResolution: 24, radius: 24, extruded: true,
          getPosition: (c: MapCompetitor) => [c.lng, c.lat], getElevation: (c: MapCompetitor) => 120 + ((w[c.id] || 0) / wmax) * 520,
          getFillColor: (c: MapCompetitor) => (c.kind === "osm" || c.kind === "fsq" ? [...C.comp, 235] : c.kind === "field" ? [...C.field, 235] : [...C.user, 235]) as [number, number, number, number],
          pickable: true, onClick: (info: { object?: MapCompetitor }) => { if (info.object) handlers.current.onCompetitorClick?.(info.object.id); },
          transitions: { getElevation: { duration: 1400, easing: easeOut, enter: () => [0] } }, updateTriggers: { getElevation: [wmax, Object.keys(w).length] },
        }),
      depth && L.competitors !== false &&
        new DL.ScatterplotLayer({
          id: "comp-glow", data: comps, getPosition: (c: MapCompetitor) => [c.lng, c.lat], getRadius: 70, radiusUnits: "meters",
          getFillColor: (c: MapCompetitor) => (c.kind === "osm" || c.kind === "fsq" ? [...C.comp, 55] : c.kind === "field" ? [...C.field, 55] : [...C.user, 55]) as [number, number, number, number], stroked: false,
        }),
      depth && L.competitors !== false &&
        new DL.TextLayer({
          id: "comp-labels",
          data: [...comps].filter((c) => c.name && !/^unnamed/i.test(c.name)).sort((a, b) => (w[b.id] || 0) - (w[a.id] || 0)).slice(0, 30),
          getPosition: (c: MapCompetitor) => [c.lng, c.lat, 120 + ((w[c.id] || 0) / wmax) * 520 + 30],
          getText: (c: MapCompetitor) => (c.name.length > 26 ? `${c.name.slice(0, 25)}…` : c.name),
          getSize: 12, sizeUnits: "pixels", getColor: [19, 19, 18, 240], getTextAnchor: "middle", getAlignmentBaseline: "bottom",
          background: true, getBackgroundColor: [255, 255, 255, 235], getBorderColor: [0, 0, 0, 30], getBorderWidth: 1, backgroundPadding: [6, 3], fontFamily: "Inter Tight, system-ui, sans-serif",
          characterSet: "auto", updateTriggers: { getPosition: [wmax, Object.keys(w).length] },
        }),
      (props.opportunity || []).length > 0 &&
        new DL.ScatterplotLayer({
          id: "opp-heat", data: props.opportunity || [], getPosition: (o: MapOpportunity) => [o.lng, o.lat, 4], radiusUnits: "meters",
          getRadius: (o: MapOpportunity) => 60 + 90 * o.score, stroked: false, pickable: true,
          getFillColor: (o: MapOpportunity) => [Math.round(30 + 40 * o.score), Math.round(90 + 134 * o.score), Math.round(120 + 48 * o.score), Math.round(40 + 150 * o.score)] as [number, number, number, number],
          onClick: (info: { object?: MapOpportunity }) => { if (info.object) handlers.current.onOpportunityClick?.(info.object); },
          updateTriggers: { getFillColor: [(props.opportunity || []).length], getRadius: [(props.opportunity || []).length] },
        }),
      (props.opportunity || []).some((o) => o.rank) &&
        new DL.ColumnLayer({
          id: "opp-top", data: (props.opportunity || []).filter((o) => o.rank), diskResolution: 6, radius: 55, extruded: true, angle: 30,
          getPosition: (o: MapOpportunity) => [o.lng, o.lat], getElevation: (o: MapOpportunity) => 900 - 110 * ((o.rank || 1) - 1),
          getFillColor: [69, 224, 168, 225], pickable: true,
          onClick: (info: { object?: MapOpportunity }) => { if (info.object) handlers.current.onOpportunityClick?.(info.object); },
        }),
      (props.opportunity || []).some((o) => o.rank) &&
        new DL.TextLayer({
          id: "opp-labels", data: (props.opportunity || []).filter((o) => o.rank),
          getPosition: (o: MapOpportunity) => [o.lng, o.lat, 900 - 110 * ((o.rank || 1) - 1) + 40],
          getText: (o: MapOpportunity) => o.label || `#${o.rank}`, getSize: 13, sizeUnits: "pixels", getColor: [4, 6, 11, 255],
          getTextAnchor: "middle", getAlignmentBaseline: "bottom", background: true, getBackgroundColor: [69, 224, 168, 235],
          backgroundPadding: [6, 3], fontFamily: "Inter Tight, system-ui, sans-serif", fontWeight: 600, characterSet: "auto",
        }),
      depth && (props.candidates || []).length > 0 &&
        new DL.ColumnLayer({
          id: "site-beacon", data: (props.candidates || []).map((c) => ({ ...c, tip: `${c.label} — your candidate site` })), diskResolution: 32, radius: 24, extruded: true,
          getPosition: (c: MapCandidate) => [c.lng, c.lat], getElevation: (c: MapCandidate) => (c.active === false ? 300 : 900),
          getFillColor: (c: MapCandidate) => (c.active === false ? [...C.youSoft, 150] : [...C.you, 255]) as [number, number, number, number], pickable: true,
          transitions: { getElevation: { duration: 1600, easing: easeOut, enter: () => [0] } },
        }),
    ].filter(Boolean));
  }, [deckReady, props.zones, props.competitors, props.candidates, props.layers, props.depth, props.zoneSpacingKm, props.competitorWeight, props.opportunity]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !props.focus) return;
    m.flyTo({ center: [props.focus.lng, props.focus.lat], zoom: 15.2, pitch: 58, duration: 1400, essential: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, props.focus?.key]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    m.getCanvas().style.cursor = props.crosshair ? "crosshair" : "";
  }, [ready, props.crosshair]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const intro = !introDone.current;
    introDone.current = true;
    const ring = props.catchment?.coordinates?.[0];
    if (ring && ring.length) {
      const b = new maplibregl.LngLatBounds(ring[0] as [number, number], ring[0] as [number, number]);
      ring.forEach((c) => b.extend(c as [number, number]));
      m.fitBounds(b, { padding: 40, duration: intro ? 2600 : 900, pitch: props.pitch ?? 45, bearing: intro ? -18 : m.getBearing() });
    } else {
      m.flyTo({ center: props.center, zoom: props.zoom ?? 13.2, duration: intro ? 2600 : 800, ...(intro ? { pitch: props.pitch ?? 55, bearing: -18 } : {}) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, props.fitKey]);

  return (
    <div className={props.className} style={{ position: props.fill ? "absolute" : "relative", ...(props.fill ? { inset: 0 } : {}) }} data-testid="map">
      {/* inline style: maplibre's .maplibregl-map sets position:relative, which would override a utility class */}
      <div ref={el} style={{ position: "absolute", inset: 0 }} />
      {!ready && !styleNote && <div className="absolute inset-0 flex items-center justify-center bg-ink-900 text-sm text-ink-400">Loading map…</div>}
      {styleNote && <div className="absolute left-2 top-2 rounded bg-ink-900/90 px-2 py-1 text-xs text-amber-800">{styleNote}</div>}
    </div>
  );
}

function easeOut(t: number) {
  return 1 - Math.pow(1 - t, 4);
}
