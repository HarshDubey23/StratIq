"use client";

/**
 * Landing-page city, drawn as a survey blueprint: real OpenStreetMap buildings and roads, real
 * competitors fetched live through the StrataIQ API, and an ILLUSTRATIVE crowd that walks to a shop.
 *
 * The camera is scrubbed by scroll: `progress` (0..5, a ref so scrolling never re-renders React) is
 * interpolated between one camera per chapter. `scene` (the nearest whole chapter) switches layers:
 *   0 hero  1 the street  2 rivals rise  3 people appear  4 each one chooses  5 the answer
 * The crowd is a drawing, not the model: the real run uses the choice model inside the app.
 */
import maplibregl, { type Map as MLMap } from "maplibre-gl";
import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { attachDeck, enhanceMap, pickStyle, type DeckHandle } from "@/lib/mapkit";
import type { PreviewComp, Spot } from "./spots";

export type { Spot, PreviewComp };

type Cam = { zoom: number; pitch: number; bearing: number };
const CAMERAS: Cam[] = [
  { zoom: 15.1, pitch: 64, bearing: -30 },
  { zoom: 15.8, pitch: 8, bearing: 0 },
  { zoom: 15.5, pitch: 70, bearing: 50 },
  { zoom: 14.3, pitch: 55, bearing: 10 },
  { zoom: 15.1, pitch: 66, bearing: 110 },
  { zoom: 14.0, pitch: 48, bearing: 190 },
];

const WHITE: [number, number, number] = [255, 255, 255];
const INK: [number, number, number] = [0, 0, 0];
const RED: [number, number, number] = [255, 75, 62];
const HAZE: [number, number, number] = [170, 184, 255];
const rgba = (c: [number, number, number], a: number) => [c[0], c[1], c[2], a] as [number, number, number, number];

function rand(seed: number) {
  let s = Math.abs(Math.round(seed)) % 2147483647 || 7;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

interface Person {
  home: [number, number];
  choice: "you" | "rival" | "none";
  path: [number, number][];
  ts: number[];
}
interface Bin {
  pos: [number, number];
  n: number;
}

/** Illustrative crowd: homes around the street; some aren't buying today, the rest walk to the nearest-ish shop. */
function makePeople(spot: Spot, comps: PreviewComp[], n = 1400): Person[] {
  const r = rand(spot.lat * 1e4 + spot.lng * 1e3 + comps.length);
  const dests = [{ lat: spot.lat, lng: spot.lng, you: true }, ...comps.slice(0, 60).map((c) => ({ lat: c.lat, lng: c.lng, you: false }))];
  const kmLat = 1 / 111.32;
  const kmLng = 1 / (111.32 * Math.cos((spot.lat * Math.PI) / 180));
  const out: Person[] = [];
  for (let i = 0; i < n; i++) {
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
    const none = r() < 0.35 || bs > 1.1 + r() * 0.6;
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

const smooth = (t: number) => t * t * (3 - 2 * t);
const easeOut = (t: number) => 1 - Math.pow(1 - t, 4);

function camAt(p: number): Cam {
  const i = Math.max(0, Math.min(CAMERAS.length - 1, Math.floor(p)));
  const j = Math.min(CAMERAS.length - 1, i + 1);
  const k = smooth(Math.max(0, Math.min(1, p - i)));
  const a = CAMERAS[i];
  const b = CAMERAS[j];
  return { zoom: a.zoom + (b.zoom - a.zoom) * k, pitch: a.pitch + (b.pitch - a.pitch) * k, bearing: a.bearing + (b.bearing - a.bearing) * k };
}

export default function HeroMap({ spot, comps, scene = 0, progress }: { spot: Spot; comps: PreviewComp[]; scene?: number; progress?: MutableRefObject<number> }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const deck = useRef<DeckHandle | null>(null);
  const [ready, setReady] = useState(false);
  const state = useRef({ spot, comps, scene, people: [] as Person[], bins: [] as Bin[], walkers: [] as Person[], free: false, cur: CAMERAS[0] as Cam, t0: 0 });
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
        // start high and flat; the first flight is the descent into the street
        m = new maplibregl.Map({
          container: el.current, style, center: [spot.lng, spot.lat], zoom: 12, pitch: 0, bearing: -80, interactive: false,
          attributionControl: { compact: true }, maxPitch: 80, fadeDuration: 0, pixelRatio: Math.min(window.devicePixelRatio || 1, 1.5),
        });
      } catch {
        return;
      }
      map.current = m;
      m.on("load", async () => {
        enhanceMap(m, { buildingsMinZoom: 12, theme: "blueprint" });
        const d = await attachDeck(m);
        if (cancelled) return;
        deck.current = d;
        setReady(true);
        const loop = (now: number) => {
          const S = state.current;
          // scroll scrubs the camera; a slow drift keeps the city alive when the page is still
          if (S.free && !m.isMoving()) {
            const target = camAt(progress?.current ?? S.scene);
            const c = S.cur;
            const k = 0.075;
            S.cur = { zoom: c.zoom + (target.zoom - c.zoom) * k, pitch: c.pitch + (target.pitch - c.pitch) * k, bearing: c.bearing + (target.bearing - c.bearing) * k };
            m.jumpTo({ center: [S.spot.lng, S.spot.lat], zoom: S.cur.zoom, pitch: S.cur.pitch, bearing: S.cur.bearing + (now - S.t0) * 0.0016 });
          }
          const sc = S.scene;
          const all = sc === 0;
          const showComps = all || sc >= 2;
          const showPeople = all || sc >= 3;
          const choose = all || sc >= 4;
          const showTrips = all || sc >= 4;
          const t = (now / 22) % 1400;
          const pulse = (now / 12) % 260;
          const binMax = Math.max(1, ...S.bins.map((b) => b.n));
          const pc = (p: Person) => (!choose ? rgba(RED, 235) : p.choice === "you" ? rgba(WHITE, 255) : p.choice === "rival" ? rgba(INK, 210) : rgba(HAZE, 120));
          d?.setLayers((DL) => [
            new DL.ScatterplotLayer({
              id: "catchment", data: [S.spot], getPosition: (s: Spot) => [s.lng, s.lat], radiusUnits: "meters",
              getRadius: sc === 1 || sc === 5 ? 1500 : 0, getFillColor: rgba(WHITE, 16), getLineColor: rgba(WHITE, 200),
              stroked: true, lineWidthMinPixels: 1.5, transitions: { getRadius: { duration: 1400, easing: easeOut } }, updateTriggers: { getRadius: sc },
            }),
            new DL.ColumnLayer({
              id: "density", data: S.bins, diskResolution: 6, angle: 30, radius: 80, coverage: 0.86, extruded: true, wireframe: true,
              getPosition: (b: Bin) => b.pos, getElevation: (b: Bin) => (sc === 3 ? 10 + (b.n / binMax) * 260 : 0),
              getFillColor: rgba(WHITE, sc === 3 ? 28 : 0), getLineColor: rgba(WHITE, sc === 3 ? 170 : 0),
              transitions: { getElevation: { duration: 1300, easing: easeOut }, getFillColor: { duration: 600 }, getLineColor: { duration: 600 } },
              updateTriggers: { getElevation: [sc, binMax], getFillColor: sc === 3, getLineColor: sc === 3 },
            }),
            showTrips && new DL.TripsLayer({
              id: "trips", data: S.walkers, getPath: (x: Person) => x.path, getTimestamps: (x: Person) => x.ts,
              getColor: (x: Person) => (x.choice === "you" ? WHITE : INK), widthMinPixels: 2, trailLength: 80, currentTime: t,
              fadeTrail: true, capRounded: true, jointRounded: true, opacity: sc === 5 ? 0.5 : 0.9,
            }),
            new DL.ScatterplotLayer({
              id: "people", data: S.people, getPosition: (p: Person) => p.home, radiusUnits: "meters", radiusMinPixels: 0,
              getRadius: showPeople ? 9 : 0, getFillColor: pc, stroked: false,
              transitions: { getRadius: { duration: 900, easing: easeOut }, getFillColor: { duration: 900 } },
              updateTriggers: { getRadius: showPeople, getFillColor: choose },
            }),
            new DL.ColumnLayer({
              id: "comps", data: S.comps, diskResolution: 4, angle: 45, radius: 13, extruded: true, wireframe: true,
              getPosition: (c: PreviewComp) => [c.lng, c.lat], getElevation: showComps ? 110 : 0,
              getFillColor: rgba(INK, 235), getLineColor: rgba(WHITE, 150),
              transitions: { getElevation: { duration: 1400, easing: easeOut, enter: () => [0] } }, updateTriggers: { getElevation: showComps },
            }),
            new DL.ScatterplotLayer({
              id: "site-ring", data: [S.spot], getPosition: (s: Spot) => [s.lng, s.lat], radiusUnits: "meters",
              getRadius: 40 + pulse, getFillColor: [0, 0, 0, 0], getLineColor: rgba(WHITE, Math.max(0, 230 - pulse * 0.88)),
              stroked: true, filled: false, lineWidthMinPixels: 2, updateTriggers: { getRadius: now, getLineColor: now },
            }),
            new DL.ColumnLayer({
              id: "site", data: [S.spot], diskResolution: 36, radius: 20, extruded: true,
              getPosition: (s: Spot) => [s.lng, s.lat], getElevation: sc === 5 ? 1100 : 640, getFillColor: rgba(WHITE, 255),
              transitions: { getElevation: { duration: 1400, easing: easeOut, enter: () => [0] } }, updateTriggers: { getElevation: sc === 5 },
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
  }, [spot, comps]);

  // the descent (on load and when the street changes), then hand the camera to the scroll
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const S = state.current;
    S.free = false;
    const cam = camAt(progress?.current ?? S.scene);
    m.flyTo({ center: [spot.lng, spot.lat], ...cam, duration: 4000, curve: 1.15, essential: true });
    const done = () => {
      S.cur = { zoom: m.getZoom(), pitch: m.getPitch(), bearing: m.getBearing() };
      S.t0 = performance.now();
      S.free = true;
    };
    m.once("moveend", done);
    return () => {
      m.off("moveend", done);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, spot]);

  return (
    <div className="absolute inset-0" aria-hidden>
      <div ref={el} style={{ position: "absolute", inset: 0 }} />
    </div>
  );
}
