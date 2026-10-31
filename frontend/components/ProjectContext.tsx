"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { DemoBanner, ErrorState, Evidence, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Project } from "@/lib/types";
import { Journey } from "@/components/Journey";

interface Ctx {
  project: Project;
  reload: () => Promise<void>;
}
const ProjectCtx = createContext<Ctx | null>(null);

export function useProject(): Ctx {
  const c = useContext(ProjectCtx);
  if (!c) throw new Error("useProject outside provider");
  return c;
}

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setProject(await api<Project>(`/projects/${id}`));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load project");
    }
  }, [id]);
  useEffect(() => {
    reload();
  }, [reload]);
  // the voice analyst runs real what-if simulations; refresh when it does
  useEffect(() => {
    const h = () => void reload();
    window.addEventListener("strataiq:refresh", h);
    return () => window.removeEventListener("strataiq:refresh", h);
  }, [reload]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {project?.is_demo && <DemoBanner />}
      <div className="relative bg-night px-4 text-white md:px-8">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-5">
          {project ? (
            <>
              <Link href="/app" className="label-mono text-white/45 hover:text-white">Projects</Link>
              <span className="text-white/25">/</span>
              <h1 className="lp-wide truncate text-[22px] leading-none tracking-[-0.03em]">{project.name}</h1>
              <span className="hidden truncate text-sm text-white/50 sm:inline">{project.category.label}{project.locations[0] ? ` · ${(project.locations[0].address || project.locations[0].label).split(",").slice(0, 2).join(",")}` : ""}</span>
              {project.category.method !== "taxonomy" && project.category.method !== "manual" && <Evidence className="bg-white" kind={project.category.method === "llm" ? "ai" : "assumption"} label={project.category.method === "llm" ? "AI-mapped category" : "Keyword category"} />}
              {!project.is_demo && project.snapshots && Object.values(project.snapshots).some(Boolean) && (
                <span className="label-mono inline-flex items-center gap-1.5 rounded-sm border border-[#3ddc84]/40 px-2 py-0.5 text-[10px] text-[#3ddc84]">
                  <span className="relative flex h-1.5 w-1.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#3ddc84] opacity-70" /><span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#3ddc84]" /></span>
                  Live sources
                </span>
              )}
            </>
          ) : (
            <Skeleton className="h-6 w-64 bg-white/10" />
          )}
        </div>
        {project && <Journey project={project} />}
      </div>
      {error && (
        <div className="p-6">
          <ErrorState message={error} onRetry={reload} />
        </div>
      )}
      {!project && !error && (
        <div className="space-y-3 p-6">
          <Skeleton className="h-24" />
          <Skeleton className="h-64" />
        </div>
      )}
      {project && <ProjectCtx.Provider value={{ project, reload }}>{children}</ProjectCtx.Provider>}
    </div>
  );
}
