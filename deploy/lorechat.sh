#!/usr/bin/env bash
# Lore Chat 单文件启动器（Linux / macOS）
# 用法: ./lorechat.sh start [--chat|--work]
# 自包含：运行时在脚本旁写出 compose / 沙箱配置，无需仓库其它文件。
# 生成: python3 scripts/gen-deploy-launchers.py
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="${ROOT}/.lorechat"
MODE_FILE="${RUNTIME}/run-mode"
AUTOUPDATE_FILE="${RUNTIME}/autoupdate"
WATCHTOWER_NAME="lorechat-watchtower"
WATCHTOWER_IMAGE="containrrr/watchtower:1.7.1"
DEFAULT_SANDBOX_IMAGE="ghcr.io/cnwinds/lore-chat-sandbox-agent:latest"
OPENSANDBOX_SERVER_IMAGE="opensandbox/server:latest"
OPENSANDBOX_EXECD_IMAGE="opensandbox/execd:v1.0.18"
OPENSANDBOX_EGRESS_IMAGE="opensandbox/egress:v1.1.0"

usage() {
  cat <<'EOF'
Usage: ./lorechat.sh <command> [options]

Commands:
  start [--chat|--work]   启动（可每次选择聊天 / Work 模式）
  stop                    停止
  update [--chat|--work]  拉取最新镜像并启动
  autoupdate on [秒]      启用 Watchtower：GHCR 有新镜像时自动拉取并重启
  autoupdate off          关闭自动更新
  autoupdate status       查看自动更新状态
  prepare                 仅写出 compose / 配置（不启动）
  log|logs                查看日志
  help                    帮助

Modes:
  --chat   仅对话与知识库
  --work   带 OpenSandbox（首次镜像较大时会提示）

数据目录：
  默认脚本旁 ./data。若本脚本位于 git 仓库的 deploy/ 下，则改用 ../docker/data。
  也可用环境变量或 .env 中的 LORECHAT_DATA_DIR 覆盖。

自动更新：
  保持 .env 中 LORECHAT_IMAGE_TAG=latest（跟随 master 推送的 GHCR latest）。
  启用后只监视 lorechat-backend / lorechat-web；沙箱 agent 镜像在手动 update 时一并刷新。
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[Lore Chat] 缺少命令: $1（请先安装 Docker）" >&2
    exit 1
  fi
}

write_file() {
  local path="$1"
  mkdir -p "$(dirname "${path}")"
  cat >"${path}"
}

in_repo_deploy() {
  [[ "$(basename "${ROOT}")" == "deploy" && -f "${ROOT}/../lorechat.sh" && -f "${ROOT}/../docker/docker-compose.yml" ]]
}

resolve_data_dir() {
  local explicit=""
  if [[ -n "${LORECHAT_DATA_DIR:-}" ]]; then
    explicit="${LORECHAT_DATA_DIR}"
  else
    explicit="$(env_get LORECHAT_DATA_DIR)"
  fi
  local target
  if [[ -n "${explicit}" ]]; then
    if [[ "${explicit}" = /* ]]; then
      target="${explicit}"
    else
      target="${ROOT}/${explicit}"
    fi
  elif in_repo_deploy; then
    target="${ROOT}/../docker/data"
  else
    target="${ROOT}/data"
  fi
  mkdir -p "${target}"
  (cd "${target}" && pwd)
}

prepare_data_dir() {
  local dir
  dir="$(resolve_data_dir)"
  mkdir -p "${dir}/knowledge" "${dir}/backups"
  export LORECHAT_DATA_DIR="${dir}"
}

materialize_bundle() {
  mkdir -p "${ROOT}/opensandbox" "${RUNTIME}"
  write_file "${ROOT}/docker-compose.yml" <<'LORECHAT_EOF'
name: lore-chat

services:
  backend:
    image: ${LORECHAT_BACKEND_IMAGE:-ghcr.io/cnwinds/lore-chat-backend:${LORECHAT_IMAGE_TAG:-latest}}
    container_name: lorechat-backend
    env_file:
      - .env
    environment:
      KB_PATH: /data/knowledge
      BACKUP_DIR: /data/backups
      SANDBOX_ENABLED: ${SANDBOX_ENABLED:-false}
      HTTP_PROXY: ${HTTP_PROXY:-}
      HTTPS_PROXY: ${HTTPS_PROXY:-}
      http_proxy: ${http_proxy:-${HTTP_PROXY:-}}
      https_proxy: ${https_proxy:-${HTTPS_PROXY:-}}
      NO_PROXY: ${NO_PROXY:-localhost,127.0.0.1}
      no_proxy: ${no_proxy:-${NO_PROXY:-localhost,127.0.0.1}}
    volumes:
      - ${LORECHAT_DATA_DIR:-./data}/knowledge:/data/knowledge
      - ${LORECHAT_DATA_DIR:-./data}/backups:/data/backups
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
    networks:
      - lorechat
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  web:
    image: ${LORECHAT_WEB_IMAGE:-ghcr.io/cnwinds/lore-chat-web:${LORECHAT_IMAGE_TAG:-latest}}
    container_name: lorechat-web
    ports:
      - "${WEB_PORT:-8080}:80"
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - lorechat

networks:
  lorechat:
    name: lorechat-net
LORECHAT_EOF
  write_file "${ROOT}/docker-compose.sandbox.yml" <<'LORECHAT_EOF'
# Work overlay for prebuilt images (default SANDBOX_IMAGE=ghcr.io/cnwinds/lore-chat-sandbox-agent:${LORECHAT_IMAGE_TAG:-latest}).
# Embedded by gen-deploy-launchers.py from docker/docker-compose.sandbox.yml.
# 带执行能力（OpenSandbox）的叠加编排。
# 默认 docker-compose.yml 不含沙箱；需要执行能力时额外 -f 本文件。
# 预构建单文件启动器由 scripts/gen-deploy-launchers.py 嵌入本文件（并把 SANDBOX_IMAGE 默认改为 GHCR）。
#
# 启动示例（项目根）：
#   docker compose --project-directory docker --env-file .env \
#     -f docker/docker-compose.yml -f docker/docker-compose.sandbox.yml up -d --build
#
# 沙箱 Agent 镜像（hn-video-report 默认环境）须先构建：
#   docker build -t lorechat-sandbox-agent:local \
#     -f docker/opensandbox/Dockerfile.agent docker/opensandbox

services:
  backend:
    environment:
      SANDBOX_ENABLED: "true"
      OPENSANDBOX_DOMAIN: opensandbox-server:8090
      OPENSANDBOX_PROTOCOL: http
      # server 内嵌 proxy 在本机 Docker 下会挂死；backend 经 host.docker.internal 直连 sandbox 端口
      OPENSANDBOX_USE_SERVER_PROXY: "false"
      OPENSANDBOX_API_KEY: ${OPENSANDBOX_API_KEY:-}
      OPENSANDBOX_WORKSPACE_VOLUME: lorechat-sandbox-workspace
      SANDBOX_IMAGE: ${SANDBOX_IMAGE:-ghcr.io/cnwinds/lore-chat-sandbox-agent:${LORECHAT_IMAGE_TAG:-latest}}
      # 默认信任：沙箱命令不征询；可在设置里关闭
      SANDBOX_TRUST_MODE: ${SANDBOX_TRUST_MODE:-true}
      SANDBOX_MIRROR_REGION: ${SANDBOX_MIRROR_REGION:-cn}
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      opensandbox-server:
        condition: service_started

  opensandbox-server:
    image: opensandbox/server:latest
    container_name: lorechat-opensandbox
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./opensandbox/config.toml:/etc/opensandbox/config.toml:ro
    environment:
      SANDBOX_CONFIG_PATH: /etc/opensandbox/config.toml
      # 生产务必在 .env 设置 OPENSANDBOX_API_KEY，并改 OPENSANDBOX_INSECURE_SERVER=NO
      OPENSANDBOX_INSECURE_SERVER: ${OPENSANDBOX_INSECURE_SERVER:-YES}
    ports:
      # 可选：宿主机调试；backend 走内网 opensandbox-server:8090
      - "${OPENSANDBOX_HOST_PORT:-18090}:8090"
    networks:
      - lorechat
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped

volumes:
  # 默认角色 PVC（须预先存在）。其他角色的 lorechat-sandbox-ws-<slug>
  # 由 OpenSandbox PVC(create_if_not_exists) 按需创建，不必在此枚举。
  lorechat-sandbox-workspace:
    name: lorechat-sandbox-workspace
LORECHAT_EOF
  write_file "${ROOT}/opensandbox/config.toml" <<'LORECHAT_EOF'
[server]
host = "0.0.0.0"
port = 8090

[log]
level = "INFO"

[runtime]
type = "docker"
execd_image = "opensandbox/execd:v1.0.18"

[egress]
image = "opensandbox/egress:v1.1.0"

[docker]
network_mode = "bridge"
# server 跑在容器里时须用宿主机可达地址（官方 compose 示例同此）；
# backend 走 use_server_proxy，不直连 host_ip。宿主机直连调试请用 spike 的 127.0.0.1。
host_ip = "host.docker.internal"
drop_capabilities = ["AUDIT_WRITE", "MKNOD", "NET_ADMIN", "NET_RAW", "SYS_ADMIN", "SYS_MODULE", "SYS_PTRACE", "SYS_TIME", "SYS_TTY_CONFIG"]
no_new_privileges = true
pids_limit = 4096

[ingress]
mode = "direct"
LORECHAT_EOF
  write_file "${ROOT}/.env.example" <<'LORECHAT_EOF'
# 由单文件启动器写出。模型与 API Key 请在网页「设置 → 模型」自行添加。

WEB_PORT=8080

# OPENAI_API_KEY=
# OPENAI_BASE_URL=
# SMALL_MODEL=
# BIG_MODEL=
# EMBED_MODEL=

# GHCR 镜像标签：latest（默认）或发行版如 0.1.0（不要加 v；git tag 才是 v0.1.0）
# 跟随主干自动更新时请保持 latest，并执行：./lorechat.sh autoupdate on
LORECHAT_IMAGE_TAG=latest

# 自动更新轮询间隔（秒）；仅 ./lorechat.sh autoupdate on 时生效
# LORECHAT_AUTO_UPDATE_INTERVAL=300

# 需要换完整镜像名时再取消注释
# LORECHAT_BACKEND_IMAGE=ghcr.io/cnwinds/lore-chat-backend:0.1.0
# LORECHAT_WEB_IMAGE=ghcr.io/cnwinds/lore-chat-web:0.1.0
# SANDBOX_IMAGE=ghcr.io/cnwinds/lore-chat-sandbox-agent:0.1.0

# 可选：覆盖知识库目录（绝对路径或相对脚本目录）
# 仓库内运行本启动器时默认已是 ../docker/data，一般不必改
# LORECHAT_DATA_DIR=
LORECHAT_EOF

  if [[ ! -f "${ROOT}/.env" ]]; then
    cp "${ROOT}/.env.example" "${ROOT}/.env"
    echo "[Lore Chat] 已创建 .env（API Key 可在网页设置中填写）"
  fi
  prepare_data_dir
}

read_saved_mode() {
  if [[ -f "${MODE_FILE}" ]]; then
    tr -d '[:space:]' <"${MODE_FILE}"
  else
    echo "chat"
  fi
}

save_mode() {
  mkdir -p "${RUNTIME}"
  printf '%s\n' "$1" >"${MODE_FILE}"
}

pick_mode_interactive() {
  local saved default_idx=1 choice
  saved="$(read_saved_mode)"
  [[ "${saved}" == "work" ]] && default_idx=2
  echo "[Lore Chat] 请选择启动模式："
  echo "  1) 聊天模式 — 对话与知识库（默认更轻量）"
  echo "  2) Work 模式 — 额外启用沙箱执行（首次镜像较大）"
  read -r -p "输入 1 或 2 [默认 ${default_idx}]: " choice || true
  choice="${choice:-${default_idx}}"
  case "${choice}" in
    2|work|WORK) echo "work" ;;
    *) echo "chat" ;;
  esac
}

resolve_mode() {
  local flag="${1:-}"
  case "${flag}" in
    --chat|chat) echo "chat" ;;
    --work|work) echo "work" ;;
    "")
      if [[ -t 0 ]]; then
        pick_mode_interactive
      else
        read_saved_mode
      fi
      ;;
    *)
      echo "[Lore Chat] 未知模式: ${flag}（用 --chat 或 --work）" >&2
      return 1
      ;;
  esac
}

sandbox_image_ref() {
  local pinned="" tag=""
  if [[ -f "${ROOT}/.env" ]]; then
    pinned="$(grep -E '^SANDBOX_IMAGE=' "${ROOT}/.env" 2>/dev/null | cut -d= -f2- | tr -d '\r' || true)"
    tag="$(grep -E '^LORECHAT_IMAGE_TAG=' "${ROOT}/.env" 2>/dev/null | cut -d= -f2- | tr -d '\r' || true)"
  fi
  if [[ -n "${pinned}" ]]; then
    echo "${pinned}"
    return
  fi
  if [[ -n "${SANDBOX_IMAGE:-}" ]]; then
    echo "${SANDBOX_IMAGE}"
    return
  fi
  echo "ghcr.io/cnwinds/lore-chat-sandbox-agent:${tag:-${LORECHAT_IMAGE_TAG:-latest}}"
}

image_present() {
  docker image inspect "$1" >/dev/null 2>&1
}

work_images_cached() {
  local agent
  agent="$(sandbox_image_ref)"
  image_present "${OPENSANDBOX_SERVER_IMAGE}" \
    && image_present "${agent}" \
    && image_present "${OPENSANDBOX_EXECD_IMAGE}" \
    && image_present "${OPENSANDBOX_EGRESS_IMAGE}"
}

warn_work_images() {
  if work_images_cached; then
    echo "[Lore Chat] Work 模式：本机已有沙箱相关镜像，将按需检查更新。"
    return
  fi
  echo "[Lore Chat] Work 模式将额外拉取沙箱相关镜像（opensandbox/server、execd、egress、sandbox-agent 等）。"
  echo "[Lore Chat] 首次下载可能较慢，请耐心等待。"
}

run_compose() {
  local mode="$1"
  shift
  need_cmd docker
  if ! docker compose version >/dev/null 2>&1; then
    echo "[Lore Chat] 需要 Docker Compose 插件（docker compose）" >&2
    exit 1
  fi
  local -a files=(-f "${ROOT}/docker-compose.yml")
  if [[ "${mode}" == "work" ]]; then
    files+=(-f "${ROOT}/docker-compose.sandbox.yml")
  fi
  docker compose --project-directory "${ROOT}" --env-file "${ROOT}/.env" "${files[@]}" "$@"
}

teardown_all() {
  run_compose work down --remove-orphans >/dev/null 2>&1 || true
  run_compose chat down --remove-orphans >/dev/null 2>&1 || true
}

web_port() {
  local port
  port="$(grep -E '^WEB_PORT=' "${ROOT}/.env" 2>/dev/null | cut -d= -f2- | tr -d '\r' || true)"
  echo "${port:-8080}"
}

env_get() {
  local key="$1"
  [[ -f "${ROOT}/.env" ]] || return 0
  local line
  line="$(grep -E "^${key}=" "${ROOT}/.env" 2>/dev/null | tail -n1 || true)"
  [[ -n "${line}" ]] || return 0
  printf '%s' "${line#*=}" | tr -d '\r'
}

autoupdate_interval() {
  local from_file="" from_env=""
  if [[ -f "${AUTOUPDATE_FILE}" ]]; then
    from_file="$(tr -d '[:space:]' <"${AUTOUPDATE_FILE}" || true)"
  fi
  from_env="$(env_get LORECHAT_AUTO_UPDATE_INTERVAL)"
  if [[ "${1:-}" =~ ^[0-9]+$ ]] && [[ "${1}" -ge 60 ]]; then
    echo "$1"
  elif [[ "${from_file}" =~ ^[0-9]+$ ]] && [[ "${from_file}" -ge 60 ]]; then
    echo "${from_file}"
  elif [[ "${from_env}" =~ ^[0-9]+$ ]] && [[ "${from_env}" -ge 60 ]]; then
    echo "${from_env}"
  else
    echo "300"
  fi
}

stop_watchtower() {
  if docker container inspect "${WATCHTOWER_NAME}" >/dev/null 2>&1; then
    docker rm -f "${WATCHTOWER_NAME}" >/dev/null 2>&1 || true
    echo "[Lore Chat] 已停止自动更新（${WATCHTOWER_NAME}）"
  fi
}

warn_autoupdate_tag() {
  local tag
  tag="$(env_get LORECHAT_IMAGE_TAG)"
  tag="${tag:-latest}"
  if [[ "${tag}" != "latest" ]]; then
    echo "[Lore Chat] 提示：当前 LORECHAT_IMAGE_TAG=${tag}；跟随 master 请改为 latest。"
  fi
}

ensure_watchtower() {
  [[ -f "${AUTOUPDATE_FILE}" ]] || return 0
  need_cmd docker
  local interval
  interval="$(autoupdate_interval)"
  printf '%s\n' "${interval}" >"${AUTOUPDATE_FILE}"
  warn_autoupdate_tag
  docker rm -f "${WATCHTOWER_NAME}" >/dev/null 2>&1 || true
  docker run -d \
    --name "${WATCHTOWER_NAME}" \
    --restart unless-stopped \
    -v /var/run/docker.sock:/var/run/docker.sock \
    "${WATCHTOWER_IMAGE}" \
    --cleanup \
    --interval "${interval}" \
    lorechat-backend lorechat-web >/dev/null
  echo "[Lore Chat] 自动更新已启用：每 ${interval}s 检查 lorechat-backend / lorechat-web"
}

do_autoupdate() {
  materialize_bundle
  local sub="${1:-status}"
  case "${sub}" in
    on|enable|start)
      local interval
      if [[ -n "${2:-}" ]]; then
        if ! [[ "${2}" =~ ^[0-9]+$ ]] || [[ "${2}" -lt 60 ]]; then
          echo "[Lore Chat] 间隔须为 ≥60 的秒数" >&2
          exit 1
        fi
      fi
      interval="$(autoupdate_interval "${2:-}")"
      mkdir -p "${RUNTIME}"
      printf '%s\n' "${interval}" >"${AUTOUPDATE_FILE}"
      ensure_watchtower
      ;;
    off|disable|stop)
      rm -f "${AUTOUPDATE_FILE}"
      stop_watchtower
      echo "[Lore Chat] 自动更新已关闭"
      ;;
    status|"" )
      if [[ -f "${AUTOUPDATE_FILE}" ]]; then
        local interval running="no"
        interval="$(autoupdate_interval)"
        if docker container inspect "${WATCHTOWER_NAME}" >/dev/null 2>&1; then
          running="yes"
        fi
        echo "[Lore Chat] 自动更新：on（间隔 ${interval}s；容器运行中: ${running}）"
        warn_autoupdate_tag
      else
        echo "[Lore Chat] 自动更新：off"
      fi
      ;;
    *)
      echo "[Lore Chat] 用法: ./lorechat.sh autoupdate on|off|status [间隔秒]" >&2
      exit 1
      ;;
  esac
}

do_start() {
  materialize_bundle
  local mode
  mode="$(resolve_mode "${1:-}")" || exit 1
  if [[ "${mode}" == "work" ]]; then
    warn_work_images
  fi
  echo "[Lore Chat] 正在启动（模式: ${mode}）..."
  echo "[Lore Chat] 数据目录 → ${LORECHAT_DATA_DIR}"
  if in_repo_deploy; then
    echo "[Lore Chat] 仓库内预构建启动器挂载 docker/data；热重载请用根目录 ./lorechat.sh start --dev"
  fi
  teardown_all
  if ! run_compose "${mode}" pull; then
    echo "[Lore Chat] 拉取镜像失败，将尝试使用本机已有镜像。" >&2
    echo "[Lore Chat] 若需跟随 GHCR：确认包为 Public，或 docker login ghcr.io" >&2
  fi
  run_compose "${mode}" up -d
  save_mode "${mode}"
  ensure_watchtower
  echo "[Lore Chat] 就绪 → http://localhost:$(web_port)"
  echo "[Lore Chat] 模式 → ${mode}；日志 → ./lorechat.sh log"
  if [[ -f "${AUTOUPDATE_FILE}" ]]; then
    echo "[Lore Chat] 自动更新 → on（./lorechat.sh autoupdate status）"
  else
    echo "[Lore Chat] 跟随 GHCR latest 可执行：./lorechat.sh autoupdate on"
  fi
  echo "[Lore Chat] 若尚未配置 API Key，打开页面后会引导填写。"
}

do_stop() {
  materialize_bundle
  stop_watchtower
  teardown_all
  echo "[Lore Chat] 已停止"
}

do_update() {
  local mode
  if [[ -n "${1:-}" ]]; then
    mode="$(resolve_mode "$1")" || exit 1
  else
    mode="$(read_saved_mode)"
  fi
  do_start "${mode}"
}

do_log() {
  materialize_bundle
  run_compose "$(read_saved_mode)" logs -f --tail=50
}

do_prepare() {
  materialize_bundle
  echo "[Lore Chat] 已写出 docker-compose.yml / sandbox / opensandbox/config.toml / .env.example"
  echo "[Lore Chat] 目录: ${ROOT}"
}

cmd="${1:-help}"
shift || true
case "${cmd}" in
  start) do_start "${1:-}" ;;
  stop) do_stop ;;
  update) do_update "${1:-}" ;;
  autoupdate) do_autoupdate "${1:-}" "${2:-}" ;;
  prepare) do_prepare ;;
  log|logs) do_log ;;
  help|-h|--help) usage ;;
  *)
    usage >&2
    exit 1
    ;;
esac
