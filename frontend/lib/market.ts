import { api } from "@/lib/api";

interface SnapStatus {
  id: string;
  status: "loading" | "complete" | "partial" | "failed";
  errors: { source: string; message: string }[];
}

/** Poll a background market-snapshot job until it finishes (or ~3 minutes pass). */
export async function waitForSnapshot(projectId: string, snapshotId: string, onTick?: (seconds: number) => void): Promise<SnapStatus> {
  const t0 = Date.now();
  for (;;) {
    const s = await api<SnapStatus>(`/projects/${projectId}/snapshots/${snapshotId}`);
    if (s.status !== "loading") return s;
    const secs = Math.round((Date.now() - t0) / 1000);
    onTick?.(secs);
    if (secs > 200) return { ...s, status: "failed", errors: [{ source: "job", message: "Still loading after 3 minutes. Check again shortly." }] };
    await new Promise((r) => setTimeout(r, 2500));
  }
}

/** Start loading live evidence for a location; resolves when the snapshot is ready. */
export async function refreshLocation(projectId: string, locationId: string, onTick?: (seconds: number) => void): Promise<SnapStatus> {
  const s = await api<SnapStatus>(`/projects/${projectId}/locations/${locationId}/refresh`, { method: "POST" });
  return s.status === "loading" ? waitForSnapshot(projectId, s.id, onTick) : s;
}
