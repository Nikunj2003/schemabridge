import type { NextConfig } from "next";

/**
 * In production the platform routes /api/* to the Python service, so Next never
 * sees those requests. Locally there is no such router, hence this proxy: it
 * keeps the browser on one origin, which is what the session cookie and the
 * same-origin check both assume.
 */
const nextConfig: NextConfig = {
  // The dev server writes agent instruction files into the repo otherwise.
  agentRules: false,

  // The repository root holds its own lockfile for deployment tooling, so the
  // web app has to name its own root or the bundler guesses the wrong one.
  turbopack: { root: import.meta.dirname },

  async rewrites() {
    const backend = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
