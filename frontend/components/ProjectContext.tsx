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
  { seg: "", label: "Overview", icon: ClipboardList },
  { seg: "/market", label: "1 · Market map", icon: MapIcon },
  { seg: "/live", label: "2 · Live market", icon: Users },
  { seg: "/genome", label: "3 · Market DNA", icon: Dna },
  { seg: "/simulation", label: "4 · Simulation lab", icon: SlidersHorizontal },
  { seg: "/decisions", label: "5 · Decisions", icon: BarChart3 },
  { seg: "/report", label: "Report", icon: FileText },
  { seg: "/factors", label: "615 factors", icon: Layers },
  { seg: "/monitor", label: "Monitoring", icon: LineChart },
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

  const base = `/app/projects/${id}`;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {project?.is_demo && <DemoBanner />}
      <div className="border-b border-ink-800 bg-ink-950 px-4 md:px-6">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-3">
          {project ? (
            <>
              <h1 className="truncate text-base font-semibold">{project.name}</h1>
              <span className="text-xs text-ink-400">{project.category.label} · {project.archetype?.label}</span>
              {project.category.method !== "taxonomy" && project.category.method !== "manual" && <Evidence kind={project.category.method === "llm" ? "ai" : "assumption"} label={project.category.method === "llm" ? "AI-mapped category" : "Keyword category"} />}
            </>
          ) : (
            <Skeleton className="h-5 w-56" />
          )}
        </div>
        <nav className="-mb-px mt-2 flex gap-1 overflow-x-auto" aria-label="Project">
          {tabs.map((t) => {
            const href = base + t.seg;
            const active = t.seg === "" ? path === base : path.startsWith(href);
            return (
              <Link
                key={t.seg}
                href={href}
                className={cn(
                  "flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm",
                  active ? "border-accent text-ink-100" : "border-transparent text-ink-400 hover:text-ink-100",
                )}
              >
                <t.icon className="h-3.5 w-3.5" /> {t.label}
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
