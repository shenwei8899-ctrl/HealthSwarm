#!/usr/bin/env bash
# 复用现有健康隔离拓扑；此脚本只清理由自身创建的独立项目。
set -euo pipefail

cd "$(dirname "$0")/.."
project=health-agent-ci
if [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$project")" ]; then
  echo "health-agent-ci 已存在容器，拒绝接管或清理" >&2
  exit 1
fi

export COMPOSE_PROJECT_NAME=$project
export YUXI_STATE_DIR=./backend/test/.tmp/health-agent-ci/state-$(date -u +%Y%m%d%H%M%S)-$$
export YUXI_ENV_FILE=./backend/test/support/health_consultation_e2e.env.example
export SANDBOX_ENV_FILE=./backend/test/support/health_consultation_sandbox.env.example
export YUXI_API_PORT=25061 YUXI_POSTGRES_PORT=25443 YUXI_REDIS_PORT=26390
export YUXI_SANDBOX_PORT=28013 YUXI_MINIO_API_PORT=29012 YUXI_MINIO_CONSOLE_PORT=29013
compose=(docker compose --env-file backend/test/support/health_consultation_e2e.env.example
  -f docker-compose.yml -f backend/test/support/health_consultation_e2e.compose.yml -p "$project")

cleanup() {
  result=$?
  if [ "$result" -ne 0 ]; then
    "${compose[@]}" logs storage-migrator --tail 80 >&2 || true
  fi
  "${compose[@]}" down -v
  return "$result"
}
trap cleanup EXIT
"${compose[@]}" up -d --no-build --pull never postgres redis minio etcd milvus sandbox-provisioner api worker
ready=false
for attempt in $(seq 1 90); do
  if "${compose[@]}" exec -T api curl -fsS --max-time 5 http://localhost:5050/api/system/ready >/dev/null; then
    ready=true
    break
  fi
  sleep 2
done
if [ "$ready" != true ]; then
  echo "隔离健康拓扑未就绪" >&2
  exit 1
fi
# 独立测试进程写入挂载的回执目录；API/Worker仍按Compose服务UID运行。
"${compose[@]}" exec -T -u root api uv run --no-sync --group test python test/support/health_agent_replay_gate.py
