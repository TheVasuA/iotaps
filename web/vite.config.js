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
        //
        // FUNCTION form on purpose. The object form matches module IDs and is
        // unreliable for package sub-entries and nested copies: `clsx` matched
        // one copy but a nested one still landed in vendor-grid, and
        // `react/jsx-runtime` matched nothing at all, so it was co-located with
        // framer-motion and the entry's jsx() call dragged vendor-motion
        // (~115KB) onto every page including the marketing surface. Matching
        // resolved paths here is deterministic and makes the failure mode
        // obvious in the chunk map if it ever regresses.
        manualChunks(id) {
          // App/project code stays with its importer.
          if (!id.includes("node_modules")) return undefined;
          const p = id.replaceAll("\\", "/");

          // Package root = first path segment under node_modules/. Matching on
          // the segment (not a substring) keeps `react-redux` from satisfying a
          // `react` rule and `@dnd-kit/core` from colliding with other cores.
          const pkg = p.split("node_modules/").pop().split("/").slice(0, p.split("node_modules/").pop().startsWith("@") ? 2 : 1).join("/");

          // Tiny shared utilities first: `cn()` pulls clsx into the entry graph,
          // so if clsx is left to Rollup it gets co-located with whichever large
          // vendor needs it and that whole chunk lands on every page.
          if (pkg === "clsx" || pkg === "tailwind-merge" || pkg === "class-variance-authority") {
            return "vendor-utils";
          }
          // react/jsx-runtime is its own entry point under the react package.
          if (pkg === "react" || pkg === "react-dom" || pkg === "react-router" || pkg === "react-router-dom") {
            return "vendor-react";
          }
          if (pkg === "@reduxjs/toolkit" || pkg === "react-redux" || pkg === "redux") return "vendor-redux";
          if (pkg === "framer-motion" || pkg === "motion") return "vendor-motion";
          if (pkg === "echarts" || pkg === "echarts-for-react") return "vendor-charts";
          if (pkg === "@xyflow/react") return "vendor-flow";
          if (pkg === "react-grid-layout" || pkg === "react-resizable") return "vendor-grid";
          if (pkg === "@dnd-kit/core" || pkg === "@dnd-kit/sortable" || pkg === "@dnd-kit/utilities") {
            return "vendor-dnd";
          }
          return undefined;
        },
      },
    },
  },
});
