#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容旧启动命令的入口。

声学评测与 AI 对话已经合并到 ``server.py``。保留此文件是为了让旧的
``python assess-proxy.py`` 启动命令继续可用，同时避免维护两套接口代码和安全配置。

新部署请统一使用：
    gunicorn server:app
"""

from server import app


if __name__ == "__main__":
    app.logger.warning(
        "assess-proxy.py 已合并至 server.py；生产环境请使用 gunicorn server:app"
    )
    app.run(host="0.0.0.0", port=5000)
