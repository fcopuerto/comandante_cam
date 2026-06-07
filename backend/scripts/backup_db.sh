#!/usr/bin/env bash
# Daily PostgreSQL backup. Intended to run inside the backend container.
# Keep last 7 daily backups.

set -euo pipefail

BACKUP_DIR="${BACKUP_PATH:-/data/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="nvr_backup_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

pg_dump "$DATABASE_URL_SYNC" | gzip > "${BACKUP_DIR}/${FILENAME}"

echo "Backup written: ${BACKUP_DIR}/${FILENAME}"

# Keep last 7, delete older
ls -t "${BACKUP_DIR}"/nvr_backup_*.sql.gz | tail -n +8 | xargs -r rm --
echo "Old backups cleaned up."
