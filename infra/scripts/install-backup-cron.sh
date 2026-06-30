#!/usr/bin/env bash
#
# install-backup-cron.sh — register the nightly off-site backup as a cron job.
#
# Installs a root crontab entry that runs backup-to-r2.sh every night at the
# configured time and appends output to a log file. Idempotent: re-running
# replaces the previous IoTAPS backup entry rather than duplicating it.
#
# Usage:
#   sudo ./install-backup-cron.sh            # default 03:15 daily
#   sudo BACKUP_CRON_SCHEDULE="0 4 * * *" ./install-backup-cron.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup-to-r2.sh"
LOG_FILE="${BACKUP_CRON_LOG:-/var/log/iotaps-backup.log}"
SCHEDULE="${BACKUP_CRON_SCHEDULE:-15 3 * * *}"   # 03:15 every day (server time)
MARKER="# iotaps-nightly-backup"

[[ -f "${BACKUP_SCRIPT}" ]] || { echo "ERROR: ${BACKUP_SCRIPT} not found" >&2; exit 1; }
chmod +x "${BACKUP_SCRIPT}"

ENTRY="${SCHEDULE} /usr/bin/env bash ${BACKUP_SCRIPT} >> ${LOG_FILE} 2>&1 ${MARKER}"

# Pull current crontab (empty if none), strip any previous iotaps entry, append.
( crontab -l 2>/dev/null | grep -v -F "${MARKER}" || true; echo "${ENTRY}" ) | crontab -

echo "Installed nightly backup cron:"
echo "  schedule : ${SCHEDULE}"
echo "  script   : ${BACKUP_SCRIPT}"
echo "  log      : ${LOG_FILE}"
echo
echo "Current crontab:"
crontab -l | grep -F "${MARKER}" || true
echo
echo "Tip: run a one-off now to verify config:  bash ${BACKUP_SCRIPT}"
