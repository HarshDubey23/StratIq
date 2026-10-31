"use client";

import { BookOpen, LayoutGrid, LogOut, Menu, Plus, Settings, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { Logo } from "@/components/brand";
import { cn } from "@/components/ui";
import { api } from "@/lib/api";
import type { Capabilities, User } from "@/lib/types";

const Ctx = createContext<{ user: User | null; caps: Capabilities | null }>({ user: null, caps: null });
export const useSession = () => useContext(Ctx);

const nav = [
  { href: "/app", label: "My projects", icon: LayoutGrid, exact: true },
  { href: "/app/projects/new", label: "New analysis", icon: Plus },
  { href: "/methodology", label: "Methodology", icon: BookOpen },
  { href: "/app/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [open, setOpen] = useState(false);
  const path = usePathname();
  const router = useRouter();

  useEffect(() => {
    api<User>("/auth/me").then(setUser).catch(() => undefined);
    api<Capabilities>("/system/capabilities").then(setCaps).catch(() => undefined);
  }, []);
  useEffect(() => setOpen(false), [path]);

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    router.push("/sign-in");
    router.refresh();
  }

  const side = (
    <aside className="flex h-full w-60 flex-col bg-night text-white">
      <div className="flex h-16 items-center border-b border-white/10 px-5">
        <Logo href="/app" tone="dark" />
      </div>
      <div className="p-3">
        <Link href="/app/projects/new" className="sheen flex h-11 items-center justify-between rounded-md bg-accent px-4 text-sm font-semibold text-white transition-colors hover:bg-white hover:text-night">
          New analysis <Plus className="h-4 w-4" />
        </Link>
      </div>
      <nav className="flex-1 px-3 pt-3" aria-label="Main">
        <p className="label-mono px-2 pb-2 text-white/35">Workspace</p>
        {nav.filter((n) => n.href !== "/app/projects/new").map((n, i) => {
          const active = n.exact ? path === n.href : path.startsWith(n.href);
          return (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "group relative flex items-center gap-3 border-t border-white/[0.08] px-2 py-2.5 text-[13.5px] transition-colors",
                active ? "text-white" : "text-white/55 hover:text-white",
              )}
            >
              <span className={cn("label-mono w-5 transition-colors", active ? "text-accent" : "text-white/30 group-hover:text-white/60")}>0{i + 1}</span>
              <span className="flex-1">{n.label}</span>
              <n.icon className={cn("h-4 w-4 transition-colors", active ? "text-accent" : "text-white/30 group-hover:text-white/60")} />
              {active && <span aria-hidden className="absolute -left-3 top-1/2 h-5 w-[3px] -translate-y-1/2 bg-accent" />}
            </Link>
          );
        })}
      </nav>
      <div className="mx-3 mb-3 flex items-center gap-2 rounded-md border border-white/10 px-3 py-2.5 text-xs text-white/60" title={caps ? `Places: OSM + Foursquare · Population: WorldPop · Travel: ${caps.routing ? "road routing" : "radius"} · Model ${caps.model_version}` : undefined}>
        <span className="relative flex h-2 w-2">
          <span className={cn("absolute inline-flex h-full w-full rounded-full opacity-70", caps ? "animate-ping bg-ok" : "bg-white/30")} />
          <span className={cn("relative inline-flex h-2 w-2 rounded-full", caps ? "bg-[#3ddc84]" : "bg-white/30")} />
        </span>
        {caps ? "Live data connected" : "Connecting…"}
        {caps && <span className="num ml-auto font-mono text-[10px] text-white/35">{caps.model_version}</span>}
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-white/10 px-5 py-4 text-xs">
        <span className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-accent text-[11px] font-semibold text-white">
            {(user?.name || user?.email || "?").slice(0, 1).toUpperCase()}
          </span>
          <span className="truncate text-white/70" title={user?.email}>{user?.name || user?.email || " "}</span>
        </span>
        <button onClick={logout} className="rounded-sm p-1.5 text-white/45 hover:bg-white/10 hover:text-white" aria-label="Sign out" title="Sign out">
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </aside>
  );

  return (
    <Ctx.Provider value={{ user, caps }}>
      <div className="flex min-h-screen">
        <div className="sticky top-0 hidden h-screen md:block">{side}</div>
        {open && (
          <div className="fixed inset-0 z-50 flex md:hidden">
            <div className="h-full">{side}</div>
            <button className="flex-1 bg-black/60 backdrop-blur-sm" aria-label="Close menu" onClick={() => setOpen(false)} />
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-14 items-center gap-3 bg-night px-4 text-white md:hidden">
            <button onClick={() => setOpen((x) => !x)} aria-label="Menu" className="text-white/80">
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
            <Logo href="/app" tone="dark" />
          </div>
          {children}
        </div>
      </div>
    </Ctx.Provider>
  );
}
