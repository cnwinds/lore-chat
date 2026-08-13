from __future__ import annotations

from pathlib import PurePosixPath

from app.engine.agent.prompts import build_system_prompt
from app.engine.knowledge_writer import is_markdown_path
from app.storage.kb_text_files import is_kb_text_file


def _looks_like_file_path(path: str) -> bool:
    """托盘展示启发：有扩展名或为允许的文本文件名 → 文件；否则 → 工作目录。"""
    name = PurePosixPath(path.replace("\\", "/")).name
    if is_markdown_path(name) or is_kb_text_file(name):
        return True
    return bool(PurePosixPath(name).suffix)


def _tray_entry_label(path: str, primary: str | None) -> str:
    if _looks_like_file_path(path):
        if path == primary:
            return f"- {path}（主文档，默认编辑目标）"
        return f"- {path}（参考）"
    return f"- {path}（工作目录）"


def build_agent_messages(
    user_text: str,
    *,
    mode: str,
    web_enabled: bool,
    system_layer_text: str,
    user_memory: str,
    history: list[dict] | None,
    active_doc_path: str | None,
    active_doc_paths: list[str] | None,
    primary_doc_path: str | None,
    extra_system_messages: list[dict] | None = None,
    attachments: list[str] | None = None,
) -> list[dict]:
    messages: list[dict] = [
        {
            "role": "system",
            "content": build_system_prompt(
                mode, system_layer_text, web_enabled, user_memory
            ),
        },
    ]
    paths = list(active_doc_paths or [])
    primary = primary_doc_path or active_doc_path
    if active_doc_path and active_doc_path not in paths:
        if not paths:
            paths = [active_doc_path]
    tray_lines = [_tray_entry_label(p, primary) for p in paths]
    if tray_lines:
        messages.append(
            {
                "role": "system",
                "content": (
                    "[上下文] 用户当前工作托盘：下列路径为本轮主要工作对象"
                    "（目录表示优先在该目录范围内检索与读写）。\n"
                    + "\n".join(tray_lines)
                ),
            }
        )
    if extra_system_messages:
        messages.extend(extra_system_messages)
    if history:
        messages.extend(history)
    user_msg: dict = {"role": "user", "content": user_text}
    if attachments:
        user_msg["attachments"] = list(attachments)
    messages.append(user_msg)
    return messages
