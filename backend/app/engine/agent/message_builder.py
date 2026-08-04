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
    if paths:
        lines = []
        for p in paths:
            suffix = "（主文档，默认编辑目标）" if p == primary else "（参考上下文）"
            lines.append(f"- {p}{suffix}")
        messages.append(
            {
                "role": "system",
                "content": "[上下文] 用户当前文档托盘：\n" + "\n".join(lines),
            }
        )
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_text})
    return messages
