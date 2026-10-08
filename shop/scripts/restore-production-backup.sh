#!/bin/sh
set -eu

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
    echo "Usage: sh scripts/restore-production-backup.sh database/backups/healthflow_YYYYMMDD_HHMMSS.dump.gz" >&2
    exit 1
fi

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"

gzip -dc "$1" | docker compose -f docker-compose.production.yml exec -T \
    -e PGPASSWORD="$POSTGRES_PASSWORD" db pg_restore --clean --if-exists \
    --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB" -
