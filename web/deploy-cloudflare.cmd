@echo off
REM Deploy IoTAPS frontend to Cloudflare Pages (Windows)
REM Prerequisites: npm install -g wrangler && wrangler login
REM First-time: wrangler pages project create iotaps-web --production-branch main

echo ==> Building frontend for production...
call npm run build
if errorlevel 1 (
    echo BUILD FAILED
    exit /b 1
)

echo ==> Deploying to Cloudflare Pages...
npx wrangler pages deploy dist --project-name iotaps-web

echo ==> Done! Frontend deployed to Cloudflare Pages.
echo     Set env vars (VITE_GOOGLE_CLIENT_ID) in the Cloudflare dashboard.
