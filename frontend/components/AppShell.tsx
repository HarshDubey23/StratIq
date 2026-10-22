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
    <aside className="flex h-full w-56 flex-col border-r border-ink-800 bg-ink-950">
      <div className="flex h-14 items-center border-b border-ink-800 px-4">
        <Logo href="/app" />
      </div>
      <nav className="flex-1 space-y-0.5 p-2" aria-label="Main">
        {nav.map((n) => {
          const active = n.exact ? path === n.href : path.startsWith(n.href);
          return (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm",
                active ? "bg-ink-800 text-ink-100" : "text-ink-300 hover:bg-ink-900 hover:text-ink-100",
              )}
            >
              <n.icon className="h-4 w-4" /> {n.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-ink-800 p-3 text-xs">
        {caps && (
          <div className="mb-3 space-y-1 text-ink-400">
            <div className="flex justify-between"><span>Places</span><span className="text-ink-200">OpenStreetMap</span></div>
            <div className="flex justify-between"><span>Population</span><span className="text-ink-200">WorldPop</span></div>
            <div className="flex justify-between"><span>Travel time</span><span className={caps.routing ? "text-ink-200" : "text-ink-500"}>{caps.routing ? "openrouteservice" : "radius only"}</span></div>
            <div className="flex justify-between"><span>AI text</span><span className={caps.ai ? "text-ink-200" : "text-ink-500"}>{caps.ai ? "enabled" : "off"}</span></div>
            <div className="flex justify-between"><span>Model</span><span className="num text-ink-200">{caps.model_version}</span></div>
          </div>
        )}
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-ink-300" title={user?.email}>{user?.name || user?.email || " "}</span>
          <button onClick={logout} className="text-ink-400 hover:text-ink-100" aria-label="Sign out" title="Sign out">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
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
            <button className="flex-1 bg-black/50" aria-label="Close menu" onClick={() => setOpen(false)} />
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-12 items-center gap-3 border-b border-ink-800 px-3 md:hidden">
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
