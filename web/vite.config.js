import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Vite config for the IoTAPS SPA.
// - `@` alias points at `src/` (shadcn/ui convention).
// - dev server proxies /api and /ws to the FastAPI backend so the SPA can run
//   against a local backend without CORS during development.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: process.env.VITE_WS_PROXY_TARGET || "ws://localhost:8000",
        ws: true,
      },
    },
  },
  build: {
    // Nginx serves the production build from web/dist (see docker-compose.yml).
    outDir: "dist",
    sourcemap: false,
  },
});
