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
LORECHAT_DEFAULT_SANDBOX_IMAGE="lorechat-sandbox-agent:local"

usage() {
  cat <<'EOF'
Usage: ./lorechat.sh <command> [options]

Commands:
  setup                   Create backend venv, install deps, copy env examples
  dev                     Development mode (uvicorn --reload + Vite HMR)
  start [--chat|--work]   Production via Docker Compose (local build)
  stop                    Stop Docker Compose stack (or local dev helpers)
  restart                 stop then start (or re-run last mode)
  log|logs                Tail Docker Compose logs (or local .lorechat/web.log)
  help                    Show this help

Modes (start):
  --chat   Core stack only (default)
  --work   Core + OpenSandbox (first run may pull large images)

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

do_start() {
  ensure_runtime
  ensure_docker_compose
  local stack_mode
  stack_mode="$(lorechat_resolve_stack_mode "${1:-}")" || exit 1
  if [[ "${stack_mode}" == "work" ]]; then
    lorechat_warn_work_images
  fi
  echo "start" >"${MODE_FILE}"
  lorechat_save_stack_mode "${stack_mode}"
  echo "[Lore Chat] Starting Docker Compose (mode: ${stack_mode}, local --build) ..."
  lorechat_teardown_stack
  lorechat_compose "${stack_mode}" up -d --build
  local port
  port="$(grep -E '^WEB_PORT=' "${ROOT}/.env" 2>/dev/null | cut -d= -f2- || true)"
  port="${port:-8080}"
  echo "[Lore Chat] Ready → http://localhost:${port}"
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
  rm -f "${MODE_FILE}"
  echo "[Lore Chat] Stopped"
}

do_restart() {
  local mode="start"
  local stack_mode
  stack_mode="$(lorechat_read_stack_mode)"
  if [[ -f "${MODE_FILE}" ]]; then
    mode="$(tr -d '[:space:]' <"${MODE_FILE}")"
  fi
  do_stop
  sleep 1
  if [[ "${mode}" == "dev" ]]; then
    do_dev
  else
    do_start "${stack_mode}"
  fi
}

do_log() {
  if [[ -f "${ROOT}/.env" ]] && command -v docker >/dev/null 2>&1; then
    ensure_docker_compose
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
  start) do_start "${1:-}" ;;
  stop) do_stop ;;
  restart) do_restart ;;
  log|logs) do_log ;;
  help|-h|--help) usage ;;
  *)
    usage >&2
    exit 1
    ;;
esac
