#!/usr/bin/env bash
#
# restore-from-r2.sh — pull a database backup from Cloudflare R2 and restore it
# into the running Postgres container.
#
# Usage:
#   ./restore-from-r2.sh            # restore the LATEST backup in the bucket
#   ./restore-from-r2.sh db/iotaps_20260630_030000.dump   # restore a specific key
#
# DESTRUCTIVE: runs `pg_restore --clean --if-exists`, which drops and recreates
# objects from the dump. Intended for disaster recovery / standby promotion.
#
# Reads the same .env config as backup-to-r2.sh.
#
set -euo pipefail

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

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker not found"
command -v aws    >/dev/null 2>&1 || die "aws CLI not found"
: "${BACKUP_R2_BUCKET:?BACKUP_R2_BUCKET not set}"
: "${BACKUP_R2_ENDPOINT:?BACKUP_R2_ENDPOINT not set}"
: "${BACKUP_R2_ACCESS_KEY_ID:?BACKUP_R2_ACCESS_KEY_ID not set}"
: "${BACKUP_R2_SECRET_ACCESS_KEY:?BACKUP_R2_SECRET_ACCESS_KEY not set}"

export AWS_ACCESS_KEY_ID="${BACKUP_R2_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${BACKUP_R2_SECRET_ACCESS_KEY}"
export AWS_DEFAULT_REGION="auto"

REMOTE_KEY="${1:-}"
if [[ -z "${REMOTE_KEY}" ]]; then
  log "No key given — finding the latest backup under db/"
  REMOTE_KEY="$(aws s3api list-objects-v2 \
    --bucket "${BACKUP_R2_BUCKET}" --prefix "db/" \
    --endpoint-url "${BACKUP_R2_ENDPOINT}" \
    --query 'sort_by(Contents,&LastModified)[-1].Key' \
    --output text 2>/dev/null)"
  [[ -n "${REMOTE_KEY}" && "${REMOTE_KEY}" != "None" ]] || die "no backups found in bucket"
fi
log "Restoring from s3://${BACKUP_R2_BUCKET}/${REMOTE_KEY}"

docker ps --format '{{.Names}}' | grep -qx "${PG_CONTAINER}" \
  || die "postgres container '${PG_CONTAINER}' is not running"

TMP="$(mktemp --suffix=.dump)"
trap 'rm -f "${TMP}"' EXIT

aws s3 cp "s3://${BACKUP_R2_BUCKET}/${REMOTE_KEY}" "${TMP}" \
  --endpoint-url "${BACKUP_R2_ENDPOINT}" --only-show-errors \
  || die "download failed"
log "Downloaded $(wc -c < "${TMP}" | tr -d ' ') bytes"

read -r -p "This OVERWRITES the '${PG_DB}' database. Type 'RESTORE' to proceed: " confirm
[[ "${confirm}" == "RESTORE" ]] || die "aborted by operator"

log "Restoring into ${PG_CONTAINER}:${PG_DB} ..."
docker exec -i "${PG_CONTAINER}" \
  pg_restore --clean --if-exists --no-owner --no-privileges \
  -U "${PG_USER}" -d "${PG_DB}" < "${TMP}" \
  || log "pg_restore reported non-zero (often ignorable --clean notices); review above"

log "Restore complete. Run migrations next: docker exec -w /srv/app iotaps-api alembic upgrade head"
