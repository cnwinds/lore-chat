# shellcheck shell=bash
# 共享：chat/work 栈模式解析、沙箱镜像缓存探测、compose 编排。
# 仅由仓库根 lorechat.sh source。预构建单文件启动器由 gen-deploy-launchers.py
# 内嵌同等逻辑，不 source 本文件。
#
# 调用方须先设置：
#   LORECHAT_RUNTIME          .lorechat 目录
#   LORECHAT_COMPOSE_DIR      compose --project-directory
#   LORECHAT_COMPOSE_ENV      --env-file 路径
#   LORECHAT_COMPOSE_BASE     基础 compose 文件
#   LORECHAT_COMPOSE_SANDBOX  sandbox 叠加文件
#   LORECHAT_DEFAULT_SANDBOX_IMAGE  默认业务沙箱镜像（无 .env 时）
#
# 可选：
#   LORECHAT_STACK_MODE_FILE  默认 ${LORECHAT_RUNTIME}/run-mode
#   LORECHAT_COMPOSE_DEMO=1   叠加 docker-compose.demo.yml（演示站）
#   LORECHAT_COMPOSE_DEMO_FILE  demo 叠加文件路径

# 镜像 pin：scripts/opensandbox-pins.sh（由 gen-deploy-launchers.py 从 config.toml / sandbox compose 生成）
# shellcheck source=opensandbox-pins.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/opensandbox-pins.sh"

lorechat_stack_mode_file() {
  echo "${LORECHAT_STACK_MODE_FILE:-${LORECHAT_RUNTIME}/run-mode}"
}

lorechat_read_stack_mode() {
  local f legacy
  f="$(lorechat_stack_mode_file)"
  legacy="${LORECHAT_RUNTIME}/stack-mode.txt"
  if [[ ! -f "${f}" && -f "${legacy}" ]]; then
    f="${legacy}"
  fi
  if [[ -f "${f}" ]]; then
    tr -d '[:space:]' <"${f}"
  else
    echo "chat"
  fi
}

lorechat_save_stack_mode() {
  mkdir -p "${LORECHAT_RUNTIME}"
  printf '%s\n' "$1" >"$(lorechat_stack_mode_file)"
}

lorechat_pick_stack_mode_interactive() {
  local saved default_idx=1 choice
  saved="$(lorechat_read_stack_mode)"
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

# $1 = flag（可空 / --chat / --work / chat / work）
lorechat_resolve_stack_mode() {
  local flag="${1:-}"
  case "${flag}" in
    --chat|chat) echo "chat" ;;
    --work|work) echo "work" ;;
    "")
      if [[ -t 0 ]]; then
        lorechat_pick_stack_mode_interactive
      else
        lorechat_read_stack_mode
      fi
      ;;
    *)
      echo "[Lore Chat] 未知模式: ${flag}（用 --chat 或 --work）" >&2
      return 1
      ;;
  esac
}

lorechat_sandbox_image_ref() {
  local from_env=""
  if [[ -n "${LORECHAT_COMPOSE_ENV:-}" && -f "${LORECHAT_COMPOSE_ENV}" ]]; then
    from_env="$(grep -E '^SANDBOX_IMAGE=' "${LORECHAT_COMPOSE_ENV}" 2>/dev/null | cut -d= -f2- | tr -d '\r' || true)"
  fi
  if [[ -n "${from_env}" ]]; then
    echo "${from_env}"
  else
    echo "${SANDBOX_IMAGE:-${LORECHAT_DEFAULT_SANDBOX_IMAGE}}"
  fi
}

lorechat_docker_image_present() {
  docker image inspect "$1" >/dev/null 2>&1
}

# Work 相关镜像均已在本地则为真（含 config.toml 中的 execd / egress）
lorechat_work_images_cached() {
  local agent
  agent="$(lorechat_sandbox_image_ref)"
  lorechat_docker_image_present "${LORECHAT_OPENSANDBOX_SERVER_IMAGE}" \
    && lorechat_docker_image_present "${agent}" \
    && lorechat_docker_image_present "${LORECHAT_OPENSANDBOX_EXECD_IMAGE}" \
    && lorechat_docker_image_present "${LORECHAT_OPENSANDBOX_EGRESS_IMAGE}"
}

lorechat_warn_work_images() {
  if lorechat_work_images_cached; then
    echo "[Lore Chat] Work 模式：本机已有沙箱相关镜像，将按需检查更新。"
    return
  fi
  echo "[Lore Chat] Work 模式将额外拉取沙箱相关镜像（opensandbox/server、execd、egress、sandbox-agent 等）。"
  echo "[Lore Chat] 首次下载可能较慢，请耐心等待。"
}

# $1 = chat|work；其余为 compose 参数。
# LORECHAT_COMPOSE_DEV=1 → docker-compose.dev.yml
# LORECHAT_COMPOSE_DEMO=1 → docker-compose.demo.yml
lorechat_compose() {
  local mode="$1"
  shift
  local -a files=(-f "${LORECHAT_COMPOSE_BASE}")
  if [[ "${mode}" == "work" ]]; then
    files+=(-f "${LORECHAT_COMPOSE_SANDBOX}")
  fi
  if [[ "${LORECHAT_COMPOSE_DEMO:-}" == "1" ]]; then
    files+=(-f "${LORECHAT_COMPOSE_DEMO_FILE:-${LORECHAT_COMPOSE_DIR}/docker-compose.demo.yml}")
  fi
  if [[ "${LORECHAT_COMPOSE_DEV:-}" == "1" ]]; then
    files+=(-f "${LORECHAT_COMPOSE_DEV_FILE:-${LORECHAT_COMPOSE_DIR}/docker-compose.dev.yml}")
  fi
  docker compose \
    --project-directory "${LORECHAT_COMPOSE_DIR}" \
    --env-file "${LORECHAT_COMPOSE_ENV}" \
    "${files[@]}" \
    "$@"
}

lorechat_teardown_stack() {
  # demo 叠加与否不影响同名项目 down；两套都试一遍清干净。
  LORECHAT_COMPOSE_DEMO=1 lorechat_compose work down --remove-orphans >/dev/null 2>&1 || true
  LORECHAT_COMPOSE_DEMO=1 lorechat_compose chat down --remove-orphans >/dev/null 2>&1 || true
  lorechat_compose work down --remove-orphans >/dev/null 2>&1 || true
  lorechat_compose chat down --remove-orphans >/dev/null 2>&1 || true
}
