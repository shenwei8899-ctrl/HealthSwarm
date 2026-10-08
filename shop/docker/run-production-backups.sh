#!/bin/sh
set -u

interval="${BACKUP_INTERVAL_SECONDS:-86400}"
while true; do
    if ! sh /opt/healthflow/backup-postgresql.sh; then
        echo "PostgreSQL backup failed" >&2
    fi
    sleep "$interval"
done
