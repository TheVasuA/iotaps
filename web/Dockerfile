# IoTAPS frontend image — builds the Vite SPA and serves it with Nginx.
#
# Multi-stage so the VPS needs ONLY Docker: no Node, no npm, and no separate
# frontend deploy step. `docker compose build nginx` compiles web/src into
# static assets and bakes them into the final Nginx image, replacing the old
# workflow that required `npm run build` on the host to populate ./web/dist.
#
# Nginx config is NOT baked in; docker-compose.yml mounts infra/nginx/* so
# routing changes only need a container restart, not an image rebuild.

# ---------------------------------------------------------------------------
# Stage 1 — build the SPA
# ---------------------------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies first for layer caching: this layer is only invalidated
# when package.json / package-lock.json change, not on every source edit.
# `npm ci` installs exactly the versions pinned in package-lock.json so the
# image build is reproducible and matches local builds.
COPY package.json package-lock.json ./
RUN npm ci

# Copy sources and build. Vite reads .env.production for `mode=production`,
# which is where VITE_API_BASE_URL / VITE_WS_URL live. Those are relative
# (same-origin) so the bundle works on any hostname it is served from.
COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — serve the built assets
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine

# Only the compiled output ships; node_modules and sources stay in stage 1.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
