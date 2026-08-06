"""时间线 / SSE 共用的 progress_log 追加逻辑。"""

from __future__ import annotations

import re

_NOISE_PREFIX = "仍在运行…"
_MAX_PROGRESS_CHARS = 100_000

# CSI / OSC / 其它 ESC 序列
_ANSI_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_ANSI_CSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_ANSI_OTHER = re.compile(r"\x1b.")
# 光标回行 / 清行类，按「覆盖当前行」处理
_REDRAW_CSI = re.compile(r"\x1b\[[0-9;]*[GJK]")
_HAS_REDRAW = re.compile(r"\r|\x1b\[[0-9;]*[GJK]")
# 已落库的刷屏进度行（展示时折叠）
_PROGRESS_LINE = re.compile(
    r"(?:Downloading|Rendering|Uploading|Progress|◐|◓|◑|◒|█|░|\d+(?:\.\d+)?%)",
    re.I,
)


def is_noise_progress(message: str) -> bool:
    return (message or "").strip().startswith(_NOISE_PREFIX)


def sanitize_controls(message: str) -> str:
    """把终端重绘序列映射为 \\r，并剥离其余 ANSI；保留 \\r / \\n。"""
    if not message:
        return message
    text = message.replace("\r\n", "\n")
    # 先把回行/清屏类 CSI 变成 \\r，再剥掉其它控制符
    text = _REDRAW_CSI.sub("\r", text)
    text = _ANSI_OSC.sub("", text)
    text = _ANSI_CSI.sub("", text)
    text = _ANSI_OTHER.sub("", text)
    return text


def apply_carriage_returns(text: str) -> str:
    """在每一逻辑行内应用 \\r 覆盖写。"""
    if not text or "\r" not in text:
        return text
    ended = text.endswith("\n")
    parts = text.split("\n")
    out: list[str] = []
    for line in parts:
        if "\r" not in line:
            out.append(line)
            continue
        cur = ""
        for piece in line.split("\r"):
            if len(piece) >= len(cur):
                cur = piece
            else:
                cur = piece + cur[len(piece) :]
        out.append(cur)
    result = "\n".join(out)
    if ended and not result.endswith("\n"):
        result += "\n"
    return result


def _progress_fingerprint(line: str) -> str:
    s = re.sub(r"[\d.]+", "0", line)
    s = re.sub(r"[◐◓◑◒✓]", "", s)
    return s.strip()


def collapse_repeated_progress(text: str) -> str:
    """连续同类进度行只留最后一条（兼容已落库的刷屏数据）。"""
    if not text or "\n" not in text:
        return text
    ended = text.endswith("\n")
    lines = text.split("\n")
    out: list[str] = []
    for line in lines:
        if (
            out
            and line
            and _PROGRESS_LINE.search(line)
            and _PROGRESS_LINE.search(out[-1])
            and _progress_fingerprint(line) == _progress_fingerprint(out[-1])
        ):
            out[-1] = line
            continue
        out.append(line)
    result = "\n".join(out)
    if ended and not result.endswith("\n"):
        result += "\n"
    return result


def normalize_stream_chunk(message: str) -> str:
    """规范化终端流片段：剥 ANSI、应用 \\r、折叠进度刷屏。"""
    if not message:
        return message
    text = apply_carriage_returns(sanitize_controls(message))
    return collapse_repeated_progress(text)


def ensure_line_chunk(message: str) -> str:
    """OpenSandbox 常按行回调且不带尾换行；补上以便拼接/展示。

    含 \\r / 光标回行 CSI 的重绘帧不加尾换行，避免进度条刷成成千上万行。
    """
    raw = message or ""
    is_redraw = bool(_HAS_REDRAW.search(raw))
    text = sanitize_controls(raw)
    if not text:
        return text
    if is_redraw:
        return text
    if text.endswith("\n"):
        return text
    if "\n" not in text:
        return text + "\n"
    return text


def _needs_sep(prev: str, nxt: str) -> bool:
    if not prev or not nxt:
        return False
    if prev.endswith("\n") or nxt.startswith("\n"):
        return False
    return True


def _merge_chunk(prev: str, text: str) -> str:
    """合并一块输出；开头的 \\r 覆盖上一行（即使上一行已有尾换行）。"""
    if text.startswith("\r"):
        text = text.lstrip("\r")
        body = prev[:-1] if prev.endswith("\n") else prev
        head, sep, _last = body.rpartition("\n")
        prev = head + sep
        merged = prev + text
    else:
        sep = "\n" if _needs_sep(prev, text) else ""
        merged = prev + sep + text
    return collapse_repeated_progress(apply_carriage_returns(merged))


def append_progress_chunk(log: list[str], message: str) -> list[str]:
    """追加流式块：连续输出拼到同一缓冲项；必要时插入换行。"""
    # 保留 \\r，供跨块覆盖；展示路径再 normalize
    text = sanitize_controls(message)
    if not text or is_noise_progress(text):
        return log
    if (
        log
        and not text.startswith("$ ")
        and not text.lstrip().startswith("[exit ")
    ):
        log = [*log[:-1], _merge_chunk(log[-1], text)]
    else:
        log = [*log, collapse_repeated_progress(apply_carriage_returns(text))]
    joined_len = sum(len(s) for s in log)
    if joined_len > _MAX_PROGRESS_CHARS:
        joined = collapse_repeated_progress("".join(log))
        return [joined[-_MAX_PROGRESS_CHARS:]]
    return log
