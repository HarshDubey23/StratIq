"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Logo } from "@/components/brand";
import { Button, Field, Input, NumberInput, Segmented } from "@/components/ui";
import { api } from "@/lib/api";

export default function Onboarding() {
  const router = useRouter();
  const [plan, setPlan] = useState<"new" | "existing">("new");
  const [industry, setIndustry] = useState("");
  const [city, setCity] = useState("");
  const [budget, setBudget] = useState<number | null>(null);
  const [goal, setGoal] = useState<"profit" | "low_risk" | "growth" | "break_even">("profit");
  const [busy, setBusy] = useState(false);

  async function save(skip = false) {
    setBusy(true);
    const prefs = skip
      ? { onboarding: "skipped" }
      : { onboarding: "done", plan_type: plan, industry, city, budget, default_goal: goal };
    await api("/auth/preferences", { method: "PUT", json: { preferences: prefs } }).catch(() => undefined);
    const q = new URLSearchParams();
    if (!skip) {
      if (industry) q.set("category", industry);
      if (city) q.set("place", city);
      q.set("objective", plan === "new" ? "start_new" : "improve_existing");
      q.set("goal", goal);
      if (budget) q.set("budget", String(budget));
    }
    router.push(skip ? "/app" : `/app/projects/new?${q.toString()}`);
  }

  return (
    <div className="grid-bg flex min-h-screen items-center justify-center bg-ink-950 px-4 py-10">
      <div className="w-full max-w-lg">
        <div className="mb-8 flex justify-center">
          <Logo href="/app" />
        </div>
        <div className="space-y-5 rounded-xl border border-black/[0.07] bg-black/[0.025] p-6">
          <div>
            <h1 className="text-lg font-semibold">A few quick questions</h1>
            <p className="mt-1 text-sm text-ink-300">They pre-fill your first analysis. Everything is optional.</p>
          </div>
          <Field label="Are you planning a new business or growing an existing one?">
            <Segmented value={plan} onChange={setPlan} options={[{ value: "new", label: "New business" }, { value: "existing", label: "Existing business" }]} />
          </Field>
          <Field label="What kind of business?" hint="Anything, e.g. “gym”, “pizza outlet”, “dental clinic”, “cloud kitchen”.">
            <Input value={industry} onChange={(e) => setIndustry(e.target.value)} placeholder="Type any business" />
          </Field>
          <Field label="Which city or area?">
            <Input value={city} onChange={(e) => setCity(e.target.value)} placeholder="e.g. Indiranagar, Bengaluru" />
          </Field>
          <Field label="Approximate investment budget">
            <NumberInput value={budget} onChange={setBudget} prefix="₹" allowEmpty placeholder="e.g. 1500000" />
          </Field>
          <Field label="What matters most?">
            <Segmented
              value={goal}
              onChange={setGoal}
              options={[
                { value: "profit", label: "Profit" },
                { value: "low_risk", label: "Low risk" },
                { value: "break_even", label: "Fast payback" },
                { value: "growth", label: "Growth" },
              ]}
            />
          </Field>
          <div className="flex justify-between pt-2">
            <Button variant="ghost" onClick={() => save(true)} disabled={busy}>Skip for now</Button>
            <Button variant="primary" onClick={() => save(false)} loading={busy}>Continue</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
