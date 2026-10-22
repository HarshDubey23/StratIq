"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSession } from "@/components/AppShell";
import { Button, Card, CardHeader, Dialog, ErrorState, Field, Input, Notice } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

export default function Settings() {
  const { user } = useSession();
  const router = useRouter();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [del, setDel] = useState(false);

  async function change(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      await api("/auth/password", { method: "POST", json: { current_password: cur, new_password: next } });
      setMsg("Password updated.");
      setCur("");
      setNext("");
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Could not update password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-3xl space-y-5 px-4 py-8 md:px-8">
      <h1 className="text-xl font-semibold">Settings</h1>
      <Card>
        <CardHeader title="Account" />
        <div className="space-y-1 p-4 text-sm">
          <div><span className="text-ink-400">Email: </span>{user?.email}</div>
          <div><span className="text-ink-400">Name: </span>{user?.name || "—"}</div>
        </div>
      </Card>
      <Card>
        <CardHeader title="Change password" />
        <form onSubmit={change} className="space-y-3 p-4">
          {err && <ErrorState message={err} />}
          {msg && <Notice>{msg}</Notice>}
          <Field label="Current password"><Input type="password" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" /></Field>
          <Field label="New password" hint="At least 8 characters."><Input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" /></Field>
          <Button type="submit" loading={busy} disabled={next.length < 8 || !cur}>Update password</Button>
        </form>
      </Card>
      <Card>
        <CardHeader title="Your data" />
        <div className="space-y-3 p-4 text-sm text-ink-300">
          <p>Your business inputs, scenarios, competitors you add and actual outcomes are stored in your account and are only visible to you, unless you create a share link for a report.</p>
          <p>Market data is fetched from public sources (OpenStreetMap, WorldPop) and cached briefly to respect their usage policies. No personal data about individuals is collected; contributor names from OpenStreetMap are discarded.</p>
          <Button variant="danger" onClick={() => setDel(true)}>Delete my account and all data</Button>
        </div>
      </Card>
      <Dialog
        open={del}
        onClose={() => setDel(false)}
        title="Delete account?"
        footer={<><Button onClick={() => setDel(false)}>Cancel</Button><Button variant="danger" onClick={async () => { await api("/auth/account", { method: "DELETE" }); router.push("/"); }}>Delete everything</Button></>}
      >
        This permanently deletes your account, all projects, scenarios, runs and reports, and revokes share links.
      </Dialog>
    </main>
  );
}
