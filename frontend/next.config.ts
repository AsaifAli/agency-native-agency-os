import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Keep constrained CI/cloud build workers from exhausting process limits.
  experimental: { cpus: 1 },
  // Keep browser source maps private in production builds.
  productionBrowserSourceMaps: false,
};

export default nextConfig;
