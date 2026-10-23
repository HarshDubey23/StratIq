/**
 * Same-origin proxy to the FastAPI backend.
 *
 * A route handler (instead of a config rewrite) lets long requests — live market loads and
 * simulations can take a minute — run up to the platform's function limit, and keeps the
 * session cookie first-party on every host (Vercel, Render, Docker).
 */
import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const API = (process.env.API_URL || "http://localhost:8000").replace(/\/$/, "");
const HOP = ["host", "connection", "content-length", "transfer-encoding", "keep-alive", "upgrade", "accept-encoding"];

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const target = `${API}/api/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const headers = new Headers(req.headers);
  HOP.forEach((h) => headers.delete(h));
  headers.set("x-forwarded-host", req.headers.get("host") || "");
  headers.set("x-forwarded-proto", req.nextUrl.protocol.replace(":", ""));
  const init: RequestInit = { method: req.method, headers, redirect: "manual", cache: "no-store" };
  if (req.method !== "GET" && req.method !== "HEAD") init.body = await req.arrayBuffer();
  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch {
    return Response.json({ detail: "The StrataIQ API is waking up or unreachable. Try again in a few seconds." }, { status: 503 });
  }
  const out = new Headers();
  upstream.headers.forEach((v, k) => {
    if (!["content-encoding", "content-length", "transfer-encoding", "connection", "set-cookie"].includes(k)) out.set(k, v);
  });
  const cookies = (upstream.headers as Headers & { getSetCookie?: () => string[] }).getSetCookie?.() ?? [];
  cookies.forEach((c) => out.append("set-cookie", c));
  const body = upstream.status === 204 || upstream.status === 304 ? null : upstream.body;
  return new Response(body, { status: upstream.status, headers: out });
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
