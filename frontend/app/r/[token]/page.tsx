"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo } from "@/components/brand";
import { ReportView, type ReportContent } from "@/components/ReportView";
import { ErrorState, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

export default function SharedReport() {
  const { token } = useParams<{ token: string }>();
  const [c, setC] = useState<ReportContent | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api<{ content: ReportContent }>(`/shared/reports/${token}`).then((r) => setC(r.content)).catch((e) => setErr(e instanceof ApiError ? e.message : "Not found"));
  }, [token]);
  return (
    <div className="min-h-screen bg-ink-950 px-4 py-8">
      <div className="no-print mx-auto mb-6 flex max-w-4xl items-center justify-between">
        <Logo />
        <span className="text-xs text-ink-400">Shared report snapshot</span>
      </div>
      {err && <div className="mx-auto max-w-4xl"><ErrorState message={err} /></div>}
      {!c && !err && <Skeleton className="mx-auto h-96 max-w-4xl" />}
      {c && <ReportView c={c} />}
    </div>
  );
}
