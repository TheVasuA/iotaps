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
    // echarts (vendor-charts) is ~1MB and is intentionally isolated in its own
    // long-cached chunk, loaded only on chart routes. Raise the warning limit
    // so an already-optimal split doesn't spam the build log.
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // Split large, rarely-changing vendor libraries into their own cached
        // chunks. This keeps per-route chunks (e.g. DashboardPage, RuleEditor)
        // small, lets heavy deps be shared across routes instead of duplicated,
        // and improves long-term caching since vendor code changes infrequently.
        manualChunks: {
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          "vendor-redux": ["@reduxjs/toolkit", "react-redux"],
          "vendor-charts": ["echarts", "echarts-for-react"],
          "vendor-flow": ["@xyflow/react"],
          "vendor-grid": ["react-grid-layout", "react-resizable"],
          "vendor-dnd": ["@dnd-kit/core", "@dnd-kit/sortable", "@dnd-kit/utilities"],
          "vendor-motion": ["framer-motion"],
        },
      },
    },
  },
});
