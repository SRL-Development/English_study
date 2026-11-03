# 英语全能学习台

网站与微信小程序双端英语学习项目，共用 Flask + SQLite 后端。

## 功能

- 网站端词汇、听说、语法、完形填空、学习统计和 AI 口语陪练
- 微信小程序登录、单词听读、跟读评测、云端学习进度和个人中心
- 账号注册登录、邮箱激活、微信登录及后台用户统计
- Edge TTS 语音合成、讯飞 ISE 发音评测、OpenAI 兼容模型对话

## 客户端

- HTTPS 网页：后端直接托管 `english-learning.html`，通过同一域名访问 API
- 微信小程序：在 `miniprogram/config.js` 设置同一个 HTTPS API 域名

## 部署方式

支持以下服务端部署：

- Docker Compose（Linux/Windows，推荐）
- Linux 原生 Gunicorn + systemd
- Windows 原生 Waitress + 开机计划任务

完整操作见 [DEPLOYMENT.md](./DEPLOYMENT.md)。

## 本地运行

建议使用 Python 3.11 或 3.12，并安装用于音频转码的 FFmpeg。

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
```

复制环境变量模板并填写必要配置：

```bash
cp .env.example .env
```

开发环境启动：

```bash
python server.py
```

浏览器访问 `http://127.0.0.1:5000`，后台入口为
`http://127.0.0.1:5000/admin`，健康检查为
`http://127.0.0.1:5000/api/health`。

## 测试

```bash
python -m unittest -v test_server.py
npx pyright
```

## 生产部署

推荐使用 Gunicorn，仅监听本机端口，再由 Nginx 或宝塔反向代理：

```bash
gunicorn -w 2 --threads 4 --timeout 90 -b 127.0.0.1:5000 server:app
```

生产环境必须设置强随机 `ADMIN_PASSWORD`；密钥只放在 `.env` 或服务器环境变量中，
不得提交到仓库。数据库 `app.db`、语音缓存和本机工具文件已由 `.gitignore` 排除。

更完整的产品状态、接口和部署说明见 [小程序项目档案.md](./小程序项目档案.md)。
