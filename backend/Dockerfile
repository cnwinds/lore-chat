FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV KB_PATH=/data/knowledge
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# 单 worker：SQLite FTS / Chroma 不适合多进程并发写
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
