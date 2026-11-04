#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${ENGLISH_STUDY_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
COMPOSE_FILE="${ENGLISH_STUDY_COMPOSE:-$APP_DIR/compose.server.yaml}"

for command_name in docker curl flock; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "缺少命令：$command_name"
    exit 1
  fi
done
if ! docker compose version >/dev/null 2>&1; then
  echo "未安装 Docker Compose 插件。"
  exit 1
fi
if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "找不到 $APP_DIR/.env，请先从 .env.example 复制并填写。"
  exit 1
fi
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "找不到生产编排文件：$COMPOSE_FILE"
  exit 1
fi

admin_password="$(sed -n 's/^ADMIN_PASSWORD=//p' "$APP_DIR/.env" | tail -n 1 | tr -d '\r')"
if [[ -z "$admin_password" ]]; then
  echo ".env 中的 ADMIN_PASSWORD 不能为空。"
  exit 1
fi

mkdir -p "$APP_DIR/backups"
chmod 700 "$APP_DIR/backups"

ENGLISH_STUDY_DIR="$APP_DIR" ENGLISH_STUDY_COMPOSE="$COMPOSE_FILE" \
  bash "$SCRIPT_DIR/update.sh"

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  ln -sfn "$SCRIPT_DIR/update.sh" /usr/local/bin/english-study-update
fi

echo
echo "Docker 应用安装完成："
echo "  USER  http://127.0.0.1:5000"
echo "  ADMIN http://127.0.0.1:5001"
echo "下一步运行 deploy/nginx/configure.sh 配置域名与 HTTPS。"
echo "以后在任意目录执行 sudo english-study-update 即可一键升级。"
