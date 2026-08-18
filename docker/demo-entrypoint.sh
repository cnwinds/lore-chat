#!/bin/sh
set -e

# 部署即重置：每次启动从 demo/ 的纯文本内容重建运行时知识库。
# settings.json / auth.json 含密钥与口令，不在 demo/ 定稿里；从 backups 旁路还原，
# 避免每次重建后演示站无模型可用。
PRESERVE_DIR="${BACKUP_DIR:-/data/backups}/demo-preserved"
KB="${KB_PATH:-/data/knowledge}"

python /app/demo/build.py --kb "${KB}"

mkdir -p "${KB}/.kb"
if [ -f "${PRESERVE_DIR}/settings.json" ]; then
  cp "${PRESERVE_DIR}/settings.json" "${KB}/.kb/settings.json"
fi
if [ -f "${PRESERVE_DIR}/auth.json" ]; then
  cp "${PRESERVE_DIR}/auth.json" "${KB}/.kb/auth.json"
fi

# 叠加 --dev 时 compose 会传入 uvicorn --reload …；否则默认单 worker。
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
