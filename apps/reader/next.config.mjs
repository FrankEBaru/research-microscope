/** @type {import('next').NextConfig} */
import { createHash } from "node:crypto";

const flag = process.env.RRM_ARTIFACTS_V2;
// Next's filesystem cache does not include NEXT_PUBLIC_* in its key, so a page
// compiled with the previous demo token keeps sending it and the server
// answers 401. The hash is not the token.
const publicKeys = [
  "NEXT_PUBLIC_BURST_URL",
  "NEXT_PUBLIC_READER_URL",
  "NEXT_PUBLIC_RRM_DEMO_TOKEN",
  "NEXT_PUBLIC_RRM_OFFLINE",
  "NEXT_PUBLIC_RRM_FEATURES",
  "NEXT_PUBLIC_RRM_PANORAMA_TIMEOUT_MS",
];
const envTag = createHash("sha256")
  .update(publicKeys.map((key) => `${key}=${process.env[key] ?? ""}`).join("\0"))
  .digest("hex")
  .slice(0, 16);

const config = {
  output: "export",
  images: { unoptimized: true },
  reactStrictMode: true,
  devIndicators: false,
  webpack(webpackConfig) {
    const cache = webpackConfig.cache;
    if (cache && typeof cache === "object") {
      cache.version = `${cache.version || ""}|rrm-public-env:${envTag}`;
    }
    return webpackConfig;
  },
};
if (flag != null && flag !== "") config.env = { NEXT_PUBLIC_RRM_ARTIFACTS_V2: flag };
export default config;
