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
  ground: "#efede6",
  water: "#cfdcea",
  park: "#e1e8d6",
  road: "#ffffff",
  roadMajor: "#fbfaf6",
  label: "#7a766d",
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

/** Recolour the base style, extrude real OSM building footprints and add lighting + atmosphere. */
export function enhanceMap(m: MLMap, opts: { buildingsMinZoom?: number; buildingOpacity?: number } = {}) {
  const style = m.getStyle();
  const layers = style.layers || [];
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
              0, "#f7f5f0", 12, "#efece5", 30, "#e6e2d9", 80, "#dad5ca", 200, "#cbc5b8",
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
  safe(() => m.setLight({ anchor: "viewport", color: "#ffffff", intensity: 0.32, position: [1.4, 200, 35] }));
  const anyMap = m as unknown as { setSky?: (s: Record<string, unknown>) => void };
  safe(() =>
    anyMap.setSky?.({
      "sky-color": "#0b0d18",
      "horizon-color": "#1a2050",
      "fog-color": "#F5F3EE",
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
