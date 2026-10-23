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
  { href: "/app", label: "Overview", icon: LayoutGrid, exact: true },
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
    <aside className="flex h-full w-60 flex-col border-r border-white/[0.06] bg-ink-950/90 backdrop-blur-xl">
      <div className="flex h-16 items-center px-5">
        <Logo href="/app" />
      </div>
      <nav className="flex-1 space-y-0.5 px-3 pt-2" aria-label="Main">
        {nav.map((n) => {
          const active = n.exact ? path === n.href : path.startsWith(n.href);
          return (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors",
                active ? "bg-white/[0.06] text-ink-100" : "text-ink-300 hover:bg-white/[0.03] hover:text-ink-100",
              )}
            >
              {active && <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-full bg-accent" />}
              <n.icon className="h-4 w-4" /> {n.label}
            </Link>
          );
        })}
      </nav>
      <div className="m-3 rounded-2xl border border-white/[0.06] bg-white/[0.02] p-3.5 text-xs">
        <div className="mb-2.5 flex items-center gap-2 text-ink-200">
          <span className="relative flex h-2 w-2">
            <span className={cn("absolute inline-flex h-full w-full rounded-full opacity-70", caps ? "animate-ping bg-model" : "bg-ink-500")} />
            <span className={cn("relative inline-flex h-2 w-2 rounded-full", caps ? "bg-model" : "bg-ink-500")} />
          </span>
          {caps ? "Live data connected" : "Connecting to data…"}
        </div>
        {caps && (
          <div className="space-y-1.5 text-ink-400">
            <div className="flex justify-between"><span>Places</span><span className="text-ink-200">OSM + Foursquare</span></div>
            <div className="flex justify-between"><span>Population</span><span className="text-ink-200">WorldPop</span></div>
            <div className="flex justify-between"><span>Travel time</span><span className={caps.routing ? "text-ink-200" : "text-ink-500"}>{caps.routing ? "openrouteservice" : "radius"}</span></div>
            <div className="flex justify-between"><span>Voice</span><span className="text-ink-200">Strata</span></div>
            <div className="flex justify-between"><span>Model</span><span className="num text-ink-200">{caps.model_version}</span></div>
          </div>
        )}
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-white/[0.06] px-5 py-4 text-xs">
        <span className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent to-agent text-[11px] font-semibold text-ink-950">
            {(user?.name || user?.email || "?").slice(0, 1).toUpperCase()}
          </span>
          <span className="truncate text-ink-300" title={user?.email}>{user?.name || user?.email || " "}</span>
        </span>
        <button onClick={logout} className="rounded-full p-1.5 text-ink-400 hover:bg-white/5 hover:text-ink-100" aria-label="Sign out" title="Sign out">
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
          <div className="flex h-14 items-center gap-3 border-b border-white/[0.06] px-4 md:hidden">
            <button onClick={() => setOpen((x) => !x)} aria-label="Menu" className="text-ink-200">
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
            <Logo href="/app" />
          </div>
          {children}
        </div>
      </div>
    </Ctx.Provider>
  );
}
