import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8173,
    strictPort: true,
    // Dev proxy: /opz/* e /health → FastAPI locale
    proxy: {
      "/opz": "http://localhost:8765",
      "/health": "http://localhost:8765",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
