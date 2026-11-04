# 部署指南

本项目发布为用户平台与管理平台两个独立镜像，运行时共用持久化数据卷：

```text
用户域名 / 微信小程序 ─→ user:5000 ─┐
                                     ├→ english-study-data
管理后台独立域名 ──────→ admin:5001 ─┘
```

生产环境只公开 `80/443`。宿主机的 `5000/5001` 都只监听 `127.0.0.1`，不得直接对全网开放。

## 一、统一配置

复制环境变量模板：

```bash
cp .env.example .env
```

至少填写：

```dotenv
ADMIN_PASSWORD=强随机密码
MAIL_SECRET=另一个强随机值
SITE_BASE_URL=https://englearner.cn
SITE_DOMAIN=englearner.cn
ADMIN_DOMAIN=admin.englearner.cn
APP_UTC_OFFSET_HOURS=8
```

微信、讯飞、LLM 和邮件配置按实际开通情况填写。`.env`、数据库和缓存均不得提交到 Git。

## 二、云主机 Docker + Nginx 部署（推荐）

生产环境使用 `compose.server.yaml`，不在服务器构建源码。宿主机 Nginx 公开 `80/443`，
USER/ADMIN 容器只绑定 `127.0.0.1:5000/5001`。数据库和 TTS 缓存保存在命名卷
`english-study-data`，重建容器不会删除。

把发布包解压到 `/opt/english-study` 后执行：

```bash
cd /opt/english-study
sudo bash deploy/cloud/install-dependencies.sh
cp .env.example .env
nano .env
sudo bash deploy/docker/install.sh
sudo bash deploy/nginx/configure.sh
```

依赖脚本支持 Ubuntu/Debian 以及使用 DNF/YUM 的主流 RPM 系统，并从 Docker 官方软件源
安装 Engine 与 Compose 插件。配置 HTTPS 前，必须先把 `SITE_DOMAIN`、`ADMIN_DOMAIN` 的
DNS A 记录指向服务器，并在阿里云安全组开放 TCP `22/80/443`。

容器启用了只读根文件系统、最小权限、PID 限制、健康检查与 Docker 日志轮转。不要开放
`5000/5001`，也不要执行 `docker compose down -v`。

### 备选：Docker 内 Caddy 自动 HTTPS

先把 `SITE_DOMAIN`、`ADMIN_DOMAIN` 的 DNS A 记录都指向服务器，并开放 `80/443`：

```bash
docker compose -f compose.yaml -f compose.https.yaml up -d
```

Caddy 会为两个域名分别申请证书。采用本指南的宿主机 Nginx 时不要启动 Caddy。

### Portainer 管理页面

```bash
docker compose -f deploy/portainer/compose.yaml up -d
```

Portainer 只绑定 `127.0.0.1:9443`。从自己的电脑建立 SSH 隧道后访问：

```bash
ssh -L 9443:127.0.0.1:9443 root@服务器IP
```

浏览器打开 `https://127.0.0.1:9443`。Portainer 挂载了 Docker Socket，必须视为最高权限管理入口。

### Docker 更新

```bash
sudo bash deploy/docker/update.sh
```

脚本会先在线备份 SQLite，再拉取两个稳定镜像、重建容器并核对角色、版本、构建号；
健康检查失败会自动回滚。服务器不需要 Git，也不会执行 `git pull`。

每次推送 `main` 后，GitHub Actions 还会运行后端测试并发布镜像：

```text
ghcr.io/srl-development/english-study-user:latest
ghcr.io/srl-development/english-study-admin:latest
```

若服务器可以访问 GHCR，可在 `.env` 中设置：

```dotenv
USER_IMAGE=ghcr.io/srl-development/english-study-user:latest
ADMIN_IMAGE=ghcr.io/srl-development/english-study-admin:latest
```

手动更新：

```bash
sudo bash deploy/docker/update.sh
```

阿里云访问 GHCR 不稳定时，可将两个镜像同步到阿里云 ACR，再把 `USER_IMAGE`、
`ADMIN_IMAGE` 改为对应的 ACR 地址。

### 旧方案：1Panel 图形界面

在 1Panel 的「容器 → 编排」中新建编排，使用仓库里的 `compose.1panel.yaml`，并在同一
编排目录创建 `.env`（可从 `.env.example` 复制）。首次部署或后续升级都执行：

```bash
docker compose -f compose.1panel.yaml pull user admin
docker compose -f compose.1panel.yaml up -d --force-recreate user admin
```

注意：1Panel 会把编排内容保存在面板数据库中，不会自动跟随 GitHub 文件变化。仓库的
`compose.1panel.yaml` 更新后，必须在 1Panel 编排编辑器中重新粘贴最新内容。新版中
Admin 容器内外均使用 `5001`，映射应显示为 `127.0.0.1:5001:5001`，并通过
`pull_policy: always` 避免只重启旧镜像。

在 1Panel「网站」中创建两个反向代理网站：用户域名代理到
`http://127.0.0.1:5000`，管理域名代理到 `http://127.0.0.1:5001`，然后分别申请
HTTPS 证书。阿里云安全组只需放行 `80/443`，不要放行 `5000/5001`。

完成首次部署后，推荐按 `deploy/1panel/README.md` 在 1Panel 创建「Shell 脚本」计划任务。
之后只需点击该任务的「执行」，脚本会自动备份、拉取、升级、验证，并在失败时回滚；
整个过程不依赖服务器访问 GitHub 源码。

## 三、Linux 原生部署

要求：Python 3.11/3.12、FFmpeg、Git、curl、Nginx（或其他 HTTPS 反向代理）。

```bash
sudo bash deploy/linux/install.sh
```

该脚本会创建虚拟环境、安装依赖、生成并启用 `english-learning.service`。检查：

```bash
systemctl status english-learning --no-pager
journalctl -u english-learning -f
curl http://127.0.0.1:5000/api/health
```

Nginx 示例位于 `deploy/nginx/english-learning.conf.example`。替换域名和证书路径后启用。

Linux 更新：

```bash
sudo bash deploy/linux/update.sh
```

更新脚本会备份数据库、安装新依赖、重启、健康检查，并保留最近 30 天备份。

## 四、Windows 原生部署

要求：64 位 Python 3.11/3.12、FFmpeg、Git。Windows 使用 Waitress，不使用 Gunicorn。

在 PowerShell 中：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\install.ps1
```

编辑 `.env` 后，前台启动：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\start.ps1
```

管理员 PowerShell 注册开机启动任务：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\register-task.ps1
```

日志位于 `data\logs\server.log`。Windows 更新：

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\update.ps1
```

Windows 对外 HTTPS 可安装 Caddy，并在项目根目录执行：

```powershell
$env:SITE_DOMAIN='englearner.cn'
caddy run --config deploy\caddy\Caddyfile.native
```

也可以使用 IIS ARR 或 Nginx，把 HTTPS 请求转发至 `127.0.0.1:5000`。

## 五、客户端

### HTTPS 网页

访问：

```text
https://englearner.cn/
```

网页和 API 同源，不需要额外配置 CORS。学员登录为 `/login`，注册为
`/register`，登录后各模块使用 `/app/...` 独立地址。管理员在独立域名使用
`/admin/login`，登录后进入 `/admin/dashboard`。两个容器的健康检查均为 `/api/health`。

Flask 已启用 HTML/JSON 压缩；Nginx 示例仅对 SSE `/chat` 关闭缓冲，普通页面和
API 保持 gzip 与代理缓冲。宝塔反向代理时建议同样开启 gzip，且不要对整站关闭
`proxy_buffering`。

### 微信小程序

修改 `miniprogram/config.js`：

```javascript
module.exports = {
  API_BASE: 'https://englearner.cn'
};
```

然后在微信公众平台配置：

- request 合法域名：`https://englearner.cn`
- uploadFile 合法域名：`https://englearner.cn`
- 域名必须 HTTPS、证书有效，并满足备案及小程序平台要求

## 六、数据备份

必须备份：

- `.env`
- `app.db`
- `tts_cache`（可选，可重新生成）

Docker 更新脚本把数据库备份到 `backups/`；Linux 更新脚本默认备份到
`/var/backups/english-learning/`；Windows 更新脚本备份到项目的 `backups/`。

任何部署方式都不要把真实 `.env`、数据库或备份文件提交到 GitHub。

### 从旧版根目录迁移 `app.db`

旧版默认把数据库放在项目根目录。Linux/Windows 原生新部署可先停止服务，再把它复制到
`.env` 中 `APP_DATA_DIR` 对应目录。

Docker 迁移示例（先把旧数据库放到当前项目根目录）：

```bash
docker compose stop user admin
docker run --rm \
  -v english-study-data:/data \
  -v "$PWD:/backup:ro" \
  python:3.12-slim \
  sh -c 'cp /backup/app.db /data/app.db && chown 10001:10001 /data/app.db'
docker compose start user admin
```

迁移前后都应保留一份独立数据库备份，并通过 `/api/health` 和后台用户列表确认数据完整。
