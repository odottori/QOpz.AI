import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function normalizeBasePath(raw: string | undefined): string {
  const trimmed = (raw ?? "/").trim();
  if (!trimmed || trimmed === "/") return "/";
  const withLeading = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  return withLeading.endsWith("/") ? withLeading : `${withLeading}/`;
}

const basePath = normalizeBasePath(process.env.VITE_BASE_PATH);
const apiProxy = {
  "/opz": "http://127.0.0.1:8765",
  "/health": "http://127.0.0.1:8765",
  "/guide": "http://127.0.0.1:8765",
};

export default defineConfig({
  base: basePath,
  plugins: [react()],
  server: {
    port: 8173,
    strictPort: true,
    // Dev proxy: /opz/* and /health to local FastAPI.
    proxy: apiProxy,
  },
  preview: { port: 8173, strictPort: true, proxy: apiProxy },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
