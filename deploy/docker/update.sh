#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
APP_DIR="${ENGLISH_STUDY_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
COMPOSE_FILE="${ENGLISH_STUDY_COMPOSE:-$APP_DIR/compose.server.yaml}"
BACKUP_DIR="${ENGLISH_STUDY_BACKUPS:-$APP_DIR/backups}"
USER_IMAGE="${UPDATE_USER_IMAGE:-ghcr.io/shirenliang12-source/english-study-user:latest}"
ADMIN_IMAGE="${UPDATE_ADMIN_IMAGE:-ghcr.io/shirenliang12-source/english-study-admin:latest}"
LOCK_FILE="/tmp/english-study-docker-update.lock"

cd "$APP_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "已有升级任务正在执行，本次退出。"
  exit 0
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "找不到编排文件：$COMPOSE_FILE"
  exit 1
fi
if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "找不到环境变量文件：$APP_DIR/.env"
  exit 1
fi

compose() {
  USER_IMAGE="$USER_IMAGE" ADMIN_IMAGE="$ADMIN_IMAGE" \
    docker compose -f "$COMPOSE_FILE" "$@"
}

health() {
  local port="$1"
  curl -fsS --max-time 8 "http://127.0.0.1:${port}/api/health"
}

wait_for_health() {
  local expected_build="${1:-}"
  local user_health admin_health
  for _ in {1..45}; do
    user_health="$(health 5000 2>/dev/null || true)"
    admin_health="$(health 5001 2>/dev/null || true)"
    if [[ "$user_health" == *'"role":"user"'* \
      && "$admin_health" == *'"role":"admin"'* \
      && "$user_health" == *'"version"'* \
      && "$admin_health" == *'"version"'* ]]; then
      if [[ -z "$expected_build" \
        || ("$user_health" == *"$expected_build"* && "$admin_health" == *"$expected_build"*) ]]; then
        printf '%s\n%s\n' "$user_health" "$admin_health"
        return 0
      fi
    fi
    sleep 2
  done
  return 1
}

current_user_health="$(health 5000 2>/dev/null || true)"
current_admin_health="$(health 5001 2>/dev/null || true)"
old_user_id="$(docker image inspect --format '{{.Id}}' "$USER_IMAGE" 2>/dev/null || true)"
old_admin_id="$(docker image inspect --format '{{.Id}}' "$ADMIN_IMAGE" 2>/dev/null || true)"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
stamp="$(date +%Y%m%d-%H%M%S)"
user_cid="$(compose ps -q user 2>/dev/null || true)"
if [[ -n "$user_cid" ]]; then
  echo "正在在线备份数据库……"
  compose exec -T user python - "/data/app.db" "/tmp/app-$stamp.db" <<'PY'
import os
import sqlite3
import sys

source_path, target_path = sys.argv[1:3]
if os.path.exists(source_path):
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    with target:
        source.backup(target)
    target.close()
    source.close()
PY
  if compose exec -T user test -f "/tmp/app-$stamp.db"; then
    docker cp "$user_cid:/tmp/app-$stamp.db" "$BACKUP_DIR/app-$stamp.db"
    compose exec -T user rm -f "/tmp/app-$stamp.db"
    echo "数据库备份：$BACKUP_DIR/app-$stamp.db"
  fi
fi

rollback_user="english-study-user:rollback-$stamp"
rollback_admin="english-study-admin:rollback-$stamp"
if [[ -n "$old_user_id" ]]; then docker tag "$old_user_id" "$rollback_user"; fi
if [[ -n "$old_admin_id" ]]; then docker tag "$old_admin_id" "$rollback_admin"; fi

echo "正在拉取 USER 与 ADMIN 稳定通道镜像……"
docker pull "$USER_IMAGE"
docker pull "$ADMIN_IMAGE"
new_user_id="$(docker image inspect --format '{{.Id}}' "$USER_IMAGE")"
new_admin_id="$(docker image inspect --format '{{.Id}}' "$ADMIN_IMAGE")"

if [[ "$old_user_id" == "$new_user_id" && "$old_admin_id" == "$new_admin_id" \
  && "$current_user_health" == *'"role":"user"'* \
  && "$current_admin_health" == *'"role":"admin"'* ]]; then
  echo "已经是最新且服务健康，无需重建。"
  printf '%s\n%s\n' "$current_user_health" "$current_admin_health"
  exit 0
fi

expected_build="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$USER_IMAGE" 2>/dev/null || true)"
echo "正在重建 USER 与 ADMIN……"
if compose up -d --pull never --force-recreate --remove-orphans user admin \
  && wait_for_health "$expected_build"; then
  find "$BACKUP_DIR" -type f -name 'app-*.db' -mtime +30 -delete
  if command -v nginx >/dev/null 2>&1 && ! nginx -t; then
    echo "警告：应用升级成功，但 Nginx 配置检查未通过。现有 Nginx 进程未重载。"
  fi
  echo "升级完成。"
  exit 0
fi

echo "升级健康检查失败，正在回滚……"
if [[ -n "$old_user_id" && -n "$old_admin_id" ]]; then
  USER_IMAGE="$rollback_user" ADMIN_IMAGE="$rollback_admin" \
    docker compose -f "$COMPOSE_FILE" up -d --pull never --force-recreate user admin
  if wait_for_health; then
    echo "已回滚到升级前版本。"
  else
    echo "自动回滚后健康检查仍失败，请运行 docker compose logs。"
  fi
else
  echo "首次安装没有旧镜像可回滚，请检查容器日志。"
fi
exit 1
