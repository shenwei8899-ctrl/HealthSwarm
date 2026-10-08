#!/bin/sh
set -u

interval="${MONITOR_INTERVAL_SECONDS:-60}"
failures=0
while true; do
    if curl -kfsS --max-time 10 https://nginx/healthz >/dev/null; then
        failures=0
    else
        failures=$((failures + 1))
        if [ "$failures" -ge 3 ] && [ -n "${ALERT_WEBHOOK_URL:-}" ]; then
            curl -fsS --max-time 10 -H 'Content-Type: application/json' \
                -d '{"event":"healthflow_unhealthy","service":"nginx","message":"连续3次健康检查失败"}' \
                "$ALERT_WEBHOOK_URL" >/dev/null || true
        fi
    fi
    sleep "$interval"
done
