import Link from "next/link";

/** Mark: three survey strata (स्तर = layer) with the site point lit in saffron. */
export function LogoMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <path d="M4 20.5 16 26l12-5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className="text-ink-500" />
      <path d="M4 15.5 16 21l12-5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" className="text-ink-300" />
      <path d="M4 10.5 16 16l12-5.5L16 5 4 10.5Z" stroke="var(--color-accent)" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx="16" cy="10.6" r="2.2" fill="var(--color-accent)" />
    </svg>
  );
}

export function Logo({ href = "/", compact = false }: { href?: string; compact?: boolean }) {
  return (
    <Link href={href} className="group flex items-center gap-2.5 text-ink-100" aria-label="StrataIQ home">
      <LogoMark />
      {!compact && (
        <span className="flex items-baseline gap-1.5">
          <span className="font-display text-[17px] font-medium tracking-tight">StrataIQ</span>
          <span className="font-deva text-[13px] text-ink-400 transition-colors group-hover:text-accent" lang="hi">स्तर</span>
        </span>
      )}
    </Link>
  );
}
