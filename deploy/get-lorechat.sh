#!/usr/bin/env bash
# 下载单文件启动器并启动。
# Linux/macOS:
#   curl -fsSL https://raw.githubusercontent.com/cnwinds/lore-chat/master/deploy/get-lorechat.sh | bash
#   curl ... | bash -s -- --work
# Windows（PowerShell）请改用:
#   irm https://raw.githubusercontent.com/cnwinds/lore-chat/master/deploy/get-lorechat.ps1 | iex
set -euo pipefail

REPO_RAW="${LORECHAT_REPO_RAW:-https://raw.githubusercontent.com/cnwinds/lore-chat/master}"
DEST="${LORECHAT_DIR:-${PWD}/lore-chat}"
MODE_FLAG="${1:-}"

echo "[Lore Chat] 安装目录: ${DEST}"
mkdir -p "${DEST}"
echo "[Lore Chat] 下载 lorechat.sh（单文件启动器）"
curl -fsSL "${REPO_RAW}/deploy/lorechat.sh" -o "${DEST}/lorechat.sh"
chmod +x "${DEST}/lorechat.sh"
cd "${DEST}"

echo "[Lore Chat] 就绪。仅需本目录下的 lorechat.sh 即可启动。"
if [[ -n "${MODE_FLAG}" ]]; then
  exec ./lorechat.sh start "${MODE_FLAG}"
fi
if [[ -t 0 ]]; then
  exec ./lorechat.sh start
fi
exec ./lorechat.sh start --chat
