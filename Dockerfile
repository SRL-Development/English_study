FROM python:3.12-slim

ARG APP_ROLE=all
ARG APP_PORT=5000
ARG APP_VERSION=dev
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_DATA_DIR=/data \
    APP_ROLE=${APP_ROLE} \
    APP_PORT=${APP_PORT} \
    APP_VERSION=${APP_VERSION}

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py assess-proxy.py admin.html english-learning.html index.html ./

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app \
    && mkdir -p /data \
    && chown -R app:app /data

USER app

EXPOSE ${APP_PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('APP_PORT','5000')+'/api/health', timeout=3)"

CMD ["sh", "-c", "exec gunicorn --workers 2 --threads 4 --timeout 90 --bind 0.0.0.0:${APP_PORT} server:app"]
