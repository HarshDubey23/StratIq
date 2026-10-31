"use client";

/**
 * Map kit: the "night cartography" look shared by every map, plus a lazily
 * loaded deck.gl overlay for real 3D data layers (competitor pillars,
 * population columns, demand arcs). deck.gl is imported on demand so it never
 * runs during server rendering and only ships to pages that draw a map.
 */
import type { IControl, Map as MLMap } from "maplibre-gl";

export const STYLE_DARK = "https://tiles.openfreemap.org/styles/positron"; // light base, recoloured in enhanceMap
export const STYLE_FALLBACK = "https://tiles.openfreemap.org/styles/liberty";

export const C = {
  ground: "#eef0f4",
  water: "#d2ddef",
  park: "#e2ebdf",
  road: "#ffffff",
  roadMajor: "#ffffff",
  label: "#6b7180",
  you: [47, 73, 255] as [number, number, number],
  youSoft: [138, 155, 255] as [number, number, number],
  comp: [245, 158, 11] as [number, number, number],
  agent: [229, 72, 77] as [number, number, number],
  user: [124, 58, 237] as [number, number, number],
  field: [101, 163, 13] as [number, number, number],
};

export async function pickStyle(): Promise<string> {
  try {
    const r = await fetch(STYLE_DARK);
    if (r.ok) return STYLE_DARK;
  } catch {
    /* offline */
  }
  return STYLE_FALLBACK;
}

function safe(fn: () => void) {
  try {
    fn();
  } catch {
    /* layer/property absent in this style */
  }
}

/** Survey-blueprint palette for the landing city: one blue field, white line work. */
export const BP = { field: "#2F49FF", water: "#2236D6", park: "#3A55FF", line: "#FFFFFF" };

/** Landing look: the street as a blueprint. Fills vanish into the blue, roads become white lines,
 *  buildings become glassy pale-blue blocks with white footprints, labels go. */
function blueprint(m: MLMap, layers: { id: string; type: string }[], minzoom: number) {
  for (const l of layers) {
    const id = l.id.toLowerCase();
    if (l.type === "background") safe(() => m.setPaintProperty(l.id, "background-color", BP.field));
    else if (l.type === "fill") {
      if (id.includes("water")) safe(() => m.setPaintProperty(l.id, "fill-color", BP.water));
      else if (id.includes("park") || id.includes("wood") || id.includes("grass")) safe(() => m.setPaintProperty(l.id, "fill-color", BP.park));
      else safe(() => m.setLayoutProperty(l.id, "visibility", "none"));
    } else if (l.type === "line") {
      if (/road|highway|street|tunnel|bridge|path|rail/.test(id)) {
        const major = /motorway|trunk|primary|major/.test(id);
        safe(() => m.setPaintProperty(l.id, "line-color", BP.line));
        safe(() => m.setPaintProperty(l.id, "line-opacity", major ? 0.5 : 0.18));
      } else if (!id.includes("water")) safe(() => m.setLayoutProperty(l.id, "visibility", "none"));
    } else if (l.type === "symbol") safe(() => m.setLayoutProperty(l.id, "visibility", "none"));
  }
  if (!m.getSource("openmaptiles")) return;
  safe(() =>
    m.addLayer({
      id: "siq-bp-footprints", source: "openmaptiles", "source-layer": "building", type: "line", minzoom,
      paint: { "line-color": BP.line, "line-width": 0.6, "line-opacity": 0.45 },
    }),
  );
  safe(() =>
    m.addLayer({
      id: "siq-3d-buildings", source: "openmaptiles", "source-layer": "building", type: "fill-extrusion", minzoom,
      paint: {
        "fill-extrusion-color": ["interpolate", ["linear"], ["coalesce", ["get", "render_height"], 6], 0, "#5068ff", 20, "#7b8dff", 60, "#a9b5ff", 160, "#e4e8ff"],
        "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], minzoom, 0, minzoom + 1.5, ["coalesce", ["get", "render_height"], 6]],
        "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
        "fill-extrusion-opacity": 0.72,
        "fill-extrusion-vertical-gradient": true,
      },
    }),
  );
  safe(() => m.setLight({ anchor: "map", color: "#ffffff", intensity: 0.42, position: [1.3, 210, 40] }));
  const anyMap = m as unknown as { setSky?: (s: Record<string, unknown>) => void };
  safe(() =>
    anyMap.setSky?.({
      "sky-color": BP.field, "horizon-color": "#8f9fff", "fog-color": BP.field,
      "sky-horizon-blend": 0.5, "horizon-fog-blend": 0.6, "fog-ground-blend": 0.25, "atmosphere-blend": 0.4,
    }),
  );
}

/** Recolour the base style, extrude real OSM building footprints and add lighting + atmosphere. */
export function enhanceMap(m: MLMap, opts: { buildingsMinZoom?: number; buildingOpacity?: number; theme?: "light" | "blueprint" } = {}) {
  const style = m.getStyle();
  const layers = style.layers || [];
  if (opts.theme === "blueprint") return blueprint(m, layers, opts.buildingsMinZoom ?? 12.5);
  for (const l of layers) {
    const id = l.id.toLowerCase();
    if (l.type === "background") safe(() => m.setPaintProperty(l.id, "background-color", C.ground));
    else if (l.type === "fill" && id.includes("water")) safe(() => m.setPaintProperty(l.id, "fill-color", C.water));
    else if (l.type === "fill" && (id.includes("park") || id.includes("landcover") || id.includes("wood") || id.includes("grass")))
      safe(() => m.setPaintProperty(l.id, "fill-color", C.park));
    else if (l.type === "fill" && id.includes("building")) safe(() => m.setLayoutProperty(l.id, "visibility", "none"));
    else if (l.type === "line" && (id.includes("road") || id.includes("highway") || id.includes("street") || id.includes("tunnel") || id.includes("bridge"))) {
      const major = /motorway|trunk|primary|major/.test(id);
      safe(() => m.setPaintProperty(l.id, "line-color", major ? C.roadMajor : C.road));
    } else if (l.type === "symbol") {
      safe(() => m.setPaintProperty(l.id, "text-color", C.label));
      safe(() => m.setPaintProperty(l.id, "text-halo-color", C.ground));
      safe(() => m.setPaintProperty(l.id, "text-halo-width", 1.4));
    }
  }
  const firstSymbol = layers.find((l) => l.type === "symbol")?.id;
  if (m.getSource("openmaptiles") && !m.getLayer("siq-3d-buildings")) {
    safe(() =>
      m.addLayer(
        {
          id: "siq-3d-buildings",
          source: "openmaptiles",
          "source-layer": "building",
          type: "fill-extrusion",
          minzoom: opts.buildingsMinZoom ?? 12.5,
          paint: {
            "fill-extrusion-color": [
              "interpolate", ["linear"], ["coalesce", ["get", "render_height"], 6],
              0, "#f8f9fb", 12, "#eef0f4", 30, "#e3e6ec", 80, "#d5d9e1", 200, "#c4c9d3",
            ],
            "fill-extrusion-height": ["interpolate", ["linear"], ["zoom"], 12.5, 0, 14, ["coalesce", ["get", "render_height"], 6]],
            "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
            "fill-extrusion-opacity": opts.buildingOpacity ?? 0.92,
            "fill-extrusion-vertical-gradient": true,
          },
        },
        firstSymbol,
      ),
    );
  }
  // low sun from the side gives the white blocks readable faces
  safe(() => m.setLight({ anchor: "map", color: "#ffffff", intensity: 0.5, position: [1.3, 210, 40] }));
  const anyMap = m as unknown as { setSky?: (s: Record<string, unknown>) => void };
  safe(() =>
    anyMap.setSky?.({
      "sky-color": "#dfe6f6",
      "horizon-color": "#eef1f7",
      "fog-color": "#F3F4F7",
      "sky-horizon-blend": 0.6,
      "horizon-fog-blend": 0.7,
      "fog-ground-blend": 0.35,
      "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 12, 0.6, 16, 0.3],
    }),
  );
}

// ---------------------------------------------------------------- deck.gl overlay
type DeckMods = {
  MapboxOverlay: typeof import("@deck.gl/mapbox").MapboxOverlay;
  layers: typeof import("@deck.gl/layers") & { TripsLayer: typeof import("@deck.gl/geo-layers").TripsLayer };
};
let deckMods: Promise<DeckMods> | null = null;
export function loadDeck(): Promise<DeckMods> {
  if (!deckMods) {
    deckMods = Promise.all([import("@deck.gl/mapbox"), import("@deck.gl/layers"), import("@deck.gl/geo-layers")]).then(([mb, layers, geo]) => ({
      MapboxOverlay: mb.MapboxOverlay,
      layers: { ...layers, TripsLayer: geo.TripsLayer },
    }));
  }
  return deckMods;
}

export interface DeckHandle {
  setLayers: (fn: (L: DeckMods["layers"]) => unknown[]) => void;
  setTooltip: (fn: ((info: { object?: unknown }) => string | null) | null) => void;
  destroy: () => void;
}

/** Attach a deck.gl overlay (interleaved, so pillars and buildings occlude each other correctly). */
export async function attachDeck(m: MLMap): Promise<DeckHandle | null> {
  try {
    const mods = await loadDeck();
    let tip: ((info: { object?: unknown }) => string | null) | null = null;
    const overlay = new mods.MapboxOverlay({
      interleaved: true,
      layers: [],
      getTooltip: (info: { object?: unknown }) => {
        const t = tip?.(info);
        return t ? { text: t, style: { background: "rgba(255,255,255,.97)", color: "#131312", border: "1px solid rgba(0,0,0,.08)", borderRadius: "8px", fontSize: "12px", padding: "6px 9px", fontFamily: "var(--font-inter-tight), sans-serif" } } : null;
      },
    } as ConstructorParameters<DeckMods["MapboxOverlay"]>[0]);
    m.addControl(overlay as unknown as IControl);
    return {
      setLayers: (fn) => overlay.setProps({ layers: fn(mods.layers) as never }),
      setTooltip: (fn) => {
        tip = fn;
      },
      destroy: () => {
        try {
          m.removeControl(overlay as unknown as IControl);
        } catch {
          /* already gone */
        }
      },
    };
  } catch (e) {
    console.warn("deck.gl overlay unavailable", e);
    return null;
  }
}

/** colour ramp for population columns: pale cobalt → cobalt → red */
export function popColor(t: number, alpha = 150): [number, number, number, number] {
  const s = Math.max(0, Math.min(1, t));
  const stops: [number, [number, number, number]][] = [
    [0, [214, 220, 255]],
    [0.45, [120, 140, 255]],
    [0.75, [47, 73, 255]],
    [1, [229, 72, 77]],
  ];
  for (let i = 1; i < stops.length; i++) {
    if (s <= stops[i][0]) {
      const [a0, c0] = stops[i - 1];
      const [a1, c1] = stops[i];
      const k = (s - a0) / (a1 - a0);
      return [c0[0] + (c1[0] - c0[0]) * k, c0[1] + (c1[1] - c0[1]) * k, c0[2] + (c1[2] - c0[2]) * k, alpha];
    }
  }
  return [229, 72, 77, alpha];
}

export function metersPerZoneRadius(spacingKm: number | undefined | null): number {
  return Math.max(60, (spacingKm || 0.3) * 1000 * 0.48);
}
