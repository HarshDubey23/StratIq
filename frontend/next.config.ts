import type { NextConfig } from "next";

const API_URL = (process.env.API_URL || "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: true },
  // Simulations and market loads can take tens of seconds; don't cut the proxied request at 30 s.
  experimental: { proxyTimeout: 120_000 },
  // The browser only ever talks to this origin; /api is proxied to FastAPI so the
  // session cookie is first-party (no cross-site cookie issues in production).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
