from __future__ import annotations

from pathlib import PurePosixPath

from app.engine.agent.prompt_parts import PARTS_KEY, copy_tag_history, speaker_label, tag
from app.engine.agent.prompts import (
    build_system_prompt_parts,
    current_time_block,
    wrap_turn_cards,
)
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
    role_system_prompt: str = "",
    role_cards: str = "",
    turn_cards: str = "",
) -> list[dict]:
    sys_parts = build_system_prompt_parts(
        mode,
        system_layer_text,
        user_memory,
        role_system_prompt=role_system_prompt,
        role_cards=role_cards,
    )
    messages: list[dict] = [
        {
            "role": "system",
            "content": "".join(p["text"] for p in sys_parts),
            PARTS_KEY: sys_parts,
        },
    ]
    paths = list(active_doc_paths or [])
    primary = primary_doc_path or active_doc_path
    if active_doc_path and active_doc_path not in paths:
        if not paths:
            paths = [active_doc_path]
    tray_lines = [_tray_entry_label(p, primary) for p in paths]
    if tray_lines:
        tray_content = (
            "【工作托盘】\n\n"
            "下列路径为本轮主要工作对象；"
            "目录表示优先在该目录范围内检索与读写。\n\n"
            + "\n".join(tray_lines)
        )
        messages.append(
            tag(
                {"role": "system", "content": tray_content},
                "tray",
                label="工作托盘",
                text=tray_content,
            )
        )
    if extra_system_messages:
        for raw in extra_system_messages:
            msg = dict(raw)
            if PARTS_KEY not in msg:
                content = str(msg.get("content") or "")
                tag(msg, "extra", text=content)
            messages.append(msg)
    if history:
        for h in history:
            messages.append(copy_tag_history(h))
    # 当前时间逐轮变化，放整条提示词最末（本轮用户消息最前），保住前缀缓存
    prefix = [current_time_block()]
    block = wrap_turn_cards(turn_cards)
    if block:
        prefix.append(block)
    user_content = "\n\n".join([*prefix, user_text])
    user_parts: list[dict] = [
        {"kind": "time", "label": "当前时间", "text": prefix[0]},
    ]
    if block:
        user_parts.append({"kind": "turn_cards", "label": "相关知识卡", "text": block})
    user_parts.append(
        {
            "kind": "user_text",
            "label": speaker_label(user_text, "user"),
            "text": user_text,
        }
    )
    user_msg: dict = {
        "role": "user",
        "content": user_content,
        PARTS_KEY: user_parts,
    }
    if attachments:
        user_msg["attachments"] = list(attachments)
    messages.append(user_msg)
    return messages
