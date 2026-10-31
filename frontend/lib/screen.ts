/**
 * What the user is looking at right now. Pages publish a small, number-only summary of their visible state;
 * the voice analyst reads it so it can answer "what am I looking at?" from the same numbers on screen.
 */
export type ScreenState = Record<string, unknown> & { page: string; scenario_id?: string | null };

declare global {
  interface Window {
    __strataScreen?: ScreenState & { at: number };
  }
}

export function publishScreen(state: ScreenState) {
  if (typeof window === "undefined") return;
  window.__strataScreen = { ...state, at: Date.now() };
}

export function readScreen(): (ScreenState & { at: number }) | null {
  if (typeof window === "undefined") return null;
  return window.__strataScreen || null;
}

/** Hand a finished strategy run to the live page, even if it hasn't mounted yet (voice can run one from any page). */
export function sendStrategy(detail: { scenario_id?: string; result?: unknown }) {
  if (typeof window === "undefined") return;
  (window as unknown as { __strataPending?: unknown }).__strataPending = detail;
  window.dispatchEvent(new CustomEvent("strataiq:strategy"));
}

export function takePendingStrategy<T = { scenario_id?: string; result?: unknown }>(): T | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { __strataPending?: T };
  const d = w.__strataPending ?? null;
  w.__strataPending = undefined;
  return d;
}

/** Everything a person can read on the current page: title, headings, visible text (voice panel excluded) and the
 *  numbers the page publishes. Lets the voice analyst "see" any page, not only the ones that publish numbers. */
export function readPage() {
  if (typeof document === "undefined") return null;
  const root = document.querySelector<HTMLElement>("main") || document.body;
  let text = root.innerText || "";
  const dock = document.querySelector<HTMLElement>("[data-voice-dock]");
  if (dock && root.contains(dock)) text = text.replace(dock.innerText, "");
  text = text.replace(/[ \t]+/g, " ").replace(/\n{2,}/g, "\n").trim();
  const headings = Array.from(root.querySelectorAll<HTMLElement>("h1, h2, h3"))
    .filter((h) => !dock?.contains(h))
    .map((h) => h.innerText.trim())
    .filter(Boolean)
    .slice(0, 24);
  return { path: window.location.pathname, title: document.title, headings, visible_text: text.slice(0, 5000), truncated: text.length > 5000, numbers: readScreen() };
}
