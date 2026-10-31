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
    <aside className="flex h-full w-60 flex-col border-r border-black/[0.06] bg-white">
      <div className="flex h-16 items-center px-5">
        <Logo href="/app" />
      </div>
      <div className="px-3 pb-3">
        <Link href="/app/projects/new" className="sheen flex h-10 items-center justify-center gap-2 rounded-lg bg-accent text-sm font-medium text-white shadow-[0_8px_30px_-12px_rgba(47,73,255,.9)] transition-colors hover:bg-[#2238e0]">
          <Plus className="h-4 w-4" /> New analysis
        </Link>
      </div>
      <nav className="flex-1 space-y-0.5 px-3 pt-2" aria-label="Main">
        <p className="idx px-3 pb-2">WORKSPACE</p>
        {nav.filter((n) => n.href !== "/app/projects/new").map((n) => {
          const active = n.exact ? path === n.href : path.startsWith(n.href);
          return (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] transition-colors",
                active ? "bg-black/[0.06] text-ink-100" : "text-ink-300 hover:bg-black/[0.03] hover:text-ink-100",
              )}
            >
              <n.icon className={cn("h-4 w-4", active && "text-accent")} /> {n.label}
            </Link>
          );
        })}
      </nav>
      <div className="mx-3 mb-3 flex items-center gap-2 rounded-lg border border-black/[0.06] px-3 py-2.5 text-xs text-ink-300" title={caps ? `Places: OSM + Foursquare · Population: WorldPop · Travel: ${caps.routing ? "road routing" : "radius"} · Model ${caps.model_version}` : undefined}>
        <span className="relative flex h-2 w-2">
          <span className={cn("absolute inline-flex h-full w-full rounded-full opacity-70", caps ? "animate-ping bg-ok" : "bg-ink-500")} />
          <span className={cn("relative inline-flex h-2 w-2 rounded-full", caps ? "bg-ok" : "bg-ink-500")} />
        </span>
        {caps ? "Live data connected" : "Connecting…"}
        {caps && <span className="num ml-auto font-mono text-[10px] text-ink-500">{caps.model_version}</span>}
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-black/[0.06] px-5 py-4 text-xs">
        <span className="flex min-w-0 items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent text-[11px] font-semibold text-white">
            {(user?.name || user?.email || "?").slice(0, 1).toUpperCase()}
          </span>
          <span className="truncate text-ink-300" title={user?.email}>{user?.name || user?.email || " "}</span>
        </span>
        <button onClick={logout} className="rounded-md p-1.5 text-ink-400 hover:bg-black/5 hover:text-ink-100" aria-label="Sign out" title="Sign out">
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
          <div className="flex h-14 items-center gap-3 border-b border-black/[0.06] px-4 md:hidden">
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
