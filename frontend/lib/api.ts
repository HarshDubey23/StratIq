export class ApiError extends Error {
  status: number;
  fields: { field: string; message: string }[];
  data: unknown;
  constructor(status: number, message: string, fields: { field: string; message: string }[] = [], data: unknown = null) {
    super(message);
    this.status = status;
    this.fields = fields;
    this.data = data;
  }
}

function messageFrom(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && "message" in d) return String((d as { message: unknown }).message);
  }
  if (status === 502) return "A data provider is not responding right now. Please try again in a moment.";
  if (status >= 500) return "The server had a problem. Please try again.";
  return `Request failed (${status})`;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, {
      ...rest,
      credentials: "include",
      headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...(headers || {}) },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Cannot reach the StrataIQ server. Check your connection.");
  }
  if (res.status === 204) return undefined as T;
  let body: unknown = null;
  const text = await res.text();
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const fields = body && typeof body === "object" && "errors" in body ? ((body as { errors: { field: string; message: string }[] }).errors ?? []) : [];
    if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      // Clear a stale/expired cookie first so the middleware does not bounce us back.
      await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" }).catch(() => undefined);
      window.location.href = `/sign-in?next=${next}`;
    }
    throw new ApiError(res.status, messageFrom(body, res.status), fields, body);
  }
  return body as T;
}
