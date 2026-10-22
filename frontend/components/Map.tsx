"use client";

import dynamic from "next/dynamic";

/** MapLibre touches `window` at import time, so the map is client-only. */
export const Map = dynamic(() => import("./MapView"), {
  ssr: false,
  loading: () => <div className="flex h-full w-full items-center justify-center bg-ink-900 text-sm text-ink-400">Loading map…</div>,
});
