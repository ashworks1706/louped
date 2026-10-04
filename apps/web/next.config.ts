import type { NextConfig } from "next";

// A static export: `louped serve` serves out/ next to the API, so there is no Node server to run.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
};

export default nextConfig;
