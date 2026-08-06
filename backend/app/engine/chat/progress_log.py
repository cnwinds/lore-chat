"""时间线 / SSE 共用的 progress_log 追加逻辑。"""

from __future__ import annotations

_NOISE_PREFIX = "仍在运行…"
_MAX_PROGRESS_CHARS = 100_000


def is_noise_progress(message: str) -> bool:
    return (message or "").strip().startswith(_NOISE_PREFIX)


def append_progress_chunk(log: list[str], message: str) -> list[str]:
    """追加流式块：连续输出拼到同一缓冲项；返回新 list（可能原地改）。"""
    if not message or is_noise_progress(message):
        return log
    if (
        log
        and not message.startswith("$ ")
        and not message.lstrip().startswith("[exit ")
    ):
        log[-1] = log[-1] + message
    else:
        log.append(message)
    joined_len = sum(len(s) for s in log)
    if joined_len > _MAX_PROGRESS_CHARS:
        joined = "".join(log)
        return [joined[-_MAX_PROGRESS_CHARS:]]
    return log
