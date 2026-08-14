#!/usr/bin/env bash
# Lore Chat control script for Linux / macOS
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="${ROOT}/.lorechat"
BACKEND_DIR="${ROOT}/backend"
FRONTEND_DIR="${ROOT}/frontend"
LOG="${RUNTIME}/web.log"
MODE_FILE="${RUNTIME}/mode.txt"

LORECHAT_BACKEND_PORT="${LORECHAT_BACKEND_PORT:-8000}"
LORECHAT_FRONTEND_PORT="${LORECHAT_FRONTEND_PORT:-5173}"
PYTHON="${BACKEND_DIR}/.venv/bin/python"

# shellcheck source=scripts/lorechat-compose-lib.sh
source "${ROOT}/scripts/lorechat-compose-lib.sh"
LORECHAT_RUNTIME="${RUNTIME}"
LORECHAT_COMPOSE_DIR="${ROOT}/docker"
LORECHAT_COMPOSE_ENV="${ROOT}/.env"
LORECHAT_COMPOSE_BASE="${ROOT}/docker/docker-compose.yml"
LORECHAT_COMPOSE_SANDBOX="${ROOT}/docker/docker-compose.sandbox.yml"
LORECHAT_COMPOSE_DEV_FILE="${ROOT}/docker/docker-compose.dev.yml"
LORECHAT_DEFAULT_SANDBOX_IMAGE="lorechat-sandbox-agent:local"
COMPOSE_DEV_FILE="${RUNTIME}/compose-dev"
PROXY_RELAY_PID_FILE="${RUNTIME}/proxy-relay.pid"
PROXY_RELAY_LOG="${RUNTIME}/proxy-relay.log"

usage() {
  cat <<'EOF'
Usage: ./lorechat.sh <command> [options]

Commands:
  setup                   Create backend venv, install deps, copy env examples
  dev                     Host development (uvicorn --reload + Vite HMR)
  start [--chat|--work] [--dev]
                          Docker Compose (local build); --dev mounts source + hot reload
  stop                    Stop Docker Compose stack (or local dev helpers)
  restart                 stop then start (or re-run last mode)
  log|logs                Tail Docker Compose logs (or local .lorechat/web.log)
  help                    Show this help

Modes (start):
  --chat   Core stack only (default)
  --work   Core + OpenSandbox (first run may pull large images)
  --dev    Bind-mount backend/frontend; uvicorn --reload + Vite HMR (no rebuild on edit)

Environment:
  LORECHAT_BACKEND_PORT   default 8000
  LORECHAT_FRONTEND_PORT  default 5173
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[Lore Chat] Missing required command: $1" >&2
    exit 1
  fi
}

ensure_runtime() {
  mkdir -p "${RUNTIME}"
}

# 读 .env 中的 KEY=VALUE（忽略注释/空行）；无则空
_lorechat_env_get() {
  local key="$1"
  [[ -f "${ROOT}/.env" ]] || return 0
  local line
  line="$(grep -E "^${key}=" "${ROOT}/.env" 2>/dev/null | tail -n1 || true)"
  [[ -n "${line}" ]] || return 0
  printf '%s' "${line#*=}"
}

# WSL/本机 Clash 仅监听 127.0.0.1 时，为 Docker 起 0.0.0.0 转发
ensure_proxy_relay() {
  local enabled target listen
  enabled="$(_lorechat_env_get LORECHAT_HOST_PROXY_RELAY)"
  [[ "${enabled}" == "1" || "${enabled}" == "true" ]] || return 0

  target="$(_lorechat_env_get LORECHAT_PROXY_RELAY_TARGET)"
  listen="$(_lorechat_env_get LORECHAT_PROXY_RELAY_LISTEN)"
  target="${target:-127.0.0.1:7897}"
  listen="${listen:-0.0.0.0:17897}"

  if [[ -f "${PROXY_RELAY_PID_FILE}" ]]; then
    local old
    old="$(tr -d '[:space:]' <"${PROXY_RELAY_PID_FILE}" || true)"
    if [[ -n "${old}" ]] && kill -0 "${old}" 2>/dev/null; then
      echo "[Lore Chat] Proxy relay already running (pid ${old}): ${listen} → ${target}"
      return 0
    fi
    rm -f "${PROXY_RELAY_PID_FILE}"
  fi

  need_cmd python3
  nohup python3 "${ROOT}/scripts/host-proxy-relay.py" \
    --listen "${listen}" \
    --target "${target}" \
    >>"${PROXY_RELAY_LOG}" 2>&1 &
  echo $! >"${PROXY_RELAY_PID_FILE}"
  sleep 0.3
  if kill -0 "$(tr -d '[:space:]' <"${PROXY_RELAY_PID_FILE}")" 2>/dev/null; then
    echo "[Lore Chat] Proxy relay: ${listen} → ${target}"
  else
    echo "[Lore Chat] Proxy relay failed to start; see ${PROXY_RELAY_LOG}" >&2
    rm -f "${PROXY_RELAY_PID_FILE}"
  fi
}

stop_proxy_relay() {
  [[ -f "${PROXY_RELAY_PID_FILE}" ]] || return 0
  local pid
  pid="$(tr -d '[:space:]' <"${PROXY_RELAY_PID_FILE}" || true)"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
    echo "[Lore Chat] Proxy relay stopped"
  fi
  rm -f "${PROXY_RELAY_PID_FILE}"
}

do_setup() {
  need_cmd python3
  need_cmd npm
  need_cmd node

  local pyver
  pyver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' || {
    echo "[Lore Chat] Python 3.12+ required (found ${pyver})" >&2
    exit 1
  }

  if [[ ! -x "${PYTHON}" ]]; then
    echo "[Lore Chat] Creating backend/.venv ..."
    python3 -m venv "${BACKEND_DIR}/.venv"
  fi

  echo "[Lore Chat] Installing backend requirements ..."
  "${PYTHON}" -m pip install -U pip
  "${PYTHON}" -m pip install -r "${BACKEND_DIR}/requirements.txt"

  if [[ ! -f "${BACKEND_DIR}/.env" ]]; then
    cp "${BACKEND_DIR}/.env.example" "${BACKEND_DIR}/.env"
    echo "[Lore Chat] Created backend/.env from .env.example — set OPENAI_API_KEY (or use web Settings)"
  fi

  if [[ ! -f "${FRONTEND_DIR}/.env" ]]; then
    cp "${FRONTEND_DIR}/.env.example" "${FRONTEND_DIR}/.env"
    echo "[Lore Chat] Created frontend/.env from .env.example"
  fi

  echo "[Lore Chat] Installing frontend dependencies ..."
  (cd "${FRONTEND_DIR}" && npm install)

  echo "[Lore Chat] Setup complete. Next: ./lorechat.sh dev"
}

do_dev() {
  ensure_runtime
  need_cmd node
  if [[ ! -x "${PYTHON}" ]]; then
    echo "[Lore Chat] Backend venv missing. Run: ./lorechat.sh setup" >&2
    exit 1
  fi
  if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    echo "[Lore Chat] Frontend node_modules missing. Run: ./lorechat.sh setup" >&2
    exit 1
  fi
  if [[ ! -f "${BACKEND_DIR}/.env" ]]; then
    echo "[Lore Chat] backend/.env missing. Run: ./lorechat.sh setup" >&2
    exit 1
  fi

  echo "dev" >"${MODE_FILE}"
  echo "[Lore Chat] Dev → http://localhost:${LORECHAT_FRONTEND_PORT} (API :${LORECHAT_BACKEND_PORT})"
  cd "${FRONTEND_DIR}"
  exec node scripts/dev.mjs
}

ensure_docker_compose() {
  need_cmd docker
  if ! docker compose version >/dev/null 2>&1; then
    echo "[Lore Chat] Docker Compose plugin required (docker compose)" >&2
    exit 1
  fi
  if [[ ! -f "${ROOT}/.env" ]]; then
    echo "[Lore Chat] Root .env missing. Copy .env.docker.example → .env (API Key optional; web Settings OK)" >&2
    exit 1
  fi
}

# 解析 start 参数：--chat|--work 与可选 --dev（顺序不限）
lorechat_parse_start_args() {
  local stack_flag=""
  LORECHAT_COMPOSE_DEV=0
  local arg
  for arg in "$@"; do
    case "${arg}" in
      --dev|dev) LORECHAT_COMPOSE_DEV=1 ;;
      --chat|chat|--work|work|"")
        if [[ -n "${stack_flag}" && -n "${arg}" ]]; then
          echo "[Lore Chat] 只能指定一个栈模式（--chat 或 --work）" >&2
          return 1
        fi
        stack_flag="${arg}"
        ;;
      *)
        echo "[Lore Chat] 未知参数: ${arg}（用 --chat / --work / --dev）" >&2
        return 1
        ;;
    esac
  done
  lorechat_resolve_stack_mode "${stack_flag}"
}

do_start() {
  ensure_runtime
  ensure_docker_compose
  local stack_mode
  stack_mode="$(lorechat_parse_start_args "$@")" || exit 1
  export LORECHAT_COMPOSE_DEV
  if [[ "${stack_mode}" == "work" ]]; then
    lorechat_warn_work_images
  fi
  ensure_proxy_relay
  echo "start" >"${MODE_FILE}"
  lorechat_save_stack_mode "${stack_mode}"
  if [[ "${LORECHAT_COMPOSE_DEV}" == "1" ]]; then
    echo "1" >"${COMPOSE_DEV_FILE}"
    echo "[Lore Chat] Starting Docker Compose (mode: ${stack_mode}, --dev hot-reload) ..."
  else
    rm -f "${COMPOSE_DEV_FILE}"
    echo "[Lore Chat] Starting Docker Compose (mode: ${stack_mode}, local --build) ..."
  fi
  lorechat_teardown_stack
  # 开发叠加用预构建/已有镜像挂载源码即可；仍 --build 以同步 Dockerfile 依赖
  lorechat_compose "${stack_mode}" up -d --build
  local port
  port="$(grep -E '^WEB_PORT=' "${ROOT}/.env" 2>/dev/null | cut -d= -f2- || true)"
  port="${port:-8080}"
  echo "[Lore Chat] Ready → http://localhost:${port}"
  if [[ "${LORECHAT_COMPOSE_DEV}" == "1" ]]; then
    echo "[Lore Chat] Dev mounts: backend/app → uvicorn --reload；frontend → Vite HMR"
  fi
  echo "[Lore Chat] Logs  → ./lorechat.sh log"
}

do_stop() {
  ensure_runtime
  if [[ -f "${ROOT}/.env" ]] && command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    lorechat_teardown_stack
  fi
  if command -v lsof >/dev/null 2>&1; then
    for port in "${LORECHAT_BACKEND_PORT}" "${LORECHAT_FRONTEND_PORT}"; do
      local pids
      pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
      if [[ -n "${pids}" ]]; then
        # shellcheck disable=SC2086
        kill ${pids} 2>/dev/null || true
      fi
    done
  fi
  stop_proxy_relay
  rm -f "${MODE_FILE}"
  echo "[Lore Chat] Stopped"
}

do_restart() {
  local mode="start"
  local stack_mode
  local -a start_args=()
  stack_mode="$(lorechat_read_stack_mode)"
  if [[ -f "${MODE_FILE}" ]]; then
    mode="$(tr -d '[:space:]' <"${MODE_FILE}")"
  fi
  do_stop
  sleep 1
  if [[ "${mode}" == "dev" ]]; then
    do_dev
  else
    start_args=("--${stack_mode}")
    if [[ -f "${COMPOSE_DEV_FILE}" ]] && [[ "$(tr -d '[:space:]' <"${COMPOSE_DEV_FILE}")" == "1" ]]; then
      start_args+=(--dev)
    fi
    do_start "${start_args[@]}"
  fi
}

do_log() {
  if [[ -f "${ROOT}/.env" ]] && command -v docker >/dev/null 2>&1; then
    ensure_docker_compose
    if [[ -f "${COMPOSE_DEV_FILE}" ]] && [[ "$(tr -d '[:space:]' <"${COMPOSE_DEV_FILE}")" == "1" ]]; then
      export LORECHAT_COMPOSE_DEV=1
    fi
    lorechat_compose "$(lorechat_read_stack_mode)" logs -f --tail=50
    return
  fi
  if [[ -f "${LOG}" ]]; then
    tail -n 50 -f "${LOG}"
    return
  fi
  echo "[Lore Chat] No Docker stack or log file. Start with: ./lorechat.sh start" >&2
  exit 1
}

cmd="${1:-help}"
shift || true
case "${cmd}" in
  setup) do_setup ;;
  dev) do_dev ;;
  start) do_start "$@" ;;
  stop) do_stop ;;
  restart) do_restart ;;
  log|logs) do_log ;;
  help|-h|--help) usage ;;
  *)
    usage >&2
    exit 1
    ;;
esac
