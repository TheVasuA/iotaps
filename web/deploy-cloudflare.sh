#!/usr/bin/env bash
# Deploy IoTAPS frontend to Cloudflare Pages.
#
# Prerequisites:
#   npm install -g wrangler
#   wrangler login
#
# Usage:
#   cd web && bash deploy-cloudflare.sh
#
# First-time setup:
#   wrangler pages project create iotaps-web --production-branch main

set -euo pipefail

echo "==> Building frontend for production..."
npm run build

echo "==> Deploying to Cloudflare Pages..."
npx wrangler pages deploy dist --project-name iotaps-web

echo "==> Done! Frontend deployed to Cloudflare Pages."
echo "    Set env vars (VITE_GOOGLE_CLIENT_ID) in the Cloudflare dashboard."
