#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "请使用 root 执行：sudo bash deploy/linux/install.sh"
  exit 1
fi

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR="${APP_DATA_DIR:-$APP_DIR/data}"

if id www >/dev/null 2>&1; then
  RUN_USER="${RUN_USER:-www}"
elif id www-data >/dev/null 2>&1; then
  RUN_USER="${RUN_USER:-www-data}"
else
  echo "未找到 www 或 www-data 用户，请先创建运行用户或设置 RUN_USER。"
  exit 1
fi

command -v python3 >/dev/null || { echo "缺少 python3"; exit 1; }
command -v ffmpeg >/dev/null || { echo "缺少 ffmpeg"; exit 1; }

python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

install -d -o "$RUN_USER" -g "$RUN_USER" -m 750 "$DATA_DIR"

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "已创建 $APP_DIR/.env，请尽快填写 ADMIN_PASSWORD、MAIL_SECRET 和正式域名。"
fi

sed \
  -e "s|__APP_DIR__|$APP_DIR|g" \
  -e "s|__DATA_DIR__|$DATA_DIR|g" \
  -e "s|__RUN_USER__|$RUN_USER|g" \
  "$APP_DIR/deploy/linux/english-learning.service.template" \
  > /etc/systemd/system/english-learning.service

systemctl daemon-reload
systemctl enable --now english-learning.service

sleep 3
curl -fsS http://127.0.0.1:5000/api/health
echo
echo "安装完成。服务日志：journalctl -u english-learning -f"
