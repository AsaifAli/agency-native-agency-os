import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Keep browser source maps private in production builds.
  productionBrowserSourceMaps: false,
};

export default nextConfig;
