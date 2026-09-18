FROM python:3.12-slim

# Debian apt 国内源
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r requirements.txt

COPY app ./app

ARG LORECHAT_VERSION=0.0.0
ARG LORECHAT_REVISION=""
ARG LORECHAT_COMMITS_AHEAD=0
ARG LORECHAT_CHANNEL=development
ARG LORECHAT_DIRTY=0
ENV LORECHAT_VERSION=$LORECHAT_VERSION \
    LORECHAT_REVISION=$LORECHAT_REVISION \
    LORECHAT_COMMITS_AHEAD=$LORECHAT_COMMITS_AHEAD \
    LORECHAT_CHANNEL=$LORECHAT_CHANNEL \
    LORECHAT_DIRTY=$LORECHAT_DIRTY
LABEL org.opencontainers.image.title="Lore Chat backend" \
      org.opencontainers.image.version="$LORECHAT_VERSION" \
      org.opencontainers.image.revision="$LORECHAT_REVISION"

ENV KB_PATH=/data/knowledge
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# 单 worker：SQLite FTS / Chroma 不适合多进程并发写
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
