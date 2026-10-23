import { Suspense } from "react";
import { QuickStart } from "@/components/QuickStart";
import { Wizard } from "./Wizard";

export default function Page() {
  return (
    <Suspense>
      <div className="mx-auto w-full max-w-5xl px-4 pt-8 md:px-10">
        <QuickStart autoFocus />
        <div className="mt-8 flex items-center gap-3 text-xs text-ink-500">
          <span className="h-px flex-1 bg-white/[0.07]" /> or set everything yourself, step by step <span className="h-px flex-1 bg-white/[0.07]" />
        </div>
      </div>
      <Wizard />
    </Suspense>
  );
}
