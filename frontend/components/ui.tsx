"use client";

import clsx from "clsx";
import { AlertTriangle, Info, Loader2, X } from "lucide-react";
import Link from "next/link";
import React, { useEffect, useId, useState } from "react";

export function cn(...a: Parameters<typeof clsx>) {
  return clsx(...a);
}

type BtnVariant = "primary" | "secondary" | "ghost" | "danger";
const btnBase =
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium tracking-[-0.01em] transition-[background,color,box-shadow,transform,border-color] duration-300 ease-out active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap";
const btnVariants: Record<BtnVariant, string> = {
  primary: "sheen bg-accent text-white shadow-[0_8px_30px_-10px_rgba(79,108,255,.75)] hover:bg-[#6580ff] hover:shadow-[0_12px_40px_-10px_rgba(79,108,255,.95)]",
  secondary: "border border-white/10 bg-white/[0.035] text-ink-100 hover:border-white/20 hover:bg-white/[0.07]",
  ghost: "text-ink-300 hover:bg-white/[0.06] hover:text-ink-100",
  danger: "border border-danger/40 bg-danger/10 text-red-300 hover:bg-danger/20",
};
const btnSizes = { sm: "h-8 px-3 text-xs", md: "h-10 px-4.5", lg: "h-12 px-6 text-[15px]" };

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  className,
  children,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: keyof typeof btnSizes; loading?: boolean }) {
  return (
    <button className={cn(btnBase, btnVariants[variant], btnSizes[size], className)} disabled={loading || rest.disabled} {...rest}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  className,
  children,
}: {
  href: string;
  variant?: BtnVariant;
  size?: keyof typeof btnSizes;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Link href={href} className={cn(btnBase, btnVariants[variant], btnSizes[size], className)}>
      {children}
    </Link>
  );
}

export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-xl border border-white/[0.07] bg-ink-900/80", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, right, className }: { title: React.ReactNode; subtitle?: React.ReactNode; right?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-3 border-b border-white/[0.06] px-5 py-3.5", className)}>
      <div className="min-w-0">
        <h3 className="font-display text-[15px] font-medium tracking-tight text-ink-100">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-ink-300">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

/** Evidence-type label. Every number on screen should carry one of these. */
export type EvidenceKind = "observed" | "user" | "assumption" | "model" | "demo" | "unknown" | "official" | "ai" | "field";
const kindStyle: Record<EvidenceKind, string> = {
  observed: "border-observed/40 bg-observed/10 text-observed",
  user: "border-userdata/40 bg-userdata/10 text-userdata",
  assumption: "border-assumption/40 bg-assumption/10 text-ink-200",
  model: "border-model/40 bg-model/10 text-model",
  demo: "border-warn/50 bg-warn/15 text-warn",
  unknown: "border-ink-500 bg-ink-800 text-ink-300",
  official: "border-sky-400/40 bg-sky-400/10 text-sky-300",
  ai: "border-fuchsia-400/40 bg-fuchsia-400/10 text-fuchsia-300",
  field: "border-field/50 bg-field/10 text-field",
};
const kindLabel: Record<EvidenceKind, string> = {
  observed: "Observed",
  user: "User",
  assumption: "Assumed",
  model: "Model",
  demo: "Demo",
  unknown: "Unknown",
  official: "Official est.",
  ai: "AI text",
  field: "Field-verified",
};
const kindTitle: Record<EvidenceKind, string> = {
  observed: "Observed in a data source (e.g. OpenStreetMap)",
  user: "Entered by you; not independently verified",
  assumption: "Model assumption with a documented range",
  model: "Estimated by the StrataIQ simulation",
  demo: "Illustrative demo data, not real",
  unknown: "Not available from any source",
  official: "Official modelled estimate (e.g. WorldPop)",
  ai: "Written by an AI model from the computed results",
  field: "Collected on the ground by a StrataIQ field researcher",
};

export function Evidence({ kind, label, className, title }: { kind: EvidenceKind; label?: string; className?: string; title?: string }) {
  return (
    <span
      title={title ?? kindTitle[kind]}
      className={cn("inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md border px-1.5 py-px text-[10.5px] font-medium", kindStyle[kind], className)}
    >
      {label ?? kindLabel[kind]}
    </span>
  );
}

export function statusToKind(status: string | null | undefined): EvidenceKind {
  if (!status) return "unknown";
  if (["user", "known"].includes(status)) return "user";
  if (status === "observed") return "observed";
  if (status === "field") return "field";
  if (["official", "industry", "literature"].includes(status)) return "official";
  if (status.startsWith("derived")) return "model";
  if (status.startsWith("assum") || status === "assumed") return "assumption";
  if (status === "unknown") return "unknown";
  return "assumption";
}

export function Badge({ children, tone = "neutral", className }: { children: React.ReactNode; tone?: "neutral" | "ok" | "warn" | "danger" | "accent"; className?: string }) {
  const tones = {
    neutral: "bg-ink-800 text-ink-200 border-ink-600",
    ok: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
    warn: "bg-amber-500/10 text-amber-300 border-amber-500/30",
    danger: "bg-red-500/10 text-red-300 border-red-500/30",
    accent: "bg-accent/10 text-[#9fb0ff] border-accent/40",
  };
  return <span className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs", tones[tone], className)}>{children}</span>;
}

export function Field({
  label,
  hint,
  error,
  children,
  kind,
  htmlFor,
}: {
  label: React.ReactNode;
  hint?: React.ReactNode;
  error?: string;
  children: React.ReactNode;
  kind?: EvidenceKind;
  htmlFor?: string;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <label htmlFor={htmlFor} className="text-xs font-medium text-ink-200">
          {label}
        </label>
        {kind && <Evidence kind={kind} />}
      </div>
      {children}
      {error ? <p className="text-xs text-red-300">{error}</p> : hint ? <p className="text-xs text-ink-400">{hint}</p> : null}
    </div>
  );
}

export const inputCls =
  "h-10 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3.5 text-sm text-ink-100 placeholder:text-ink-500 transition-[border-color,background,box-shadow] focus:border-accent focus:bg-white/[0.05] focus:shadow-[0_0_0_3px_rgba(79,108,255,.18)] focus:outline-none";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(inputCls, props.className)} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cn(inputCls, "h-auto min-h-20 py-2", props.className)} />;
}

export function Select({ className, children, ...rest }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={cn(inputCls, "pr-8", className)}>
      {children}
    </select>
  );
}

/** Numeric input that keeps a local string while typing and reports numbers (or null when empty). */
export function NumberInput({
  value,
  onChange,
  min,
  max,
  step,
  placeholder,
  prefix,
  suffix,
  id,
  allowEmpty = false,
  className,
}: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  prefix?: string;
  suffix?: string;
  id?: string;
  allowEmpty?: boolean;
  className?: string;
}) {
  const [text, setText] = useState(value === null || value === undefined ? "" : String(value));
  useEffect(() => {
    const cur = text === "" ? null : Number(text);
    if (cur !== value) setText(value === null || value === undefined ? "" : String(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <div className={cn("relative flex items-center", className)}>
      {prefix && <span className="pointer-events-none absolute left-3 text-sm text-ink-400">{prefix}</span>}
      <input
        id={id}
        inputMode="decimal"
        className={cn(inputCls, "num", prefix && "pl-7", suffix && "pr-14")}
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          const t = e.target.value.replace(/[^0-9.\-]/g, "");
          setText(t);
          if (t === "") {
            if (allowEmpty) onChange(null);
            return;
          }
          const n = Number(t);
          if (!Number.isNaN(n)) onChange(n);
        }}
        onBlur={() => {
          if (text === "") return;
          let n = Number(text);
          if (Number.isNaN(n)) return;
          if (min !== undefined) n = Math.max(min, n);
          if (max !== undefined) n = Math.min(max, n);
          setText(String(n));
          onChange(n);
        }}
        step={step}
      />
      {suffix && <span className="pointer-events-none absolute right-3 text-xs text-ink-400">{suffix}</span>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-white/[0.05]", className)} />;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-300" role="status">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function EmptyState({ icon, title, body, action }: { icon?: React.ReactNode; title: string; body?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-white/10 px-6 py-14 text-center">
      {icon && <div className="text-ink-400">{icon}</div>}
      <h3 className="font-display text-lg font-medium text-ink-100">{title}</h3>
      {body && <p className="max-w-md text-sm text-ink-300">{body}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm" role="alert">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-300" />
      <div className="flex-1 text-red-200">{message}</div>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function Notice({ tone = "info", children, className }: { tone?: "info" | "warn"; children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-lg border p-3 text-xs leading-relaxed",
        tone === "warn" ? "border-warn/30 bg-warn/[0.06] text-amber-100" : "border-white/[0.08] bg-white/[0.03] text-ink-200",
        className,
      )}
    >
      {tone === "warn" ? <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0 text-amber-300" /> : <Info className="mt-px h-3.5 w-3.5 shrink-0 text-ink-300" />}
      <div>{children}</div>
    </div>
  );
}

export function Tip({ text, children }: { text: string; children?: React.ReactNode }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        aria-describedby={id}
        className="text-ink-400 hover:text-ink-200"
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        {children ?? <Info className="h-3.5 w-3.5" />}
      </button>
      {open && (
        <span id={id} role="tooltip" className="panel absolute bottom-full left-1/2 z-50 mb-2 w-64 -translate-x-1/2 rounded-xl p-2.5 text-xs leading-relaxed text-ink-100">
          {text}
        </span>
      )}
    </span>
  );
}

export function Dialog({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; footer?: React.ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} className="panel rise w-full max-w-md rounded-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3.5">
          <h2 className="font-display text-base font-medium">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="text-ink-400 hover:text-ink-100">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-4 text-sm text-ink-200">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-white/[0.06] px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function Metric({
  label,
  value,
  sub,
  kind,
  delta,
  deltaGood,
  className,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  kind?: EvidenceKind;
  delta?: string | null;
  deltaGood?: boolean | null;
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border border-white/[0.07] bg-white/[0.025] p-3.5", className)}>
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 text-xs leading-tight text-ink-300">{label}</span>
        {kind && <Evidence kind={kind} className="-mr-1 -mt-0.5 scale-90" />}
      </div>
      <div className="num font-display mt-2 text-[22px] font-medium tracking-tight text-ink-100">{value}</div>
      <div className="mt-0.5 flex items-center gap-2 text-xs">
        {delta && <span className={cn("num", deltaGood === null || deltaGood === undefined ? "text-ink-300" : deltaGood ? "text-ok" : "text-red-300")}>{delta}</span>}
        {sub && <span className="text-ink-400">{sub}</span>}
      </div>
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, className }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; className?: string }) {
  return (
    <div role="radiogroup" className={cn("inline-flex rounded-lg border border-white/10 bg-white/[0.03] p-0.5", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn("rounded-md px-3 py-1 text-xs transition-colors", value === o.value ? "bg-ink-100 text-ink-950" : "text-ink-300 hover:text-ink-100")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function DemoBanner() {
  return (
    <div className="flex items-center gap-2 border-b border-warn/30 bg-warn/[0.08] px-4 py-1.5 text-xs font-medium text-warn">
      <AlertTriangle className="h-3.5 w-3.5" />
      Demo scenario: illustrative market data, not verified live conditions.
    </div>
  );
}
