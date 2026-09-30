"""房间（peer_dm / group）记忆与知识卡抽取辅助。"""

from __future__ import annotations

from app.engine.memory.cards import CardLens, KnowledgeCards
from app.engine.memory.constants import (
    ROOM_CONTEXT_MESSAGES,
    ROOM_MAX_ROLE_LENSES,
    ROOM_WINDOW_MAX_MESSAGES,
)
from app.engine.memory.room_window import RoomLine, RoomWindow
from app.engine.memory.role_card_extractor import RoomDialogue
from app.engine.roles import is_hidden_role


def room_line_label(line: RoomLine, role_id: str, role_names: dict[str, str]) -> str:
    if line.speaker_kind == "user":
        return "主人"
    if line.speaker_kind == "role" and (line.speaker_id or "").strip() == role_id:
        return "本角色"
    name = (line.speaker_name or "").strip()
    if not name:
        name = role_names.get((line.speaker_id or "").strip()) or (
            line.speaker_id or "同伴"
        )
    return f"同伴「{name}」"


def labeled_dialogue(
    lines: list[RoomLine], role_id: str, role_names: dict[str, str]
) -> list[tuple[str, str]]:
    return [(room_line_label(ln, role_id, role_names), ln.text) for ln in lines]


def collect_peer_names(
    lines: list[RoomLine],
    context: list[RoomLine],
    role_id: str,
    role_names: dict[str, str],
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ln in context + lines:
        if ln.speaker_kind != "role":
            continue
        rid = (ln.speaker_id or "").strip()
        if not rid or rid == role_id:
            continue
        name = (ln.speaker_name or "").strip() or role_names.get(rid) or rid
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def select_room_role_ids(
    window: RoomWindow,
    cards: KnowledgeCards,
) -> list[str]:
    counts: dict[str, int] = {}
    first_seq: dict[str, int] = {}
    for ln in window.lines:
        if ln.speaker_kind != "role":
            continue
        rid = (ln.speaker_id or "").strip()
        if not rid:
            continue
        scope = cards.scope_for_role(rid)
        if not scope or not scope.startswith("role:"):
            continue
        counts[rid] = counts.get(rid, 0) + 1
        if rid not in first_seq:
            first_seq[rid] = ln.seq
    ordered = sorted(
        counts.keys(),
        key=lambda r: (-counts[r], first_seq.get(r, 0)),
    )
    return ordered[:ROOM_MAX_ROLE_LENSES]


def owner_turns_from_window(lines: list[RoomLine]) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for ln in lines:
        if ln.speaker_kind == "user":
            turns.append(("user", ln.text))
        elif ln.speaker_kind == "role":
            turns.append(("assistant", ln.text))
    return turns


def build_room_dialogue(
    *,
    kind: str,
    title: str,
    window: RoomWindow,
    role_id: str,
    role_names: dict[str, str],
) -> RoomDialogue:
    ctx = labeled_dialogue(window.context, role_id, role_names)
    body = labeled_dialogue(window.lines, role_id, role_names)
    peers = collect_peer_names(window.lines, window.context, role_id, role_names)
    return RoomDialogue(
        kind=kind,
        title=title,
        peer_names=peers,
        context=ctx,
        lines=body,
    )


def direct_lens_for_role(cards: KnowledgeCards, role_id: str) -> CardLens | None:
    scope = cards.scope_for_role(role_id)
    if not scope or not scope.startswith("role:"):
        return None
    try:
        role = cards.roles.get(role_id)
    except KeyError:
        return None
    if is_hidden_role(role):
        return None
    return CardLens(
        scope,
        "direct",
        role.get("name") or role_id,
        role.get("system_prompt") or "",
    )


def role_name_map(cards: KnowledgeCards, role_ids: set[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rid in role_ids:
        try:
            role = cards.roles.get(rid)
        except KeyError:
            continue
        out[rid] = (role.get("name") or rid).strip() or rid
    return out


__all__ = [
    "build_room_dialogue",
    "direct_lens_for_role",
    "owner_turns_from_window",
    "role_name_map",
    "select_room_role_ids",
]
