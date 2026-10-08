#!/bin/sh
set -eu

mkdir -p /backups
stamp="$(date +%Y%m%d_%H%M%S)"
target="/backups/healthflow_${stamp}.dump.gz"
tmp="${target}.tmp"

PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump --format=custom --no-owner --no-privileges \
    -h "${POSTGRES_HOST:-db}" -p "${POSTGRES_PORT:-5432}" \
    -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip -9 > "$tmp"
mv "$tmp" "$target"
find /backups -type f -name 'healthflow_*.dump.gz' -mtime "+${BACKUP_RETENTION_DAYS:-30}" -delete
echo "PostgreSQL backup completed: $target"
