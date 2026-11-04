# 云主机 Docker + Nginx 部署

生产结构：宿主机 Nginx 只公开 `80/443`，两个 Docker 容器分别只监听
`127.0.0.1:5000` 与 `127.0.0.1:5001`，共用 `english-study-data` 数据卷。

## 首次安装

```bash
cd /opt/english-study
sudo bash deploy/cloud/install-dependencies.sh
cp .env.example .env
nano .env
sudo bash deploy/docker/install.sh
sudo bash deploy/nginx/configure.sh
```

`.env` 至少填写 `ADMIN_PASSWORD`、`MAIL_SECRET`、`SITE_BASE_URL`、
`SITE_DOMAIN`、`ADMIN_DOMAIN` 和 `LETSENCRYPT_EMAIL`。两个域名必须先解析到
云主机公网 IP；阿里云安全组开放 TCP `22/80/443`，不要开放 `5000/5001`。

## 后续一键升级

```bash
cd /opt/english-study
sudo bash deploy/docker/update.sh
```

首次安装会同时创建全局命令，之后可直接执行：

```bash
sudo english-study-update
```

升级脚本不执行 `git pull`，只拉取已经通过 CI 测试的 USER/ADMIN 镜像；升级前在线备份
SQLite，升级后核对双端角色、版本和构建号，失败则自动回滚旧镜像。

## 常用运维命令

```bash
docker compose -f compose.server.yaml ps
docker compose -f compose.server.yaml logs -f --tail=200
curl -s http://127.0.0.1:5000/api/health
curl -s http://127.0.0.1:5001/api/health
sudo nginx -t
sudo certbot renew --dry-run
```

不要执行 `docker compose down -v`，否则会删除用户数据库所在的数据卷。
