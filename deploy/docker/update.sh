#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BACKUP_DIR="$APP_DIR/backups"
cd "$APP_DIR"

exec 9>/tmp/english-learning-docker-update.lock
flock -n 9 || exit 0

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "检测到本地代码修改，停止更新。"
  git status --short
  exit 1
fi

git fetch origin main --quiet
OLD="$(git rev-parse HEAD)"
NEW="$(git rev-parse origin/main)"

if [[ "$OLD" == "$NEW" ]]; then
  echo "已经是最新版本：$OLD"
  exit 0
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
CID="$(docker compose ps -q app 2>/dev/null || true)"

if [[ -n "$CID" ]]; then
  docker compose exec -T app python - "/data/app.db" "/tmp/app-$STAMP.db" <<'PY'
import os
import sqlite3
import sys
if os.path.exists(sys.argv[1]):
    source = sqlite3.connect(sys.argv[1])
    target = sqlite3.connect(sys.argv[2])
    with target:
        source.backup(target)
    target.close()
    source.close()
PY
  docker cp "$CID:/tmp/app-$STAMP.db" "$BACKUP_DIR/app-$STAMP.db" 2>/dev/null || true
  docker compose exec -T app rm -f "/tmp/app-$STAMP.db" || true
fi

git merge --ff-only origin/main

if ! docker compose build app || ! docker compose up -d app; then
  git reset --hard "$OLD"
  docker compose build app || true
  docker compose up -d app || true
  echo "容器更新失败，已尝试恢复旧版本。"
  exit 1
fi

for _ in {1..12}; do
  if curl -fsS http://127.0.0.1:5000/api/health >/dev/null; then
    find "$BACKUP_DIR" -type f -name 'app-*.db' -mtime +30 -delete
    echo "部署成功：$(git rev-parse HEAD)"
    exit 0
  fi
  sleep 5
done

git reset --hard "$OLD"
docker compose build app
docker compose up -d app
echo "健康检查失败，已恢复旧版本。"
exit 1
