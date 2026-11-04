#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "请使用 root 运行：sudo bash $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${ENGLISH_STUDY_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
ENV_FILE="$APP_DIR/.env"

read_env() {
  local key="$1"
  sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1 | tr -d '\r'
}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "找不到 $ENV_FILE"
  exit 1
fi

SITE_DOMAIN="${SITE_DOMAIN:-$(read_env SITE_DOMAIN)}"
ADMIN_DOMAIN="${ADMIN_DOMAIN:-$(read_env ADMIN_DOMAIN)}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-$(read_env LETSENCRYPT_EMAIL)}"

domain_pattern='^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$'
if [[ ! "$SITE_DOMAIN" =~ $domain_pattern ]]; then
  echo "SITE_DOMAIN 无效：$SITE_DOMAIN"
  exit 1
fi
if [[ ! "$ADMIN_DOMAIN" =~ $domain_pattern ]]; then
  echo "ADMIN_DOMAIN 无效：$ADMIN_DOMAIN"
  exit 1
fi
if [[ "$SITE_DOMAIN" == "$ADMIN_DOMAIN" ]]; then
  echo "用户域名和管理域名必须不同。"
  exit 1
fi
if [[ ! "$LETSENCRYPT_EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then
  echo "请在 .env 中填写有效的 LETSENCRYPT_EMAIL。"
  exit 1
fi

for command_name in nginx certbot curl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "缺少命令：$command_name"
    exit 1
  fi
done

if ! curl -fsS --max-time 8 http://127.0.0.1:5000/api/health >/dev/null \
  || ! curl -fsS --max-time 8 http://127.0.0.1:5001/api/health >/dev/null; then
  echo "Docker 服务尚未就绪，请先运行 deploy/docker/install.sh。"
  exit 1
fi

available_dir=/etc/nginx/sites-available
enabled_dir=/etc/nginx/sites-enabled
if [[ ! -d "$available_dir" || ! -d "$enabled_dir" ]]; then
  available_dir=/etc/nginx/conf.d
  enabled_dir=/etc/nginx/conf.d
fi

config_file="$available_dir/english-study.conf"
enabled_file="$enabled_dir/english-study.conf"
mkdir -p /var/www/certbot "$available_dir" "$enabled_dir"

render() {
  local template="$1"
  sed -e "s/__SITE_DOMAIN__/$SITE_DOMAIN/g" \
      -e "s/__ADMIN_DOMAIN__/$ADMIN_DOMAIN/g" \
      "$template" > "$config_file"
}

if [[ -f "$config_file" ]]; then
  cp -a "$config_file" "$config_file.backup-$(date +%Y%m%d-%H%M%S)"
fi

echo "正在启用 HTTP 验证配置……"
render "$SCRIPT_DIR/english-study-http.conf.template"
if [[ "$available_dir" != "$enabled_dir" ]]; then
  ln -sfn "$config_file" "$enabled_file"
fi
nginx -t
systemctl reload nginx

echo "正在申请或续用 Let's Encrypt 证书……"
certbot certonly --webroot -w /var/www/certbot \
  --non-interactive --agree-tos --keep-until-expiring \
  --email "$LETSENCRYPT_EMAIL" --cert-name "$SITE_DOMAIN" \
  -d "$SITE_DOMAIN" -d "$ADMIN_DOMAIN"

echo "正在启用双域名 HTTPS 配置……"
render "$SCRIPT_DIR/english-study-https.conf.template"
nginx -t
systemctl reload nginx

install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'HOOK'
#!/usr/bin/env bash
set -e
nginx -t
systemctl reload nginx
HOOK
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
systemctl enable --now certbot.timer 2>/dev/null || true

echo "HTTPS 配置完成："
echo "  USER  https://$SITE_DOMAIN"
echo "  ADMIN https://$ADMIN_DOMAIN/admin/login"
