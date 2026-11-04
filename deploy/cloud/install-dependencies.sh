#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "请使用 root 运行：sudo bash $0"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

install_apt() {
  . /etc/os-release
  case "$ID" in
    ubuntu|debian) ;;
    *)
      echo "暂不支持此 apt 系统：$ID"
      exit 1
      ;;
  esac

  apt-get update
  apt-get install -y ca-certificates curl gnupg nginx certbot unzip util-linux

  if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/$ID/gpg" \
      -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    local codename="${VERSION_CODENAME:-}"
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$ID $codename stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io \
      docker-buildx-plugin docker-compose-plugin
  fi
}

install_rpm() {
  local package_manager="$1"
  "$package_manager" install -y dnf-plugins-core ca-certificates curl nginx certbot unzip util-linux

  if ! command -v docker >/dev/null 2>&1; then
    "$package_manager" config-manager --add-repo \
      https://download.docker.com/linux/centos/docker-ce.repo
    "$package_manager" install -y docker-ce docker-ce-cli containerd.io \
      docker-buildx-plugin docker-compose-plugin
  fi
}

if command -v apt-get >/dev/null 2>&1; then
  install_apt
elif command -v dnf >/dev/null 2>&1; then
  install_rpm dnf
elif command -v yum >/dev/null 2>&1; then
  install_rpm yum
else
  echo "不支持当前操作系统，请手动安装 Docker Engine、Compose、Nginx、Certbot 和 curl。"
  exit 1
fi

systemctl enable --now docker
systemctl enable --now nginx

docker version --format 'Docker Server {{.Server.Version}}'
docker compose version
nginx -v
certbot --version

echo "依赖安装完成。阿里云安全组只需开放 TCP 22、80、443。"
