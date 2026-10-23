"use client";

import dynamic from "next/dynamic";
import { Component, type ReactNode } from "react";

/** The voice SDK uses browser audio APIs, so the dock is client-only. */
const VoiceDock = dynamic(() => import("./VoiceDock"), { ssr: false });

/** A voice failure must never take the rest of the app down with it. */
class Guard extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(e: unknown) {
    console.warn("voice dock disabled:", e);
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export default function VoiceDockLoader() {
  return (
    <Guard>
      <VoiceDock />
    </Guard>
  );
}
