#!/usr/bin/env bash
#
# promote-standby.sh — turn a warm-standby VPS into the live primary in one
# command, after the primary VPS has failed.
#
# What it does, in order:
#   1. Pulls the latest application code.
#   2. Brings up Postgres (and Redis) only.
#   3. Restores the latest database backup from R2 (restore-from-r2.sh).
#   4. Brings up the full stack and runs DB migrations.
#   5. (optional) Repoints Cloudflare DNS api/mqtt A-records to THIS server's IP
#      so devices reconnect here automatically.
#
# Run this ON THE STANDBY VPS. It assumes the repo is cloned and .env is filled
# in (same secrets as primary), and that the standby normally sits idle.
#
# Required .env keys: the R2/* keys (see backup-to-r2.sh).
# Optional (for automatic DNS failover):
#   CLOUDFLARE_API_TOKEN   (token with Zone:DNS:Edit on the iotaps zone)
#   CLOUDFLARE_ZONE_ID
#   FAILOVER_DNS_RECORDS   (comma list, e.g. "api.iotaps.com,mqtt.iotaps.com")
#   FAILOVER_PUBLIC_IP     (this server's public IP; auto-detected if unset)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${IOTAPS_ENV_FILE:-${PROJECT_DIR}/.env}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a; source "${ENV_FILE}"; set +a
fi

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

cd "${PROJECT_DIR}"
command -v docker >/dev/null 2>&1 || die "docker not found"

echo
log "=== IoTAPS standby promotion ==="
log "Project dir: ${PROJECT_DIR}"
read -r -p "Promote THIS server to primary? Type 'PROMOTE' to continue: " confirm
[[ "${confirm}" == "PROMOTE" ]] || die "aborted by operator"

# --- 1. latest code ----------------------------------------------------------
log "Pulling latest code"
git pull --ff-only origin main || log "git pull skipped/failed — continuing with current checkout"

# --- 2. data services first --------------------------------------------------
log "Starting postgres + redis"
docker compose up -d postgres redis
log "Waiting for postgres to be healthy"
for i in $(seq 1 30); do
  if docker exec "${BACKUP_POSTGRES_CONTAINER:-iotaps-postgres}" \
       pg_isready -U "${POSTGRES_USER:-iotaps}" -d "${POSTGRES_DB:-iotaps}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
  [[ "${i}" -eq 30 ]] && die "postgres did not become ready"
done

# --- 3. restore latest backup from R2 ----------------------------------------
log "Restoring latest backup from R2"
# Auto-confirm the restore prompt inside restore-from-r2.sh.
echo "RESTORE" | "${SCRIPT_DIR}/restore-from-r2.sh"

# --- 4. full stack + migrations ----------------------------------------------
log "Bringing up the full stack"
docker compose up -d
sleep 10
log "Running database migrations"
docker exec -w /srv/app "${API_CONTAINER:-iotaps-api}" alembic upgrade head || \
  log "migration step reported an error — check manually"

# --- 5. DNS failover (optional) ----------------------------------------------
if [[ -n "${CLOUDFLARE_API_TOKEN:-}" && -n "${CLOUDFLARE_ZONE_ID:-}" && -n "${FAILOVER_DNS_RECORDS:-}" ]]; then
  IP="${FAILOVER_PUBLIC_IP:-$(curl -fsS -m 10 https://api.ipify.org || true)}"
  [[ -n "${IP}" ]] || die "could not determine public IP for DNS failover"
  log "Repointing DNS records to ${IP}"
  IFS=',' read -ra RECORDS <<< "${FAILOVER_DNS_RECORDS}"
  for name in "${RECORDS[@]}"; do
    name="$(echo "${name}" | xargs)"  # trim
    [[ -z "${name}" ]] && continue
    rec_id="$(curl -fsS -m 15 \
      -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
      "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records?type=A&name=${name}" \
      | python3 -c "import sys,json; r=json.load(sys.stdin)['result']; print(r[0]['id'] if r else '')" 2>/dev/null || true)"
    if [[ -z "${rec_id}" ]]; then
      log "  ${name}: no existing A record — skipping (create it manually)"
      continue
    fi
    curl -fsS -m 15 -X PUT \
      -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
      -H "Content-Type: application/json" \
      "https://api.cloudflare.com/client/v4/zones/${CLOUDFLARE_ZONE_ID}/dns_records/${rec_id}" \
      --data "{\"type\":\"A\",\"name\":\"${name}\",\"content\":\"${IP}\",\"ttl\":60,\"proxied\":false}" \
      >/dev/null && log "  ${name} -> ${IP} (TTL 60)" || log "  ${name}: DNS update failed"
  done
else
  log "DNS failover skipped (CLOUDFLARE_* not configured)."
  log "Manually point api/mqtt A-records to this server's IP in Cloudflare."
fi

echo
log "=== Promotion complete. Verify: curl -s http://localhost:8000/api/v1/health ==="
