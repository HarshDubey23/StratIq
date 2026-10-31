"use client";

/**
 * Landing-page city: a real 3D street (OpenStreetMap buildings), real competitors fetched live
 * from OpenStreetMap through the StrataIQ API, and synthetic customer trips (clearly labelled
 * as simulated) streaming toward them. The camera follows the scroll chapters.
 */
import maplibregl, { type Map as MLMap } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { attachDeck, C, enhanceMap, pickStyle, type DeckHandle } from "@/lib/mapkit";
import type { PreviewComp, Spot } from "./spots";

export type { Spot, PreviewComp };

const CAMERAS = [
  { zoom: 15.4, pitch: 62, bearing: -28 },
  { zoom: 14.6, pitch: 55, bearing: 18 },
  { zoom: 15.9, pitch: 70, bearing: 52 },
  { zoom: 14.2, pitch: 40, bearing: -10 },
  { zoom: 15.0, pitch: 66, bearing: 120 },
];

function rand(seed: number) {
  let s = seed % 2147483647;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

interface Trip {
  path: [number, number][];
  ts: number[];
  you: boolean;
}

/** Synthetic people (illustrative): homes scattered around the street, each walking to a business. */
function makeTrips(spot: Spot, comps: PreviewComp[], n = 900): Trip[] {
  const r = rand(Math.round(spot.lat * 1e4 + spot.lng * 1e3));
  const dests = [{ lat: spot.lat, lng: spot.lng, you: true }, ...comps.slice(0, 60).map((c) => ({ lat: c.lat, lng: c.lng, you: false }))];
  const out: Trip[] = [];
  const kmLat = 1 / 111.32;
  const kmLng = 1 / (111.32 * Math.cos((spot.lat * Math.PI) / 180));
  for (let i = 0; i < n; i++) {
    const a = r() * Math.PI * 2;
    const d = 0.25 + Math.sqrt(r()) * 1.6;
    const home: [number, number] = [spot.lng + Math.cos(a) * d * kmLng, spot.lat + Math.sin(a) * d * kmLat];
    // nearest-ish destination with some randomness (illustrative choice, not the model)
    let best = dests[0];
    let bs = Infinity;
    for (const dst of dests) {
      const dd = Math.hypot((dst.lng - home[0]) / kmLng, (dst.lat - home[1]) / kmLat) * (0.6 + r() * 0.9) * (dst.you ? 0.85 : 1);
      if (dd < bs) {
        bs = dd;
        best = dst;
      }
    }
    // gentle L-shaped path (streets are rarely straight lines)
    const mid: [number, number] = r() < 0.5 ? [best.lng, home[1]] : [home[0], best.lat];
    const t0 = r() * 1000;
    const dur = 120 + bs * 90;
    out.push({ path: [home, mid, [best.lng, best.lat]], ts: [t0, t0 + dur * 0.5, t0 + dur], you: best.you });
  }
  return out;
}

export default function HeroMap({ spot, comps, chapter, showTrips, framed = false }: { spot: Spot; comps: PreviewComp[]; chapter: number; showTrips: boolean; framed?: boolean }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const deck = useRef<DeckHandle | null>(null);
  const [ready, setReady] = useState(false);
  const state = useRef({ spot, comps, chapter, showTrips, trips: [] as Trip[] });
  state.current.spot = spot;
  state.current.comps = comps;
  state.current.chapter = chapter;
  state.current.showTrips = showTrips;

  useEffect(() => {
    let cancelled = false;
    let raf = 0;
    (async () => {
      const style = await pickStyle();
      if (cancelled || !el.current) return;
      let m: MLMap;
      try {
        m = new maplibregl.Map({
          container: el.current, style, center: [spot.lng, spot.lat], ...CAMERAS[0], interactive: false, attributionControl: { compact: true },
          maxPitch: 80, fadeDuration: 0, pixelRatio: Math.min(window.devicePixelRatio || 1, 1.5),
        });
      } catch {
        return;
      }
      map.current = m;
      m.on("load", async () => {
        enhanceMap(m, { buildingsMinZoom: 12 });
        const d = await attachDeck(m);
        if (cancelled) return;
        deck.current = d;
        setReady(true);
        let last = performance.now();
        const loop = (now: number) => {
          const dt = Math.min(64, now - last);
          last = now;
          // slow orbit
          if (!m.isMoving()) m.setBearing(m.getBearing() + dt * 0.0035);
          const S = state.current;
          const t = (now / 22) % 1400;
          d?.setLayers((DL) => [
            S.showTrips && new DL.TripsLayer({
              id: "trips", data: S.trips, getPath: (x: Trip) => x.path, getTimestamps: (x: Trip) => x.ts,
              getColor: (x: Trip) => (x.you ? C.you : C.agent), widthMinPixels: 2.2, trailLength: 70, currentTime: t, fadeTrail: true, capRounded: true, jointRounded: true,
            }),
            new DL.ColumnLayer({
              id: "comps", data: S.comps, diskResolution: 18, radius: 14, extruded: true,
              getPosition: (c: PreviewComp) => [c.lng, c.lat], getElevation: () => 160, getFillColor: [...C.comp, 240] as [number, number, number, number],
            }),
            new DL.ScatterplotLayer({
              id: "comp-glow", data: S.comps, getPosition: (c: PreviewComp) => [c.lng, c.lat], getRadius: 46, radiusUnits: "meters",
              getFillColor: [...C.comp, 45] as [number, number, number, number], stroked: false,
            }),
            new DL.ScatterplotLayer({
              id: "site-ring", data: [S.spot], getPosition: (s: Spot) => [s.lng, s.lat], radiusUnits: "meters",
              getRadius: 40 + ((now / 12) % 220), getFillColor: [0, 0, 0, 0], getLineColor: [...C.you, Math.max(0, 200 - ((now / 12) % 220))] as [number, number, number, number],
              stroked: true, filled: false, lineWidthMinPixels: 2, updateTriggers: { getRadius: now, getLineColor: now },
            }),
            new DL.ColumnLayer({
              id: "site", data: [S.spot], diskResolution: 36, radius: 22, extruded: true,
              getPosition: (s: Spot) => [s.lng, s.lat], getElevation: 620, getFillColor: [...C.you, 255] as [number, number, number, number],
            }),
          ].filter(Boolean));
          raf = requestAnimationFrame(loop);
        };
        raf = requestAnimationFrame(loop);
      });
    })();
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      deck.current?.destroy();
      map.current?.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // new data → new synthetic trips
  useEffect(() => {
    state.current.trips = makeTrips(spot, comps);
  }, [spot, comps]);

  // camera choreography
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const cam = CAMERAS[chapter % CAMERAS.length];
    m.flyTo({ center: [spot.lng, spot.lat], ...cam, duration: 2600, curve: 1.3, essential: true });
  }, [ready, chapter, spot]);

  return (
    <div className="absolute inset-0" aria-hidden>
      <div ref={el} style={{ position: "absolute", inset: 0 }} />
      {/* vignette so type stays legible over the city (not needed inside a framed window) */}
      {!framed && <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(120%_80%_at_70%_40%,transparent_30%,rgba(245,243,238,.35)_70%,#F5F3EE_100%)]" />}
      {!framed && <div className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-ink-950 via-ink-950/70 to-transparent" />}
    </div>
  );
}
