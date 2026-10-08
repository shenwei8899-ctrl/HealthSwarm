#!/bin/sh
set -u

interval="${V5_JOB_INTERVAL_SECONDS:-60}"

while true; do
    if php scripts/run-v5-jobs.php; then
        touch /tmp/healthflow-scheduler-ok
    else
        echo "HealthFlow scheduler cycle failed" >&2
    fi
    sleep "$interval"
done
