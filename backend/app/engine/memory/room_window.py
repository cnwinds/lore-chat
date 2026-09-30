"""房间记忆抽取窗口：游标后的消息切片与上下文。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoomLine:
    seq: int
    speaker_kind: str
    speaker_id: str | None
    speaker_name: str | None
    text: str


@dataclass(frozen=True)
class RoomWindow:
    lines: list[RoomLine]
    context: list[RoomLine]
    end_seq: int | None
    has_more: bool


def _is_included_row(row) -> bool:
    status = (row["status"] or "").strip()
    if status != "complete":
        return False
    try:
        speaker = (row["speaker_kind"] or "").strip()
    except (KeyError, IndexError):
        speaker = ""
    if speaker not in ("user", "role"):
        return False
    text = (row["text"] or "").strip()
    return bool(text)


def _to_line(row) -> RoomLine:
    return RoomLine(
        seq=int(row["seq"]),
        speaker_kind=(row["speaker_kind"] or "").strip(),
        speaker_id=row["speaker_id"],
        speaker_name=row["speaker_name"],
        text=(row["text"] or "").strip(),
    )


def build_room_window(
    rows: list,
    *,
    after_seq: int | None,
    limit: int,
    context: int,
) -> RoomWindow:
    """由按 seq 升序的消息行构建窗口（调用方已过滤 conversation_id）。

    消息行落库即终态（助手回复在回合结束时才写入）：失败 / 中断的消息与系统刺激、
    空消息一样不纳入，但计入 end_seq，游标照常越过。
    """
    cursor = after_seq or 0
    context_rows = [
        r for r in rows if int(r["seq"]) <= cursor and _is_included_row(r)
    ]
    context_lines = (
        [_to_line(r) for r in context_rows[-context:]] if context > 0 else []
    )

    lines: list[RoomLine] = []
    end_seq: int | None = None
    for row in rows:
        seq = int(row["seq"])
        if seq <= cursor:
            continue
        if len(lines) >= limit:
            break
        end_seq = seq
        if _is_included_row(row):
            lines.append(_to_line(row))

    has_more = end_seq is not None and any(int(r["seq"]) > end_seq for r in rows)

    return RoomWindow(
        lines=lines,
        context=context_lines,
        end_seq=end_seq,
        has_more=has_more,
    )


__all__ = ["RoomLine", "RoomWindow", "build_room_window"]
