import Link from "next/link";

export function LogoMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 2.5 21 7.5v9L12 21.5 3 16.5v-9L12 2.5Z" stroke="currentColor" strokeWidth="1.4" className="text-ink-400" />
      <path d="M3 12.2 12 17l9-4.8" stroke="var(--color-accent)" strokeWidth="1.6" />
      <path d="M3 8.6 12 13.4l9-4.8" stroke="currentColor" strokeWidth="1.2" className="text-ink-300" />
      <circle cx="12" cy="13.4" r="1.6" fill="var(--color-accent)" />
    </svg>
  );
}

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="flex items-center gap-2 text-ink-100" aria-label="StrataIQ home">
      <LogoMark />
      <span className="text-[15px] font-semibold tracking-tight">
        Strata<span className="text-accent">IQ</span>
      </span>
    </Link>
  );
}
