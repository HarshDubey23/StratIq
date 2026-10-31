import Link from "next/link";
import cn from "clsx";

/** Mark: three survey strata (स्तर = layer) with the site point lit in cobalt. */
export function LogoMark({ size = 24, tone = "light" }: { size?: number; tone?: "light" | "dark" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <path d="M4 20.5 16 26l12-5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className={tone === "dark" ? "text-white/35" : "text-ink-500"} />
      <path d="M4 15.5 16 21l12-5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className={tone === "dark" ? "text-white/65" : "text-ink-300"} />
      <path d="M4 10.5 16 16l12-5.5L16 5 4 10.5Z" stroke="var(--color-accent)" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx="16" cy="10.6" r="2.2" fill="var(--color-accent)" />
    </svg>
  );
}

/** `tone="dark"` sits on night or cobalt grounds. */
export function Logo({ href = "/", compact = false, tone = "light" }: { href?: string; compact?: boolean; tone?: "light" | "dark" }) {
  return (
    <Link href={href} className={cn("group flex items-center gap-2.5", tone === "dark" ? "text-white" : "text-ink-100")} aria-label="StrataIQ home">
      <LogoMark tone={tone} />
      {!compact && (
        <span className="flex items-baseline gap-1.5">
          <span className="lp-wide text-[16px] tracking-[-0.02em]">StrataIQ</span>
          <span className={cn("font-deva text-[13px] transition-colors group-hover:text-accent", tone === "dark" ? "text-white/45" : "text-ink-400")} lang="hi">स्तर</span>
        </span>
      )}
    </Link>
  );
}
