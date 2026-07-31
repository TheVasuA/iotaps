# IoTaps — Environment & Deployment Guide

---

## 🎯 Two `.env` Files

| File | What it controls | Where to edit |
|------|-----------------|---------------|
| **`.env`** (project root) | Backend: DB, Redis, MQTT, JWT, email, payments | On the server / your machine |
| **`web/.env` / `web/.env.production`** | Frontend: API URL, WebSocket URL, Google OAuth | In `web/` folder |

---

## 1. Root `.env` — Backend (Docker services)

All 7 Docker containers read from this file.

### 🔧 What MUST be changed before deployment

| Variable | Local dev value | Production value |
|----------|----------------|------------------|
| `POSTGRES_PASSWORD` | `change_me_postgres` | Strong random string |
| `DATABASE_URL` | `postgresql+asyncpg://iotaps:change_me_postgres@postgres:5432/iotaps` | Same format, use real password |
| `REDIS_PASSWORD` | `change_me_redis` | Strong random string |
| `REDIS_URL` | `redis://:change_me_redis@redis:6379/0` | Same format, use real password |
| `JWT_SECRET` | `change_me_jwt_secret_use_a_long_random_string` | `openssl rand -base64 36` |
| `SUPERADMIN_EMAIL` | `admin@example.com` | Your email |
| `SUPERADMIN_PASSWORD` | `change_me_strong_password` | Strong password |

### 🔄 Local vs Production — what's different

| Variable | **Local** | **Production** |
|----------|-----------|----------------|
| `APP_ENV` | `development` | `production` |
| `APP_DEBUG` | `true` | `false` |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | `https://api.yourdomain.com` |
| `CORS_ALLOW_ORIGINS` | `*` | `https://yourdomain.com,https://www.yourdomain.com` |
| `MQTT_HOST` | `mosquitto` | `mosquitto` (Docker internal) |
| Passwords | `change_me_*` placeholders | Strong random values |

### 🔌 Optional — leave empty to disable

| Feature | Variables to set |
|---------|-----------------|
| Google OAuth | `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` |
| Payments (Razorpay) | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` |
| Email (SMTP) | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` |
| MongoDB identity vault | `MONGODB_URI` |
| Off-site backups (R2) | `BACKUP_R2_BUCKET`, `BACKUP_R2_ENDPOINT`, etc. |

---

## 2. Frontend `.env` — Web App

### 📁 Local dev → `web/.env` (copy from `web/.env.example`)

```ini
VITE_API_BASE_URL=/api/v1                              # Relative path → Vite proxies to localhost:8000
VITE_API_PROXY_TARGET=http://localhost:8000             # Backend dev server
VITE_WS_PROXY_TARGET=ws://localhost:8000                # WebSocket dev server
VITE_GOOGLE_CLIENT_ID=                                  # Leave blank unless testing Google login
```

### 🌐 Production build → `web/.env.production`

```ini
VITE_API_BASE_URL=https://api.iotaps.com/api/v1         # Change to your domain
VITE_WS_URL=wss://api.iotaps.com/ws                      # Change to your domain
VITE_GOOGLE_CLIENT_ID=622587244689-ok0kqi83d23u2esdv5pk6t0alen4jro2.apps.googleusercontent.com
```

**After editing**, rebuild the frontend:
```bash
cd d:\iotaps\web
npm run build
docker compose up -d nginx     # reload Nginx with new files
```

---

## 3. Nginx — Where to change for deployment

| Setting | **Local (already done)** | **Production** |
|---------|-------------------------|----------------|
| File | `infra/nginx/conf.d/iotaps.conf` | Same file |
| Server name | `server_name localhost _;` | `server_name yourdomain.com www.yourdomain.com;` |
| SSL | None (port 80 only) | Add port 443 block with Let's Encrypt certs |
| Reload | — | `docker exec iotaps-nginx nginx -t && docker compose restart nginx` |

---

## 4. 🖥️ Current Local Setup — Access Points

The platform is running now at **`d:\iotaps`**. Here's everything:

### 🌐 Web URLs

| What | URL | Notes |
|------|-----|-------|
| **Main SPA** | http://localhost:80/ | Full React dashboard (login, devices, dashboards) |
| **API Health** | http://localhost/api/v1/health | Returns `{"status":"degraded","service":"iotaps-api"}` |
| **Swagger Docs** | http://localhost/api/v1/docs | Interactive API documentation |
| **OpenAPI Spec** | http://localhost/api/v1/openapi.json | Raw JSON schema |

### 🔧 Direct Service Ports (bypass Nginx)

| Service | Internal URL | Purpose |
|---------|-------------|---------|
| FastAPI API | `http://localhost:8000` | REST API (gunicorn) |
| FastAPI WS | `http://localhost:8001` | WebSocket (dedicated workers) |
| MQTT Broker | `localhost:1883` | Device MQTT connection |
| MQTT over WS | `localhost:9001` | MQTT WebSocket bridge |
| PostgreSQL | `localhost:5432` | Database (TimescaleDB) |
| Redis | `localhost:6379` | Cache & queue |

### 🐳 Docker Status

| Container | Status | Health |
|-----------|--------|--------|
| `iotaps-nginx` | ✅ Running | — |
| `iotaps-api` | ✅ Running | — |
| `iotaps-ws` | ✅ Running | — |
| `iotaps-workers` | ✅ Running | — |
| `iotaps-mosquitto` | ✅ Running | — |
| `iotaps-postgres` | ✅ Running | ✅ Healthy |
| `iotaps-redis` | ✅ Running | ✅ Healthy |

### ⚙️ Quick Commands

```bash
# Start everything
docker compose up -d

# Stop everything
docker compose stop

# View logs
docker compose logs -f

# Rebuild backend after code changes
docker compose build fastapi-api
docker compose up -d --no-deps fastapi-api fastapi-ws workers

# Rebuild frontend after changes
cd web && npm run build
docker compose up -d nginx
```

---

## 5. 📦 Deployment Checklist

### Local Dev (Windows — `d:\iotaps`)

```
Step 1:  copy .env.example .env                                    # create backend .env
Step 2:  copy web\.env.example web\.env                            # create frontend .env
Step 3:  cd web && npm install && npm run build                    # build SPA → web/dist/
Step 4:  docker compose build                                      # build Docker images
Step 5:  docker compose up -d                                      # start all 7 services
Step 6:  docker exec -w /srv/app iotaps-api alembic upgrade head   # run DB migrations
Step 7:  Open http://localhost:80/ in browser                       # ✅
```

### Production (Linux VPS — Contabo, DigitalOcean, etc.)

```
Step 1:  SSH into VPS
Step 2:  git clone https://github.com/TheVasuA/iotaps.git /projects/iotaps
Step 3:  cp .env.example .env
Step 4:  nano .env
         → CHANGE: POSTGRES_PASSWORD, DATABASE_URL, REDIS_PASSWORD,
                    REDIS_URL, JWT_SECRET, SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD
         → SET:    PUBLIC_BASE_URL=https://api.yourdomain.com
         → SET:    CORS_ALLOW_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
         → OPTIONAL: SMTP, Razorpay, R2 backup credentials

Step 5:  For Cloudflare Pages: set VITE_* vars in Cloudflare dashboard → git push
         For Docker frontend:  edit web/.env.production → npm run build

Step 6:  docker compose build --no-cache
Step 7:  docker compose up -d
Step 8:  docker exec -w /srv/app iotaps-api alembic upgrade head
Step 9:  Set up SSL certificates (Let's Encrypt) — see DEPLOY.md PART 5
Step 10: Register MQTT node — see DEPLOY.md PART 4
Step 11: Verify → curl http://localhost:8000/api/v1/health
```

---

## 6. 📋 File Summary

| File | Edit for local? | Edit for production? |
|------|----------------|---------------------|
| **`.env`** (root) | ✅ Once (copy from `.env.example`) | ✅ Yes — change all secrets & URLs |
| **`web/.env`** | ✅ Once (copy from `web/.env.example`) | ❌ Not used in production |
| **`web/.env.production`** | ❌ Not used in local dev | ✅ Yes — set your domain & Google OAuth |
| **`infra/nginx/conf.d/iotaps.conf`** | ✅ Already done for localhost | ✅ Yes — change domain & add SSL |
| **`docker-compose.yml`** | ❌ No changes needed | ❌ No changes needed |
| **`app/` (backend code)** | ❌ No changes needed | ❌ No changes needed |
| **`web/src/` (frontend code)** | ❌ No changes needed | ❌ No changes needed |