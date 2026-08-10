from __future__ import annotations

from app.engine.agent.prompts import build_system_prompt


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
    skill_roots: list[str] | None = None,
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
    tray_lines: list[str] = []
    for p in paths:
        suffix = "（主文档，默认编辑目标）" if p == primary else "（参考文档）"
        tray_lines.append(f"- {p}{suffix}")
    for root in skill_roots or []:
        label = root or "(根目录)"
        tray_lines.append(f"- {label}（Skill 包）")
    if tray_lines:
        messages.append(
            {
                "role": "system",
                "content": "[上下文] 用户当前文档托盘：\n" + "\n".join(tray_lines),
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
