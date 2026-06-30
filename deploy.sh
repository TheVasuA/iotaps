#!/usr/bin/env bash
#
# IoTAPS backend deploy / update script (run on the VPS).
#
# Automates the flow documented in firmware/deploy.txt:
#   pull -> build -> (re)start services -> wait for DB -> migrate -> health check
#
# It is idempotent and safe to re-run: it NEVER passes `-v` to `docker compose
# down`, so named volumes (postgres_data, redis_data, mosquitto_data) are
# preserved. The frontend is hosted on Cloudflare Pages, so the web build is
# OFF by default (enable with --web if this VPS also serves ./web/dist via the
# nginx container).
#
# Usage:
#   ./deploy.sh                 # build changed images + restart + migrate
#   ./deploy.sh --pull          # git pull origin main first
#   ./deploy.sh --no-build      # restart only (config/env change)
#   ./deploy.sh --web           # also `npm install && npm run build` in ./web
#   ./deploy.sh --no-migrate    # skip alembic migrations
#   ./deploy.sh --pull --web    # full update including frontend
#
# Flags can be combined in any order.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (override via environment if needed)
# ---------------------------------------------------------------------------
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
GIT_BRANCH="${GIT_BRANCH:-main}"
API_CONTAINER="${API_CONTAINER:-iotaps-api}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/api/v1/health}"
# App services rebuilt/restarted on an update (DB/redis/mosquitto are left
# running so a deploy never interrupts persistence or device connections).
APP_SERVICES=(fastapi-api fastapi-ws workers nginx)

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------
DO_PULL=0
DO_BUILD=1
DO_WEB=0
DO_MIGRATE=1

for arg in "$@"; do
  case "$arg" in
    --pull)       DO_PULL=1 ;;
    --no-build)   DO_BUILD=0 ;;
    --web)        DO_WEB=1 ;;
    --no-migrate) DO_MIGRATE=0 ;;
    -h|--help)
      grep -E '^#( |$)' "${BASH_SOURCE[0]}" | sed -E 's/^# ?//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (use --help)" >&2
      exit 2
      ;;
  esac
done

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

cd "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
log "Pre-flight checks"
command -v docker >/dev/null 2>&1 || die "docker is not installed."
docker compose version >/dev/null 2>&1 || die "the 'docker compose' v2 plugin is required."
[ -f .env ] || die ".env not found in $PROJECT_DIR. Copy .env.example to .env and fill it in."
[ -f docker-compose.yml ] || die "docker-compose.yml not found in $PROJECT_DIR."
echo "OK: docker, compose plugin, .env, compose file present."

# ---------------------------------------------------------------------------
# 1. Pull latest source
# ---------------------------------------------------------------------------
if [ "$DO_PULL" -eq 1 ]; then
  log "Pulling latest code (origin/$GIT_BRANCH)"
  git pull origin "$GIT_BRANCH"
fi

# ---------------------------------------------------------------------------
# 2. Build frontend (optional — only if this VPS serves the SPA)
# ---------------------------------------------------------------------------
if [ "$DO_WEB" -eq 1 ]; then
  log "Building frontend (web/dist)"
  command -v npm >/dev/null 2>&1 || die "npm is required for --web but was not found."
  ( cd web && npm install && npm run build )
fi

# ---------------------------------------------------------------------------
# 3. Build backend images
# ---------------------------------------------------------------------------
if [ "$DO_BUILD" -eq 1 ]; then
  log "Building backend images"
  docker compose build fastapi-api
fi

# ---------------------------------------------------------------------------
# 4. Start / restart services
#    `up -d` only recreates what changed; --no-deps avoids bouncing DB/redis.
# ---------------------------------------------------------------------------
log "Starting infrastructure (postgres, redis, mosquitto)"
docker compose up -d postgres redis mosquitto

log "Waiting for PostgreSQL to become healthy"
for i in $(seq 1 30); do
  status="$(docker inspect -f '{{.State.Health.Status}}' iotaps-postgres 2>/dev/null || echo 'starting')"
  if [ "$status" = "healthy" ]; then
    echo "PostgreSQL is healthy."
    break
  fi
  if [ "$i" -eq 30 ]; then
    die "PostgreSQL did not become healthy in time. Check: docker compose logs postgres"
  fi
  sleep 2
done

log "Restarting application services: ${APP_SERVICES[*]}"
docker compose up -d --no-deps "${APP_SERVICES[@]}"

# ---------------------------------------------------------------------------
# 5. Database migrations
# ---------------------------------------------------------------------------
if [ "$DO_MIGRATE" -eq 1 ]; then
  log "Running database migrations (alembic upgrade head)"
  # Give the freshly (re)started API container a moment to be up.
  sleep 5
  docker exec -w /srv/app "$API_CONTAINER" alembic upgrade head
fi

# ---------------------------------------------------------------------------
# 6. Health smoke test
# ---------------------------------------------------------------------------
log "Health check: $HEALTH_URL"
health_ok=0
for i in $(seq 1 15); do
  if body="$(curl -fsS "$HEALTH_URL" 2>/dev/null)"; then
    echo "$body"
    case "$body" in
      *'"status":"ok"'*)       health_ok=1; break ;;
      *'"status":"degraded"'*) warn "API is up but reports DEGRADED dependencies."; health_ok=1; break ;;
    esac
  fi
  sleep 2
done
[ "$health_ok" -eq 1 ] || warn "Health endpoint did not return OK. Check: docker compose logs fastapi-api"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
log "Deployment complete — current service status"
docker compose ps

cat <<'EOF'

Next steps / reminders:
  - Logs:            docker compose logs -f fastapi-api
  - Register MQTT node (first deploy only): see firmware/deploy.txt PART 4.
  - Backup DB before risky changes:
        docker exec iotaps-postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup_$(date +%Y%m%d).sql
  - Do NOT run `docker compose down -v` — the -v flag deletes your data volumes.
EOF
