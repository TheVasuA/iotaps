#!/usr/bin/env bash
#
# deploy.sh — safe rolling update of the IoTAPS backend on a live server.
#
# Encodes the ordering that a naive "pull, build, up" sequence gets wrong. Each
# step below exists because skipping it produced a real outage during the first
# deployment:
#
#   1. Back up BEFORE anything else. A failed migration with no dump is
#      unrecoverable.
#   2. Run migrations from a ONE-OFF container built on the new image, before
#      the long-running containers restart. The app seeds the super admin and
#      the template catalog during startup and swallows failures as warnings, so
#      booting it against an un-migrated database leaves the platform silently
#      unseeded.
#   3. Recreate only the app containers (--no-deps). Postgres, Redis and
#      Mosquitto keep their data and connections.
#   4. Restart nginx LAST. It resolves upstream container IPs once at startup,
#      so recreating the API behind it serves 502 until nginx is restarted.
#   5. Verify through nginx, not just on the API port — that is the path real
#      traffic takes.
#
# Data volumes are never touched. `docker compose down` is not used at all.
#
# Usage:
#   bash infra/scripts/deploy.sh            # pull + build + migrate + restart
#   SKIP_WEB=1  bash infra/scripts/deploy.sh   # backend only, skip SPA rebuild
#   SKIP_PULL=1 bash infra/scripts/deploy.sh   # deploy the working tree as-is
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_DIR}"

ENV_FILE="${IOTAPS_ENV_FILE:-${PROJECT_DIR}/.env}"
PG_CONTAINER="${BACKUP_POSTGRES_CONTAINER:-iotaps-postgres}"
PG_USER="$(grep -E '^POSTGRES_USER=' "${ENV_FILE}" | cut -d= -f2- || echo iotaps)"
PG_DB="$(grep -E '^POSTGRES_DB=' "${ENV_FILE}" | cut -d= -f2- || echo iotaps)"
BACKUP_DIR="${BACKUP_LOCAL_DIR:-${PROJECT_DIR}/backups}"

# Host port the web container publishes on. Must match docker-compose.yml.
WEB_PORT="${IOTAPS_WEB_PORT:-8088}"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31mFAILED: %s\033[0m\n' "$1" >&2; exit 1; }

# --- 1. backup ---------------------------------------------------------------
step "Backing up ${PG_DB} before touching anything"
mkdir -p "${BACKUP_DIR}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DUMP="pre-deploy-${STAMP}.dump"
docker exec -t "${PG_CONTAINER}" \
  pg_dump -U "${PG_USER}" -d "${PG_DB}" -Fc -f "/tmp/${DUMP}" \
  || fail "pg_dump failed — aborting before any change"
docker cp "${PG_CONTAINER}:/tmp/${DUMP}" "${BACKUP_DIR}/${DUMP}"
docker exec "${PG_CONTAINER}" rm -f "/tmp/${DUMP}"
echo "wrote ${BACKUP_DIR}/${DUMP}"

# --- 2. fetch code -----------------------------------------------------------
if [[ "${SKIP_PULL:-0}" != "1" ]]; then
  step "Pulling latest main"
  git pull origin main
else
  step "Skipping git pull (SKIP_PULL=1) — deploying working tree"
fi

# --- 3. build ----------------------------------------------------------------
step "Building the API image"
docker compose build fastapi-api || fail "API image build failed"

if [[ "${SKIP_WEB:-0}" != "1" ]]; then
  # web/.env.production is read by Vite at BUILD time, so frontend/env changes
  # only ship via a rebuild — restarting the container is not enough.
  step "Building the web image (SPA bundle is baked in)"
  docker compose build nginx || fail "web image build failed"
fi

# --- 4. migrate on the new image, before the app restarts --------------------
step "Running migrations in a one-off container"
docker compose run --rm --no-deps --workdir /srv/app fastapi-api \
  alembic upgrade head || fail "migrations failed — stack still on old image"

# --- 5. roll the app containers ---------------------------------------------
step "Recreating app containers (data services untouched)"
docker compose up -d --no-deps fastapi-api fastapi-ws workers \
  || fail "app containers failed to start"

# --- 6. nginx last, to pick up new upstream IPs ------------------------------
step "Restarting nginx so it re-resolves upstream addresses"
docker compose up -d --no-deps nginx
docker compose restart nginx

# --- 7. verify ---------------------------------------------------------------
step "Verifying"
sleep 15

HEALTH="$(curl -fsS "http://127.0.0.1:${WEB_PORT}/api/v1/health" 2>/dev/null || true)"
case "${HEALTH}" in
  *'"status":"ok"'*) echo "api via nginx: ${HEALTH}" ;;
  *) fail "health check through nginx failed: ${HEALTH:-<no response>}
   check: docker logs iotaps-api --tail 50" ;;
esac

SPA="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${WEB_PORT}/")"
[[ "${SPA}" == "200" ]] || fail "SPA did not return 200 (got ${SPA})"
echo "spa: ${SPA}"

docker compose ps --format '{{.Name}} | {{.Status}}'

printf '\n\033[1;32mDeploy complete.\033[0m Rollback dump: %s\n' \
  "${BACKUP_DIR}/${DUMP}"
