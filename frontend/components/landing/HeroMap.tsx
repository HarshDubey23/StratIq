"use client";

/**
 * Landing-page city: a real 3D street (OpenStreetMap buildings), real competitors fetched live
 * from OpenStreetMap through the StrataIQ API, and an ILLUSTRATIVE crowd of people who walk to
 * a shop. The scroll story drives `scene`:
 *   0 hero (everything)  1 the street  2 rivals rise  3 people appear  4 each one chooses  5 the answer
 * The crowd here is a drawing, not the model: the real run uses the choice model inside the app.
 */
import maplibregl, { type Map as MLMap } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { attachDeck, C, enhanceMap, pickStyle, type DeckHandle } from "@/lib/mapkit";
import type { PreviewComp, Spot } from "./spots";

export type { Spot, PreviewComp };

const CAMERAS = [
  { zoom: 15.25, pitch: 62, bearing: -28 },
  { zoom: 15.7, pitch: 12, bearing: 0 },
  { zoom: 15.4, pitch: 68, bearing: 42 },
  { zoom: 14.35, pitch: 52, bearing: -18 },
  { zoom: 15.0, pitch: 62, bearing: 96 },
  { zoom: 14.1, pitch: 46, bearing: 168 },
];

function rand(seed: number) {
  let s = Math.abs(Math.round(seed)) % 2147483647 || 7;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

type Choice = "you" | "rival" | "none";
export interface Person {
  home: [number, number];
  choice: Choice;
  path: [number, number][];
  ts: number[];
}
interface Bin {
  pos: [number, number];
  n: number;
}

/** Illustrative crowd: homes around the street; each walks to the nearest-ish shop, or stays home if everything is far. */
export function makePeople(spot: Spot, comps: PreviewComp[], n = 1400): Person[] {
  const r = rand(spot.lat * 1e4 + spot.lng * 1e3 + comps.length);
  const dests = [{ lat: spot.lat, lng: spot.lng, you: true }, ...comps.slice(0, 60).map((c) => ({ lat: c.lat, lng: c.lng, you: false }))];
  const kmLat = 1 / 111.32;
  const kmLng = 1 / (111.32 * Math.cos((spot.lat * Math.PI) / 180));
  const out: Person[] = [];
  for (let i = 0; i < n; i++) {
    // denser near the centre, like a real high street
    const a = r() * Math.PI * 2;
    const d = 0.12 + Math.pow(r(), 0.7) * 1.7;
    const home: [number, number] = [spot.lng + Math.cos(a) * d * kmLng, spot.lat + Math.sin(a) * d * kmLat];
    let best = dests[0];
    let bs = Infinity;
    for (const dst of dests) {
      const dd = Math.hypot((dst.lng - home[0]) / kmLng, (dst.lat - home[1]) / kmLat) * (0.6 + r() * 0.9) * (dst.you ? 0.85 : 1);
      if (dd < bs) {
        bs = dd;
        best = dst;
      }
    }
    const none = bs > 1.1 + r() * 0.6;
    const mid: [number, number] = r() < 0.5 ? [best.lng, home[1]] : [home[0], best.lat];
    const t0 = r() * 1000;
    const dur = 120 + bs * 90;
    out.push({
      home,
      choice: none ? "none" : best.you ? "you" : "rival",
      path: none ? [] : [home, mid, [best.lng, best.lat]],
      ts: none ? [] : [t0, t0 + dur * 0.5, t0 + dur],
    });
  }
  return out;
}

function binPeople(people: Person[], spot: Spot, cellKm = 0.22): Bin[] {
  const kmLat = 1 / 111.32;
  const kmLng = 1 / (111.32 * Math.cos((spot.lat * Math.PI) / 180));
  const m = new Map<string, Bin>();
  for (const p of people) {
    const gx = Math.round((p.home[0] - spot.lng) / (cellKm * kmLng));
    const gy = Math.round((p.home[1] - spot.lat) / (cellKm * kmLat));
    const k = `${gx}:${gy}`;
    const b = m.get(k);
    if (b) b.n++;
    else m.set(k, { pos: [spot.lng + gx * cellKm * kmLng, spot.lat + gy * cellKm * kmLat], n: 1 });
  }
  return [...m.values()];
}

const GREY: [number, number, number] = [169, 165, 155];
const rgba = (c: [number, number, number], a: number) => [c[0], c[1], c[2], a] as [number, number, number, number];

export default function HeroMap({
  spot, comps, scene = 0, framed = false, onPeople,
}: { spot: Spot; comps: PreviewComp[]; scene?: number; framed?: boolean; onPeople?: (p: Person[]) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const deck = useRef<DeckHandle | null>(null);
  const [ready, setReady] = useState(false);
  const state = useRef({ spot, comps, scene, people: [] as Person[], bins: [] as Bin[], walkers: [] as Person[], born: 0 });
  state.current.spot = spot;
  state.current.comps = comps;
  state.current.scene = scene;

  useEffect(() => {
    let cancelled = false;
    let raf = 0;
    (async () => {
      const style = await pickStyle();
      if (cancelled || !el.current) return;
      let m: MLMap;
      try {
        // start high and flat; the first flyTo is the "descent into the street"
        m = new maplibregl.Map({
          container: el.current, style, center: [spot.lng, spot.lat], zoom: 12.2, pitch: 0, bearing: -70, interactive: false,
          attributionControl: { compact: true }, maxPitch: 80, fadeDuration: 0, pixelRatio: Math.min(window.devicePixelRatio || 1, 1.5),
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
          if (!m.isMoving()) m.setBearing(m.getBearing() + dt * 0.003);
          const S = state.current;
          const sc = S.scene;
          const all = sc === 0;
          const showComps = all || sc >= 2;
          const showPeople = all || sc >= 3;
          const choose = all || sc >= 4;
          const showTrips = all || sc === 4 || sc === 5;
          const t = (now / 22) % 1400;
          const pulse = (now / 12) % 260;
          const pc = (p: Person) => (!choose ? rgba(C.agent, 220) : p.choice === "you" ? rgba(C.you, 240) : p.choice === "rival" ? rgba(C.agent, 200) : rgba(GREY, 150));
          const binMax = Math.max(1, ...S.bins.map((b) => b.n));
          d?.setLayers((DL) => [
            new DL.ScatterplotLayer({
              id: "catchment", data: [S.spot], getPosition: (s: Spot) => [s.lng, s.lat], radiusUnits: "meters",
              getRadius: sc === 1 || sc === 5 ? 1500 : 0, getFillColor: rgba(C.you, 14), getLineColor: rgba(C.you, 150),
              stroked: true, lineWidthMinPixels: 1.5, transitions: { getRadius: { duration: 1400, easing: easeOut } }, updateTriggers: { getRadius: sc },
            }),
            new DL.ColumnLayer({
              id: "density", data: S.bins, diskResolution: 6, angle: 30, radius: 105, coverage: 0.9, extruded: true,
              getPosition: (b: Bin) => b.pos, getElevation: (b: Bin) => (sc === 3 ? 20 + (b.n / binMax) * 520 : 0),
              getFillColor: (b: Bin) => rgba(mix(C.youSoft, C.agent, b.n / binMax), 120),
              transitions: { getElevation: { duration: 1300, easing: easeOut } }, updateTriggers: { getElevation: [sc, binMax] },
              material: { ambient: 0.55, diffuse: 0.55, shininess: 12 },
            }),
            showTrips && new DL.TripsLayer({
              id: "trips", data: S.walkers, getPath: (x: Person) => x.path, getTimestamps: (x: Person) => x.ts,
              getColor: (x: Person) => (x.choice === "you" ? C.you : C.agent), widthMinPixels: 2.2, trailLength: 80, currentTime: t,
              fadeTrail: true, capRounded: true, jointRounded: true, opacity: sc === 5 ? 0.45 : 0.9,
            }),
            new DL.ScatterplotLayer({
              id: "people", data: S.people, getPosition: (p: Person) => p.home, radiusUnits: "meters", radiusMinPixels: 0,
              getRadius: showPeople ? 9 : 0, getFillColor: pc, stroked: false,
              transitions: { getRadius: { duration: 900, easing: easeOut }, getFillColor: { duration: 900 } },
              updateTriggers: { getRadius: showPeople, getFillColor: choose },
            }),
            new DL.ScatterplotLayer({
              id: "comp-glow", data: S.comps, getPosition: (c: PreviewComp) => [c.lng, c.lat], radiusUnits: "meters",
              getRadius: showComps ? 48 : 0, getFillColor: rgba(C.comp, 50), stroked: false,
              transitions: { getRadius: { duration: 900 } }, updateTriggers: { getRadius: showComps },
            }),
            new DL.ColumnLayer({
              id: "comps", data: S.comps, diskResolution: 18, radius: 14, extruded: true,
              getPosition: (c: PreviewComp) => [c.lng, c.lat], getElevation: showComps ? 170 : 0, getFillColor: rgba(C.comp, 240),
              // each pillar rises when a new street loads, and again when the "rivals" chapter enters
              transitions: { getElevation: { duration: 1400, easing: easeOut, enter: () => [0] } }, updateTriggers: { getElevation: showComps },
              material: { ambient: 0.6, diffuse: 0.6, shininess: 40 },
            }),
            new DL.ScatterplotLayer({
              id: "site-ring", data: [S.spot], getPosition: (s: Spot) => [s.lng, s.lat], radiusUnits: "meters",
              getRadius: 40 + pulse, getFillColor: [0, 0, 0, 0], getLineColor: rgba(C.you, Math.max(0, 210 - pulse * 0.8)),
              stroked: true, filled: false, lineWidthMinPixels: 2, updateTriggers: { getRadius: now, getLineColor: now },
            }),
            new DL.ColumnLayer({
              id: "site", data: [S.spot], diskResolution: 36, radius: 22, extruded: true,
              getPosition: (s: Spot) => [s.lng, s.lat], getElevation: sc === 5 ? 1100 : 640, getFillColor: rgba(C.you, 255),
              transitions: { getElevation: { duration: 1400, easing: easeOut, enter: () => [0] } }, updateTriggers: { getElevation: sc === 5 },
              material: { ambient: 0.65, diffuse: 0.5, shininess: 60 },
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

  // new street → new illustrative crowd
  useEffect(() => {
    const people = makePeople(spot, comps);
    state.current.people = people;
    state.current.walkers = people.filter((p) => p.choice !== "none");
    state.current.bins = binPeople(people, spot);
    onPeople?.(people);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spot, comps]);

  // camera choreography: one shot per scene; the first one is a slow descent from above
  const first = useRef(true);
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const cam = CAMERAS[scene % CAMERAS.length];
    const intro = first.current;
    first.current = false;
    m.flyTo({ center: [spot.lng, spot.lat], ...cam, duration: intro ? 4200 : 2400, curve: intro ? 1.1 : 1.35, essential: true });
  }, [ready, scene, spot]);

  return (
    <div className="absolute inset-0" aria-hidden>
      <div ref={el} style={{ position: "absolute", inset: 0 }} />
      {!framed && <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-ink-950/80 to-transparent" />}
    </div>
  );
}

function easeOut(t: number) {
  return 1 - Math.pow(1 - t, 4);
}
function mix(a: [number, number, number], b: [number, number, number], t: number): [number, number, number] {
  const k = Math.max(0, Math.min(1, t));
  return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];
}
