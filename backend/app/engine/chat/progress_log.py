"""时间线 / SSE 共用的 progress_log 追加逻辑。"""

from __future__ import annotations

_NOISE_PREFIX = "仍在运行…"
_MAX_PROGRESS_CHARS = 100_000


def is_noise_progress(message: str) -> bool:
    return (message or "").strip().startswith(_NOISE_PREFIX)


def normalize_stream_chunk(message: str) -> str:
    """规范化终端流片段：统一换行，行级回调补尾 \\n。"""
    if not message:
        return message
    # 进度条类 \\r 覆盖在 HTML <pre> 里只会乱，改成换行
    text = message.replace("\r\n", "\n").replace("\r", "\n")
    return text


def ensure_line_chunk(message: str) -> str:
    """OpenSandbox 常按行回调且不带尾换行；补上以便拼接/展示。"""
    text = normalize_stream_chunk(message)
    if not text:
        return text
    if text.endswith("\n"):
        return text
    # 已含多行内容时保留原样；单行/无换行则视为一行
    if "\n" not in text:
        return text + "\n"
    return text


def _needs_sep(prev: str, nxt: str) -> bool:
    if not prev or not nxt:
        return False
    if prev.endswith("\n") or nxt.startswith("\n"):
        return False
    return True


def append_progress_chunk(log: list[str], message: str) -> list[str]:
    """追加流式块：连续输出拼到同一缓冲项；必要时插入换行。"""
    text = normalize_stream_chunk(message)
    if not text or is_noise_progress(text):
        return log
    if (
        log
        and not text.startswith("$ ")
        and not text.lstrip().startswith("[exit ")
    ):
        prev = log[-1]
        sep = "\n" if _needs_sep(prev, text) else ""
        log[-1] = prev + sep + text
    else:
        log.append(text)
    joined_len = sum(len(s) for s in log)
    if joined_len > _MAX_PROGRESS_CHARS:
        joined = "".join(log)
        return [joined[-_MAX_PROGRESS_CHARS:]]
    return log
