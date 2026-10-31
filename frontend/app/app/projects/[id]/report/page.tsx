"use client";

import { Copy, FileDown, Link2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useProject } from "@/components/ProjectContext";
import { ReportView, type ReportContent } from "@/components/ReportView";
import { Badge, Button, EmptyState, ErrorState, Select, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { when } from "@/lib/format";

interface ReportMeta {
  id: string;
  created_at: string;
  share_token: string | null;
}

export default function ReportPage() {
  const { project: p } = useProject();
  const [list, setList] = useState<ReportMeta[] | null>(null);
  const [cur, setCur] = useState<(ReportMeta & { content: ReportContent }) | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const open = useCallback(async (id: string) => {
    setCur(await api(`/reports/${id}`));
  }, []);

  const load = useCallback(async () => {
    try {
      const l = await api<ReportMeta[]>(`/projects/${p.id}/reports`);
      setList(l);
      if (l[0]) await open(l[0].id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load reports");
    }
  }, [p.id, open]);
  useEffect(() => {
    load();
  }, [load]);

  async function generate(share: boolean) {
    setBusy(true);
    setError(null);
    try {
      const r = await api<ReportMeta>(`/projects/${p.id}/reports?share=${share}`, { method: "POST" });
      await load();
      await open(r.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not generate report");
    } finally {
      setBusy(false);
    }
  }

  const shareUrl = cur?.share_token && typeof window !== "undefined" ? `${window.location.origin}/r/${cur.share_token}` : null;

  return (
    <main className="mx-auto w-full max-w-5xl space-y-4 p-4 md:p-6">
      <div className="no-print flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={() => generate(false)} loading={busy}><RefreshCw className="h-3.5 w-3.5" /> Generate from latest results</Button>
        <Button onClick={() => generate(true)} loading={busy}><Link2 className="h-3.5 w-3.5" /> Generate shareable link</Button>
        {cur && <Button onClick={() => window.print()}><FileDown className="h-3.5 w-3.5" /> Save as PDF</Button>}
        {list && list.length > 1 && (
          <Select value={cur?.id} onChange={(e) => open(e.target.value)} className="ml-auto h-8 w-auto text-xs" aria-label="Report version">
            {list.map((r) => <option key={r.id} value={r.id}>{when(r.created_at)}{r.share_token ? " · shared" : ""}</option>)}
          </Select>
        )}
      </div>
      {shareUrl && (
        <div className="no-print flex flex-wrap items-center gap-2 rounded-xl border border-black/[0.07] bg-black/[0.025] p-2 text-xs">
          <Badge tone="accent">Anyone with this link can view this report snapshot</Badge>
          <code className="num truncate text-ink-200">{shareUrl}</code>
          <Button size="sm" onClick={() => { navigator.clipboard.writeText(shareUrl); setCopied(true); setTimeout(() => setCopied(false), 1500); }}><Copy className="h-3 w-3" /> {copied ? "Copied" : "Copy"}</Button>
          <Button size="sm" variant="ghost" onClick={async () => { await api(`/reports/${cur!.id}/unshare`, { method: "POST" }); await open(cur!.id); load(); }}>Revoke link</Button>
        </div>
      )}
      {error && <ErrorState message={error} />}
      {list === null && !error && <Skeleton className="h-96" />}
      {list && list.length === 0 && <EmptyState title="No report yet" body="Generate a report to capture the current evidence, assumptions, scenarios and decision as a snapshot." />}
      {cur && <ReportView c={cur.content} />}
    </main>
  );
}
