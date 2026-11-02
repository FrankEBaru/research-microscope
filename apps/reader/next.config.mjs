/** @type {import('next').NextConfig} */
const flag = process.env.RRM_ARTIFACTS_V2;
const config = { output: "export", images: { unoptimized: true }, reactStrictMode: true, devIndicators: false };
if (flag != null && flag !== "") config.env = { NEXT_PUBLIC_RRM_ARTIFACTS_V2: flag };
export default config;
