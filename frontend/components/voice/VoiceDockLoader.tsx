"use client";

import dynamic from "next/dynamic";

/** The voice SDK uses browser audio APIs, so the dock is client-only. */
const VoiceDock = dynamic(() => import("./VoiceDock"), { ssr: false });

export default function VoiceDockLoader() {
  return <VoiceDock />;
}
