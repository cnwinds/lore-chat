#!/bin/sh
set -e

# 部署即重置：每次启动从 demo/ 的纯文本内容重建运行时知识库，
# 运行期漂移（若有）自动消失。
python /app/demo/build.py --kb "${KB_PATH:-/data/knowledge}"

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
