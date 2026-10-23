import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: true },
  // The browser only ever talks to this origin; /api/* is proxied to FastAPI by app/api/[...path]/route.ts,
  // so the session cookie is first-party and long simulations are not cut off by a rewrite timeout.
};

export default nextConfig;
