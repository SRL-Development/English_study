# 英语全能学习台

网站与微信小程序双端英语学习项目。用户平台和管理平台发布为两个独立 Docker 镜像，
共用同一个 SQLite 持久化数据卷。

## 功能

- 网站端词汇、听说、语法、完形填空、学习统计和 AI 口语陪练
- 幼儿园「动画英语岛」：15 节互动动画课、听辨、跟读、星星贴纸
- 小学「英语挑战世界」：15 个地图关卡、五类游戏挑战、金币与 Boss 关
- 家长儿童档案、分龄进度、每日时长与后台儿童活跃统计
- 统一登录入口：幼儿、小学、初中、高中、大学、成人六个阶段，自动进入对应学习空间
- 全学段课程中心：72 个原创主题单元，词汇、听说对话、阅读、知识点、客观练习与表达任务
- 课程判题和进度在服务端保存；按用户/儿童档案隔离，错题穿插复习且连续答对 10 次移除
- 内置 30,000 英汉词条与 30,000 双语句，支持考试标签、分级和搜索
- 微信小程序登录、单词听读、跟读评测、云端学习进度和个人中心
- 账号注册登录、邮箱激活、微信登录及运营后台（DAU/WAU/MAU、留存、学习活跃）
- 管理后台可修改管理员密码；密码哈希保存在持久化数据库中并在升级后保留
- Edge TTS 语音合成、讯飞 ISE 发音评测、OpenAI 兼容模型对话

## 客户端

- HTTPS 网页：后端直接托管 `english-learning.html`，通过同一域名访问 API
- 微信小程序：在 `miniprogram/config.js` 设置同一个 HTTPS API 域名

## 部署方式

支持以下服务端部署：

- 云主机 Docker Compose + 宿主机 Nginx（生产环境推荐）
- Docker Compose（Linux/Windows）
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

Docker 部署后，用户平台监听 `127.0.0.1:5000`，管理平台监听
`127.0.0.1:5001`；两个容器内部也分别监听 `5000` 和 `5001`。用户镜像不提供
管理路由，管理镜像也不提供用户页面与用户 API。

所有用户统一从 `/login` 登录或从 `/register` 注册，并按选择的年龄段自动分流。
用户端页面分别为 `/app/home`、`/app/vocabulary`、`/app/speaking`、
`/app/grammar`、`/app/profile`；儿童中心为 `/kids`，幼儿园和小学内部页面分别为
`/kids/kindergarten`、`/kids/primary`；管理端入口为 `/admin/login`。

全学段课程目录为 `/courses`，各路径为 `/courses/kindergarten`、`/courses/primary`、
`/courses/junior`、`/courses/senior`、`/courses/university`、`/courses/general`。
课程按国内主题与能力框架设计，小学/初中参考《义务教育英语课程标准（2022年版）》，
高中衔接必修/选择性必修能力，大学参考《大学英语教学指南（2020版）》的通用英语、
专门用途英语与跨文化交际方向。每个路径当前 12 单元、48 道原创客观题；
这是首批主题课程，尚不等同于所有出版社教材、学校进度或完整考试大纲覆盖。
幼儿路径采用亲子听说和动作体验，不宣称幼儿国家英语课标。
自由写作与口头表达提供参考和自查清单，不进行自动评分；客观题完成线为 75%。
各阶段的课程依据和覆盖范围随目录 API 返回并展示在课程页。

## 测试

```bash
python -m unittest -v test_server.py
npx pyright
```

## 生产部署

云主机生产部署使用 `compose.server.yaml`，容器仅监听本机端口，再由宿主机 Nginx
提供双域名 HTTPS。完整的一键安装、升级与回滚说明见
[`deploy/docker/README.md`](./deploy/docker/README.md)。原生 Python 部署推荐使用 Gunicorn：

```bash
gunicorn -w 2 --threads 4 --timeout 90 -b 127.0.0.1:5000 server:app
```

生产环境必须设置强随机 `ADMIN_PASSWORD`；密钥只放在 `.env` 或服务器环境变量中，
不得提交到仓库。数据库 `app.db`、语音缓存和本机工具文件已由 `.gitignore` 排除。

更完整的产品状态、接口和部署说明见 [小程序项目档案.md](./小程序项目档案.md)。
