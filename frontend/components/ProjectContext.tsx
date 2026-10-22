"use client";

import { BarChart3, ClipboardList, Dna, FileText, Layers, LineChart, Map as MapIcon, SlidersHorizontal, Users } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { cn, DemoBanner, ErrorState, Evidence, Skeleton } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Project } from "@/lib/types";

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

const tabs = [
  { seg: "", label: "Overview", step: null, icon: ClipboardList },
  { seg: "/market", label: "Market map", step: 1, icon: MapIcon },
  { seg: "/live", label: "Live market", step: 2, icon: Users },
  { seg: "/genome", label: "Market DNA", step: 3, icon: Dna },
  { seg: "/simulation", label: "Simulation lab", step: 4, icon: SlidersHorizontal },
  { seg: "/decisions", label: "Decisions", step: 5, icon: BarChart3 },
  { seg: "/report", label: "Report", step: null, icon: FileText },
  { seg: "/factors", label: "615 factors", step: null, icon: Layers },
  { seg: "/monitor", label: "Monitoring", step: null, icon: LineChart },
];

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const path = usePathname();
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

  const base = `/app/projects/${id}`;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {project?.is_demo && <DemoBanner />}
      <div className="relative border-b border-white/[0.06] bg-ink-950/80 px-4 backdrop-blur-xl md:px-8">
        <div className="flex flex-wrap items-end gap-x-4 gap-y-1 pt-5">
          {project ? (
            <>
              <h1 className="font-display truncate text-[26px] font-semibold leading-none tracking-tight">{project.name}</h1>
              <span className="pb-0.5 text-sm text-ink-400">{project.category.label} — {project.archetype?.label}</span>
              {project.locations[0] && <span className="pb-0.5 text-sm text-ink-400">{project.locations[0].address || project.locations[0].label}</span>}
              {project.category.method !== "taxonomy" && project.category.method !== "manual" && <Evidence kind={project.category.method === "llm" ? "ai" : "assumption"} label={project.category.method === "llm" ? "AI-mapped category" : "Keyword category"} />}
              {!project.is_demo && project.snapshots && Object.values(project.snapshots).some(Boolean) && (
                <span className="mb-0.5 inline-flex items-center gap-1.5 rounded-full border border-model/30 bg-model/10 px-2 py-0.5 text-[11px] text-model">
                  <span className="relative flex h-1.5 w-1.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-model opacity-70" /><span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-model" /></span>
                  Live sources
                </span>
              )}
            </>
          ) : (
            <Skeleton className="h-7 w-64" />
          )}
        </div>
        <nav className="-mb-px mt-4 flex gap-1 overflow-x-auto" aria-label="Project">
          {tabs.map((t) => {
            const href = base + t.seg;
            const active = t.seg === "" ? path === base : path.startsWith(href);
            return (
              <Link
                key={t.seg}
                href={href}
                className={cn(
                  "group relative flex shrink-0 items-center gap-2 px-3 py-2.5 text-[13px] transition-colors",
                  active ? "text-ink-100" : "text-ink-400 hover:text-ink-100",
                )}
              >
                {t.step ? (
                  <span className={cn("num flex h-4 w-4 items-center justify-center rounded-full text-[9.5px] font-semibold", active ? "bg-accent text-ink-950" : "bg-white/[0.07] text-ink-300 group-hover:bg-white/15")}>{t.step}</span>
                ) : (
                  <t.icon className="h-3.5 w-3.5" />
                )}
                {t.label}
                <span className={cn("absolute inset-x-3 -bottom-px h-[2px] rounded-full bg-accent transition-transform duration-500", active ? "scale-x-100" : "scale-x-0")} style={{ transitionTimingFunction: "cubic-bezier(.16,1,.3,1)" }} />
              </Link>
            );
          })}
        </nav>
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
