# IoTAPS — Deployment Guide

Complete, step-by-step deployment for the IoTAPS platform.

**Architecture**

```
Frontend  → Cloudflare Pages           (auto-deploys on git push)
Backend   → Contabo VPS (Docker)       API · WebSocket · workers · MQTT · Postgres · Redis
DNS       → Cloudflare                 iotaps.com → Pages, api/mqtt.iotaps.com → VPS
Backups   → Cloudflare R2 (off-site)   nightly pg_dump
Vault     → MongoDB Atlas (optional)   live mirror of identity data
```

**Containers** (all `restart: always`, self-healing): `iotaps-nginx`, `iotaps-api`,
`iotaps-ws`, `iotaps-workers`, `iotaps-mosquitto`, `iotaps-postgres`, `iotaps-redis`.

> Conventions: VPS IP `94.136.184.17`, project path `~/projects/iotaps`, repo
> `github.com/TheVasuA/iotaps`. Replace with your own where needed.

---

## 0. Prerequisites

- A Contabo (or any Ubuntu 22.04/24.04) VPS with root SSH access.
- A domain on Cloudflare (`iotaps.com`).
- A GitHub repo with the code.
- Locally: your filled-in `.env` (copy from `.env.example`).

---

## PART 1 — Frontend (Cloudflare Pages)

Do this first; it builds independently of the VPS.

1. https://dash.cloudflare.com → **Pages** → **Create a project** → connect the GitHub repo.
2. Build settings:
   - Framework preset: **None**
   - Build command: `cd web && npm install && npm run build`
   - Build output directory: `web/dist`
   - Root directory: `/`
3. Environment variable:
   - `VITE_GOOGLE_CLIENT_ID = <your Google OAuth client id>`
4. **Save and Deploy**. Note the URL (e.g. `https://iotaps-web.pages.dev`).

---

## PART 2 — DNS (Cloudflare)

Cloudflare → `iotaps.com` → **DNS** → add:

| Type  | Name | Content               | Proxy            |
|-------|------|-----------------------|------------------|
| CNAME | @    | iotaps-web.pages.dev  | Proxied (orange) |
| CNAME | www  | iotaps-web.pages.dev  | Proxied (orange) |
| A     | api  | 94.136.184.17         | **DNS only (grey)** |
| A     | mqtt | 94.136.184.17         | **DNS only (grey)** |

Then Pages → **Custom domains** → add `iotaps.com` and `www.iotaps.com`.

> `api` and `mqtt` **must be grey-cloud (DNS only)**. WebSocket and MQTT traffic
> must hit the VPS directly without Cloudflare proxy buffering. Keep their TTL at
> **60s** so failover (Part 7) is fast.

---

## PART 3 — VPS setup (fresh server)

SSH in: `ssh root@94.136.184.17`

### 3.1 System + Docker
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git awscli

# Docker
curl -fsSL https://get.docker.com | sh
sudo systemctl enable docker && sudo systemctl start docker
sudo apt install -y docker-compose-plugin
```

### 3.2 Firewall
```bash
sudo ufw allow 22/tcp     # SSH
sudo ufw allow 80/tcp     # HTTP
sudo ufw allow 443/tcp    # HTTPS
sudo ufw allow 1883/tcp   # MQTT
sudo ufw allow 9001/tcp   # MQTT over WebSocket
sudo ufw --force enable
sudo ufw status
```

### 3.3 Clone the project
```bash
sudo mkdir -p /projects && sudo chown $USER:$USER /projects
cd /projects
git clone https://github.com/TheVasuA/iotaps.git
cd iotaps
```

### 3.4 Configure environment
```bash
cp .env.example .env
nano .env
```
Fill in at minimum (see PART 8 for the full reference):
- `POSTGRES_PASSWORD`, `DATABASE_URL` (same password), `REDIS_PASSWORD`, `REDIS_URL`
- `JWT_SECRET` (long random string)
- `SUPERADMIN_EMAIL`, `SUPERADMIN_PASSWORD` (auto-seeded on first start)
- `PUBLIC_BASE_URL=https://api.iotaps.com`
- `CORS_ALLOW_ORIGINS=https://iotaps.com,https://www.iotaps.com`
- Optional: Razorpay, SMTP, R2 backups, MongoDB vault (later parts).

> Generate strong secrets: `openssl rand -base64 36`

### 3.5 Build and start
```bash
docker compose build --no-cache
docker compose up -d
```
> The API image now installs `postgresql-client-16` for the backup/restore
> feature, so the first build pulls a bit more — this is expected.

### 3.6 Run database migrations
```bash
sleep 15
docker exec -w /srv/app iotaps-api alembic upgrade head
```

### 3.7 Verify
```bash
docker compose ps          # all services Up
curl -s http://localhost:8000/api/v1/health    # {"status":"ok"}
```
On startup the app auto-seeds the **super admin** and the **default template
catalog** (7 starter templates) — no manual step needed.

---

## PART 4 — Post-deploy: register the MQTT node

The platform needs at least one MQTT node registered so devices can be assigned.

```bash
# get an admin token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<SUPERADMIN_EMAIL>","password":"<SUPERADMIN_PASSWORD>"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# register the in-stack broker
curl -X POST http://localhost:8000/api/v1/admin/mqtt-nodes \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"ip":"mosquitto","port":1883,"capacity":10000}'
```

Verify from anywhere:
```powershell
Test-NetConnection mqtt.iotaps.com -Port 1883     # PowerShell
```

---

## PART 5 — Nginx + SSL/TLS

Nginx runs **inside Docker** (`iotaps-nginx`), serves on ports 80/443, proxies
`/api/` → `fastapi-api:8000` and `/ws` → `fastapi-ws:8001`, and reads certs from
the mounted folder `./infra/nginx/certs` (→ `/etc/nginx/certs` in the container).
Config lives in `infra/nginx/nginx.conf` + `infra/nginx/conf.d/iotaps.conf`.

### 5.0 Choose how TLS is terminated

| Option | `api`/`mqtt` DNS | TLS terminated by | WebSocket | Use when |
|---|---|---|---|---|
| **A. Cloudflare proxy** | orange (Proxied) | Cloudflare | works, but ~100s idle cap | simplest; short-lived WS |
| **B. Direct + VPS cert** ✅ | **grey (DNS only)** | nginx on the VPS | unrestricted, long-lived | **recommended** for 4000+ live dashboards |

This platform keeps thousands of long-lived WebSocket connections, so **Option B
is recommended** (matches PART 2's grey-cloud records). Steps 5.1–5.4 set it up.

> Option A alternative: keep `api` orange-cloud, set Cloudflare SSL mode to
> **Full (strict)**, and install a **Cloudflare Origin Certificate** into
> `infra/nginx/certs` (15-year cert, no renewal). Then do steps 5.3–5.4 only.

### 5.1 Get a Let's Encrypt certificate (DNS-01 via Cloudflare — recommended)

DNS-01 needs no open port and renews with zero downtime — ideal since the domain
is already on Cloudflare and you have an API token (PART 7).

```bash
sudo apt install -y certbot python3-certbot-dns-cloudflare

# Cloudflare API token with Zone:DNS:Edit on the iotaps zone
sudo mkdir -p /root/.secrets
printf 'dns_cloudflare_api_token = %s\n' "<CLOUDFLARE_API_TOKEN>" \
  | sudo tee /root/.secrets/cloudflare.ini >/dev/null
sudo chmod 600 /root/.secrets/cloudflare.ini

sudo certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /root/.secrets/cloudflare.ini \
  -d api.iotaps.com \
  --agree-tos -m you@example.com --no-eff-email
```

**Fallback — standalone** (no Cloudflare token; brief nginx downtime):
```bash
cd /projects/iotaps
docker compose stop nginx                       # free port 80
sudo certbot certonly --standalone -d api.iotaps.com \
  --agree-tos -m you@example.com --no-eff-email
docker compose start nginx
```

### 5.2 Install the cert into the nginx mount
```bash
cd /projects/iotaps
sudo mkdir -p infra/nginx/certs
sudo cp /etc/letsencrypt/live/api.iotaps.com/fullchain.pem infra/nginx/certs/
sudo cp /etc/letsencrypt/live/api.iotaps.com/privkey.pem  infra/nginx/certs/
sudo chmod 644 infra/nginx/certs/*.pem
```

### 5.3 Add the HTTPS server block

Edit `infra/nginx/conf.d/iotaps.conf` and add this block (alongside the existing
`api.iotaps.com` port-80 block — change that one to redirect to HTTPS):

```nginx
# Redirect HTTP -> HTTPS for the API host
server {
    listen 80;
    server_name api.iotaps.com;
    location = /healthz { access_log off; default_type text/plain; return 200 "ok\n"; }
    location / { return 301 https://$host$request_uri; }
}

# HTTPS API + WebSocket (TLS terminated on the VPS — grey-cloud DNS)
server {
    listen 443 ssl;
    http2 on;
    server_name api.iotaps.com;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_session_cache   shared:SSL:10m;

    client_max_body_size 25m;

    location = /healthz { access_log off; default_type text/plain; return 200 "ok\n"; }

    location /api/ {
        proxy_pass http://iotaps_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /ws {
        proxy_pass http://iotaps_ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location / { return 404; }
}
```

### 5.4 Test and reload
```bash
docker exec iotaps-nginx nginx -t        # validate config
docker compose restart nginx             # apply
curl -I https://api.iotaps.com/healthz   # expect HTTP/2 200
```
Then set `PUBLIC_BASE_URL=https://api.iotaps.com` in `.env` and point the
frontend at it (`VITE_API_BASE_URL=https://api.iotaps.com/api/v1`).

### 5.5 Auto-renewal

Let's Encrypt certs last 90 days. The certbot systemd timer renews automatically;
add a **deploy hook** so renewed certs are copied into the mount and nginx reloads:

```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/iotaps.sh >/dev/null <<'EOF'
#!/usr/bin/env bash
cp /etc/letsencrypt/live/api.iotaps.com/fullchain.pem /projects/iotaps/infra/nginx/certs/
cp /etc/letsencrypt/live/api.iotaps.com/privkey.pem  /projects/iotaps/infra/nginx/certs/
docker exec iotaps-nginx nginx -s reload
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/iotaps.sh

sudo certbot renew --dry-run     # verify renewal works end-to-end
```
> DNS-01 renews with no downtime. If you used the **standalone** fallback, also
> add pre/post hooks to free port 80 during renewal:
> `sudo certbot renew --pre-hook "docker compose -f /projects/iotaps/docker-compose.yml stop nginx" --post-hook "docker compose -f /projects/iotaps/docker-compose.yml start nginx"`

---

## PART 6 — Off-site backups (Cloudflare R2)  ▸ strongly recommended

Protects all data against a full server loss. Details: `infra/scripts/README.md`.

1. Cloudflare → **R2** → create bucket `iotaps-backups`.
2. R2 → **Manage API Tokens** → Object Read & Write token; note the Access Key,
   Secret, and S3 endpoint `https://<accountid>.r2.cloudflarestorage.com`.
3. Add to `.env`: `BACKUP_R2_BUCKET`, `BACKUP_R2_ENDPOINT`,
   `BACKUP_R2_ACCESS_KEY_ID`, `BACKUP_R2_SECRET_ACCESS_KEY`.
4. Enable:
```bash
cd /projects/iotaps
bash infra/scripts/backup-to-r2.sh          # one-off test → uploads a .dump
sudo bash infra/scripts/install-backup-cron.sh   # nightly at 03:15
tail -n 50 /var/log/iotaps-backup.log
```

---

## PART 7 — Standby failover  ▸ optional

A second cheap VPS, deployed identically and left idle, lets you recover in minutes.

1. Repeat PART 3 on a second VPS (same repo, **same `.env`**), then `docker compose up -d`.
2. For automatic DNS failover, set in `.env`: `CLOUDFLARE_API_TOKEN` (Zone:DNS:Edit),
   `CLOUDFLARE_ZONE_ID`, `FAILOVER_DNS_RECORDS=api.iotaps.com,mqtt.iotaps.com`.
3. When the primary dies, on the standby:
```bash
cd /projects/iotaps
bash infra/scripts/promote-standby.sh
```
Restores the latest R2 backup, starts the stack, and repoints DNS. Devices
reconnect automatically (~1–2 min).

---

## PART 8 — Optional integrations

### 8.1 SMTP email notifications
Set in `.env`: `SMTP_HOST`, `SMTP_PORT` (587 STARTTLS / 465 SSL), `SMTP_USERNAME`,
`SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`.
Sends device-registered/deleted, payment success/failed, subscription-expiring
("low days"), and rule-alert emails. Empty `SMTP_HOST` = disabled (no-op).

> Gmail requires an **App Password**, not your account password.

### 8.2 MongoDB identity vault (off-VPS mirror)
Set `MONGODB_URI` (a free Atlas M0 cluster is ample) + `MONGODB_DB`. Mirrors users
(with password **hashes**), device tokens, and devices to an independent store.
Empty `MONGODB_URI` = disabled. Trigger an on-demand sync from Admin → Disaster
Recovery → "Sync identity vault now".

### 8.3 Razorpay (payments)
Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`. Point the
Razorpay webhook to `https://api.iotaps.com/api/v1/billing/webhook`.

---

## PART 9 — Ongoing updates

### Frontend
Just `git push` — Cloudflare Pages rebuilds and deploys automatically.

### Backend (safe rolling update)
```bash
cd /projects/iotaps

# 1. ALWAYS back up first
docker exec -t iotaps-postgres pg_dump -U iotaps -d iotaps -Fc -f /tmp/pre.dump
docker cp iotaps-postgres:/tmp/pre.dump ./backups/

# 2. pull + rebuild app image only (DB/Redis/MQTT untouched)
git pull origin main
docker compose build fastapi-api

# 3. restart app containers only
docker compose up -d --no-deps fastapi-api fastapi-ws workers nginx

# 4. migrations (additive — never drops data)
docker exec -w /srv/app iotaps-api alembic upgrade head

# 5. verify
curl -s http://localhost:8000/api/v1/health
```
If you changed the **Dockerfile** (e.g. dependencies), use
`docker compose build --no-cache fastapi-api` for step 2.

> ⚠️ **Never** run `docker compose down -v`. The `-v` deletes the data volumes
> (Postgres, Redis, MQTT). Use `docker compose down` (no `-v`).

---

## PART 10 — Verification checklist

- [ ] `docker compose ps` → all 7 services **Up**
- [ ] `curl http://localhost:8000/api/v1/health` → `{"status":"ok"}`
- [ ] `https://iotaps.com` loads and you can log in as the super admin
- [ ] `Test-NetConnection mqtt.iotaps.com -Port 1883` succeeds
- [ ] A device connects and telemetry shows on a dashboard
- [ ] Nightly backup uploaded to R2 (`tail /var/log/iotaps-backup.log`)

---

## PART 11 — Troubleshooting

| Symptom | Check |
|---|---|
| API 5xx / won't start | `docker logs iotaps-api --tail 100` |
| DB connection errors | `docker logs iotaps-postgres --tail 50`; verify `DATABASE_URL` password matches `POSTGRES_PASSWORD` |
| Devices can't connect | `docker logs iotaps-mosquitto --tail 50`; firewall ports 1883/9001; `mqtt` DNS grey-cloud |
| WebSocket fails | `api` DNS must be **grey-cloud**; check TLS cert (PART 5) |
| Redis OOM / crash | `docker stats`; Redis is capped at 512MB with LRU eviction by design |
| Disk filling up | `df -h /`; tune data-retention; old backups auto-prune after `BACKUP_RETENTION_DAYS` |
| SSH keeps asking password | server may have `PermitRootLogin prohibit-password`; fix via Contabo VNC console |

### Recovery decision tree
```
Container crashed, VPS up?   → docker compose up -d        (self-heals anyway)
VPS up but DB corrupted?     → bash infra/scripts/restore-from-r2.sh
VPS dead / unreachable?      → bash infra/scripts/promote-standby.sh   (on the spare)
No standby?                  → new VPS (PART 3) → restore-from-r2.sh
```

A live in-product version of this runbook (with flowchart) is in
**Admin → Disaster Recovery**, and a command cheat-sheet in
**Admin → Command Reference**.

---

## DANGER ZONE (destructive)

```bash
# Full wipe & redeploy — DESTROYS ALL DATA. Only on a throwaway/fresh setup.
docker compose down -v --rmi all
docker system prune -af --volumes
```
Always confirm an off-site backup exists first.
