from __future__ import annotations

import re

from app.models.llm import LLMClient

_QUESTION_RE = re.compile(
    r"(怎么|如何|什么是|啥是|为什么|有没有|能否|可以吗|请问|哪[里个]|谁|多少|吗\s*$|[?？]\s*$)"
)


def _looks_like_question(text: str) -> bool:
    return bool(_QUESTION_RE.search(text))


def is_question_only(text: str) -> bool:
    """短句、单行、无代码块且含疑问词 → 纯提问，不应写入知识库。"""
    text = text.strip()
    if not text:
        return False
    short = len(text) <= 200
    return short and _looks_like_question(text) and "\n" not in text and "```" not in text


def classify_intent(text: str, llm: LLMClient) -> str:
    """返回 remember（记录）或 recall（提问）。"""
    text = text.strip()
    if not text:
        return "remember"

    if is_question_only(text):
        return "recall"

    messages = [
        {
            "role": "system",
            "content": (
                "判断用户意图，只输出一个词：recall 或 remember。\n"
                "recall：在提问、查询、检索已有知识（即使没写问号）。\n"
                "remember：在分享资料、记录笔记、粘贴教程/命令/代码/长文希望保存。"
            ),
        },
        {"role": "user", "content": text},
    ]
    raw = llm.chat(messages, temperature=0).strip().lower()
    if raw.startswith("recall") or raw == "recall":
        return "recall"
    return "remember"
