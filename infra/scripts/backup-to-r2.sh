#!/usr/bin/env bash
#
# backup-to-r2.sh — nightly off-site database backup for IoTAPS.
#
# Dumps the running Postgres/TimescaleDB container with pg_dump (custom format),
# uploads the dump to Cloudflare R2 (S3-compatible) via the AWS CLI, prunes old
# local + remote copies, and logs the result. Designed to be run from cron.
#
# WHY off-site: a backup that lives only on the same VPS dies with the VPS. R2
# (or any S3 bucket) keeps a copy on independent infrastructure so a dead disk
# or a destroyed server does not lose customer data.
#
# Requirements on the VPS:
#   - docker (the iotaps-postgres container running)
#   - aws CLI v2  (apt install awscli  OR  the official bundle)
#
# Configuration: reads /projects/iotaps/.env (override with IOTAPS_ENV_FILE).
# Required keys (see .env.example "Off-site backups (R2/S3)"):
#   POSTGRES_USER, POSTGRES_DB
#   BACKUP_R2_BUCKET, BACKUP_R2_ENDPOINT
#   BACKUP_R2_ACCESS_KEY_ID, BACKUP_R2_SECRET_ACCESS_KEY
# Optional:
#   BACKUP_LOCAL_DIR        (default /projects/iotaps/backups)
#   BACKUP_RETENTION_DAYS   (default 14)
#   BACKUP_POSTGRES_CONTAINER (default iotaps-postgres)
#   BACKUP_HEALTHCHECK_URL  (pinged on success — e.g. healthchecks.io)
#
set -euo pipefail

# --- locate and load config --------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${IOTAPS_ENV_FILE:-${PROJECT_DIR}/.env}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a; source "${ENV_FILE}"; set +a
fi

PG_CONTAINER="${BACKUP_POSTGRES_CONTAINER:-iotaps-postgres}"
PG_USER="${POSTGRES_USER:-iotaps}"
PG_DB="${POSTGRES_DB:-iotaps}"
LOCAL_DIR="${BACKUP_LOCAL_DIR:-${PROJECT_DIR}/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

# --- preflight ----------------------------------------------------------------
command -v docker >/dev/null 2>&1 || die "docker not found"
command -v aws    >/dev/null 2>&1 || die "aws CLI not found (apt install awscli)"
docker ps --format '{{.Names}}' | grep -qx "${PG_CONTAINER}" \
  || die "postgres container '${PG_CONTAINER}' is not running"

: "${BACKUP_R2_BUCKET:?BACKUP_R2_BUCKET not set}"
: "${BACKUP_R2_ENDPOINT:?BACKUP_R2_ENDPOINT not set}"
: "${BACKUP_R2_ACCESS_KEY_ID:?BACKUP_R2_ACCESS_KEY_ID not set}"
: "${BACKUP_R2_SECRET_ACCESS_KEY:?BACKUP_R2_SECRET_ACCESS_KEY not set}"

mkdir -p "${LOCAL_DIR}"

STAMP="$(date -u '+%Y%m%d_%H%M%S')"
FILENAME="iotaps_${STAMP}.dump"
LOCAL_PATH="${LOCAL_DIR}/${FILENAME}"
REMOTE_KEY="db/${FILENAME}"

# Credentials for the AWS CLI (scoped to this process only).
export AWS_ACCESS_KEY_ID="${BACKUP_R2_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${BACKUP_R2_SECRET_ACCESS_KEY}"
export AWS_DEFAULT_REGION="auto"   # R2 ignores region but the CLI wants one

# --- 1. dump ------------------------------------------------------------------
log "Dumping ${PG_DB} from ${PG_CONTAINER} -> ${LOCAL_PATH}"
# -Fc = compressed custom format (restorable with pg_restore).
docker exec -t "${PG_CONTAINER}" \
  pg_dump -U "${PG_USER}" -d "${PG_DB}" -Fc \
  > "${LOCAL_PATH}" \
  || die "pg_dump failed"

SIZE="$(wc -c < "${LOCAL_PATH}" | tr -d ' ')"
[[ "${SIZE}" -gt 0 ]] || die "dump is empty"
log "Dump complete (${SIZE} bytes)"

# --- 2. upload to R2 ----------------------------------------------------------
log "Uploading to s3://${BACKUP_R2_BUCKET}/${REMOTE_KEY}"
aws s3 cp "${LOCAL_PATH}" "s3://${BACKUP_R2_BUCKET}/${REMOTE_KEY}" \
  --endpoint-url "${BACKUP_R2_ENDPOINT}" \
  --only-show-errors \
  || die "upload to R2 failed"
log "Upload complete"

# --- 3. prune local copies older than retention ------------------------------
log "Pruning local dumps older than ${RETENTION_DAYS} days"
find "${LOCAL_DIR}" -name 'iotaps_*.dump' -type f -mtime "+${RETENTION_DAYS}" -delete || true

# --- 4. prune remote copies older than retention -----------------------------
# R2 lifecycle rules are the robust way to expire objects, but we also prune
# here so it works without bucket-level config.
CUTOFF_EPOCH="$(date -u -d "-${RETENTION_DAYS} days" '+%s' 2>/dev/null || echo 0)"
if [[ "${CUTOFF_EPOCH}" -gt 0 ]]; then
  log "Pruning remote dumps older than ${RETENTION_DAYS} days"
  aws s3api list-objects-v2 \
    --bucket "${BACKUP_R2_BUCKET}" \
    --prefix "db/" \
    --endpoint-url "${BACKUP_R2_ENDPOINT}" \
    --query 'Contents[].{Key:Key,LastModified:LastModified}' \
    --output text 2>/dev/null | while read -r key last_modified; do
      [[ -z "${key}" ]] && continue
      obj_epoch="$(date -u -d "${last_modified}" '+%s' 2>/dev/null || echo 0)"
      if [[ "${obj_epoch}" -gt 0 && "${obj_epoch}" -lt "${CUTOFF_EPOCH}" ]]; then
        log "  deleting old remote ${key}"
        aws s3 rm "s3://${BACKUP_R2_BUCKET}/${key}" \
          --endpoint-url "${BACKUP_R2_ENDPOINT}" --only-show-errors || true
      fi
    done
fi

# --- 5. success ping (optional dead-man's switch) ----------------------------
if [[ -n "${BACKUP_HEALTHCHECK_URL:-}" ]]; then
  curl -fsS -m 10 "${BACKUP_HEALTHCHECK_URL}" >/dev/null 2>&1 || true
fi

log "Backup OK: ${REMOTE_KEY} (${SIZE} bytes)"
