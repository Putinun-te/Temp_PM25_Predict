import type { NextConfig } from "next";

// Static export: the build is plain HTML, CSS and JavaScript in out/, so the same
// files run on Azure App Service, Azure Blob static website and GitHub Pages.
// GitHub Pages serves the site under /<repository>, set through NEXT_PUBLIC_BASE_PATH.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const config: NextConfig = {
  output: "export",
  basePath,
  // Each page becomes <name>/index.html, which every static host serves at /<name>/.
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default config;
