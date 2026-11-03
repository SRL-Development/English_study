#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "请使用 root 执行此脚本。"
  exit 1
fi

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/english-learning}"
SERVICE="english-learning"
HEALTH_URL="http://127.0.0.1:5000/api/health"

exec 9>/var/lock/english-learning-update.lock
flock -n 9 || exit 0

cd "$APP_DIR"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "检测到服务器本地代码修改，停止更新。"
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
DB_PATH="$("$APP_DIR/venv/bin/python" -c 'import server; print(server.DB)')"

if [[ -s "$DB_PATH" ]]; then
  "$APP_DIR/venv/bin/python" - "$DB_PATH" "$BACKUP_DIR/app-$STAMP.db" <<'PY'
import sqlite3
import sys
source = sqlite3.connect(sys.argv[1])
target = sqlite3.connect(sys.argv[2])
with target:
    source.backup(target)
target.close()
source.close()
PY
fi

git merge --ff-only origin/main

if ! "$APP_DIR/venv/bin/pip" install -q -r requirements.txt; then
  git reset --hard "$OLD"
  echo "依赖安装失败，已恢复旧代码。"
  exit 1
fi

if ! systemctl restart "$SERVICE" || ! sleep 4 || ! curl -fsS "$HEALTH_URL" >/dev/null; then
  echo "健康检查失败，开始回滚。"
  git reset --hard "$OLD"
  "$APP_DIR/venv/bin/pip" install -q -r requirements.txt || true
  systemctl restart "$SERVICE" || true
  exit 1
fi

find "$BACKUP_DIR" -type f -name 'app-*.db' -mtime +30 -delete
echo "部署成功：$(git rev-parse HEAD)"
