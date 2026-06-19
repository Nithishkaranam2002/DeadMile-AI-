import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  transpilePackages: ["@tremor/react"],
  outputFileTracingRoot: path.join(__dirname, "../../"),
};

export default nextConfig;
