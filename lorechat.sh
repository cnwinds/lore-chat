#!/usr/bin/env bash
# Lore Chat control script for Linux / macOS
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="${ROOT}/.lorechat"
BACKEND_DIR="${ROOT}/backend"
FRONTEND_DIR="${ROOT}/frontend"
LOG="${RUNTIME}/web.log"
MODE_FILE="${RUNTIME}/mode.txt"
COMPOSE_FILE="${ROOT}/docker/docker-compose.yml"

LORECHAT_BACKEND_PORT="${LORECHAT_BACKEND_PORT:-8000}"
LORECHAT_FRONTEND_PORT="${LORECHAT_FRONTEND_PORT:-5173}"

PYTHON="${BACKEND_DIR}/.venv/bin/python"

usage() {
  cat <<'EOF'
Usage: ./lorechat.sh <command>

Commands:
  setup     Create backend venv, install deps, copy env examples
  dev       Development mode (uvicorn --reload + Vite HMR)
  start     Production via Docker Compose
  stop      Stop Docker Compose stack (or local dev helpers)
  restart   stop then start (or re-run last mode)
  log|logs  Tail Docker Compose logs (or local .lorechat/web.log)
  help      Show this help

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
    echo "[Lore Chat] Created backend/.env from .env.example — set OPENAI_API_KEY"
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

compose() {
  need_cmd docker
  if ! docker compose version >/dev/null 2>&1; then
    echo "[Lore Chat] Docker Compose plugin required (docker compose)" >&2
    exit 1
  fi
  if [[ ! -f "${ROOT}/.env" ]]; then
    echo "[Lore Chat] Root .env missing. Copy .env.docker.example → .env and set OPENAI_API_KEY" >&2
    exit 1
  fi
  docker compose --project-directory "${ROOT}/docker" --env-file "${ROOT}/.env" -f "${COMPOSE_FILE}" "$@"
}

do_start() {
  ensure_runtime
  echo "start" >"${MODE_FILE}"
  echo "[Lore Chat] Starting Docker Compose ..."
  compose up -d --build
  local port
  port="$(grep -E '^WEB_PORT=' "${ROOT}/.env" 2>/dev/null | cut -d= -f2- || true)"
  port="${port:-8080}"
  echo "[Lore Chat] Ready → http://localhost:${port}"
  echo "[Lore Chat] Logs  → ./lorechat.sh log"
}

do_stop() {
  ensure_runtime
  if [[ -f "${ROOT}/.env" ]] && command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    compose down || true
  fi
  # Best-effort: stop lingering local dev listeners
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
  if [[ -f "${MODE_FILE}" ]]; then
    mode="$(tr -d '[:space:]' <"${MODE_FILE}")"
  fi
  do_stop
  sleep 1
  if [[ "${mode}" == "dev" ]]; then
    do_dev
  else
    do_start
  fi
}

do_log() {
  if [[ -f "${ROOT}/.env" ]] && command -v docker >/dev/null 2>&1; then
    compose logs -f --tail=50
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
case "${cmd}" in
  setup) do_setup ;;
  dev) do_dev ;;
  start) do_start ;;
  stop) do_stop ;;
  restart) do_restart ;;
  log|logs) do_log ;;
  help|-h|--help) usage ;;
  *)
    usage >&2
    exit 1
    ;;
esac
