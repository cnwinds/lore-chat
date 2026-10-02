from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import Literal
from urllib.parse import unquote

from app.engine.context_view.errors import InvalidUri
from app.engine.memory.cards import CARD_KINDS
from app.engine.memory.constants import CATEGORIES

LORE_SCHEME = "lore"
LORE_ROOT = "lore://"

ConversationBucket = Literal["dm", "rooms", "channels"]
MemoryScopeKind = Literal["owner", "role", "persona"]

_OWNER_KINDS = frozenset(CATEGORIES)
_CARD_KINDS = frozenset(CARD_KINDS)


def is_kb_internal(rel_path: str) -> bool:
    """与 ``KnowledgeRepo.is_internal`` 相同语义。"""
    norm = posixpath.normpath(rel_path.replace("\\", "/").lstrip("/") or ".")
    return norm.split("/", 1)[0] in (".kb", ".git")


def _reject_internal_kb(rel_path: str) -> None:
    check = rel_path.rstrip("/") or rel_path
    if is_kb_internal(check):
        raise InvalidUri("知识库内部路径不可访问", uri=rel_path)


def _split_segments(path: str) -> list[str]:
    raw = (path or "").replace("\\", "/").strip("/")
    if not raw:
        return []
    parts: list[str] = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise InvalidUri("路径不得包含 ..")
        parts.append(unquote(part))
    return parts


@dataclass(frozen=True)
class LoreRoot:
    def format(self) -> str:
        return LORE_ROOT


@dataclass(frozen=True)
class ConversationRoot:
    def format(self) -> str:
        return f"{LORE_ROOT}conversations/"


@dataclass(frozen=True)
class MemoryRoot:
    def format(self) -> str:
        return f"{LORE_ROOT}memory/"


@dataclass(frozen=True)
class KbUri:
    rel_path: str
    is_dir: bool

    def format(self) -> str:
        p = self.rel_path.replace("\\", "/").strip("/")
        if not p:
            return f"{LORE_ROOT}kb/"
        if self.is_dir:
            return f"{LORE_ROOT}kb/{p}/"
        return f"{LORE_ROOT}kb/{p}"


@dataclass(frozen=True)
class ConversationUri:
    bucket: ConversationBucket
    owner: str | None
    conversation_id: str | None
    message_id: str | None
    is_dir: bool

    def format(self) -> str:
        parts: list[str] = ["conversations", self.bucket]
        if self.bucket in ("dm", "channels") and self.owner:
            parts.append(self.owner)
        if self.conversation_id:
            parts.append(self.conversation_id)
        if self.message_id:
            return LORE_ROOT + "/".join([*parts, self.message_id])
        tail = "/".join(parts)
        if self.is_dir or not self.conversation_id:
            return f"{LORE_ROOT}{tail}/"
        return f"{LORE_ROOT}{tail}"


@dataclass(frozen=True)
class MemoryUri:
    scope_kind: MemoryScopeKind
    subject: str | None
    kind: str | None
    item_id: str | None
    is_dir: bool

    def format(self) -> str:
        base = f"{LORE_ROOT}memory/{self.scope_kind}"
        if self.scope_kind in ("role", "persona"):
            if not self.subject:
                return f"{base}/"
            base = f"{base}/{self.subject}"
        if self.kind:
            base = f"{base}/{self.kind}"
        if self.item_id:
            return f"{base}/{self.item_id}"
        return f"{base}/"


@dataclass(frozen=True)
class LegacyConversationRef:
    conversation_id: str
    message_id: str | None = None


LoreUri = (
    LoreRoot | ConversationRoot | MemoryRoot | KbUri | ConversationUri | MemoryUri
)


def _parse_kb_tail(tail: str, *, is_dir_hint: bool | None = None) -> KbUri:
    is_dir = tail.endswith("/") if is_dir_hint is None else is_dir_hint
    rel = tail.rstrip("/")
    _reject_internal_kb(rel or ".")
    return KbUri(rel_path=rel, is_dir=is_dir or not rel)


def _validate_memory_kind(scope_kind: MemoryScopeKind, kind: str | None) -> None:
    if not kind:
        return
    if scope_kind == "owner":
        if kind not in _OWNER_KINDS:
            raise InvalidUri(f"未知主人记忆种类: {kind}")
    else:
        if kind not in _CARD_KINDS:
            raise InvalidUri(f"未知卡片种类: {kind}")


def _parse_conversation(
    segments: list[str], *, is_dir_hint: bool
) -> ConversationRoot | ConversationUri:
    if not segments:
        if not is_dir_hint:
            raise InvalidUri("conversations 根路径须以 / 结尾")
        return ConversationRoot()
    bucket = segments[0]
    if bucket not in ("dm", "rooms", "channels"):
        raise InvalidUri(f"未知会话桶: {bucket}")
    rest = segments[1:]
    owner: str | None = None
    cid: str | None = None
    mid: str | None = None
    if bucket == "dm":
        if len(rest) == 0:
            return ConversationUri("dm", None, None, None, True)
        owner = rest[0]
        rest = rest[1:]
    elif bucket == "channels":
        if len(rest) == 0:
            return ConversationUri("channels", None, None, None, True)
        owner = rest[0]
        rest = rest[1:]
    if len(rest) >= 1:
        cid = rest[0]
        rest = rest[1:]
    if len(rest) >= 1:
        mid = rest[0]
        rest = rest[1:]
    if rest:
        raise InvalidUri("会话路径段过多")
    if mid and not cid:
        raise InvalidUri("消息 id 缺少会话 id")
    if bucket == "dm" and cid and not owner:
        raise InvalidUri("dm 会话路径缺少角色 id")
    if bucket == "channels" and cid and not owner:
        raise InvalidUri("channels 会话路径缺少实例 id")
    is_dir = is_dir_hint and not mid
    if mid:
        is_dir = False
    return ConversationUri(bucket, owner, cid, mid, is_dir)


def _parse_memory(segments: list[str], *, is_dir_hint: bool) -> MemoryRoot | MemoryUri:
    if not segments:
        if not is_dir_hint:
            raise InvalidUri("memory 根路径须以 / 结尾")
        return MemoryRoot()
    scope_kind = segments[0]
    if scope_kind not in ("owner", "role", "persona"):
        raise InvalidUri(f"未知记忆作用域: {scope_kind}")
    rest = segments[1:]
    subject: str | None = None
    kind: str | None = None
    item_id: str | None = None
    sk: MemoryScopeKind = scope_kind  # type: ignore[assignment]
    if sk in ("role", "persona"):
        if len(rest) >= 1:
            subject = rest[0]
            rest = rest[1:]
        elif not is_dir_hint and rest == [] and segments == [scope_kind]:
            pass
    if len(rest) >= 1:
        kind = rest[0]
        rest = rest[1:]
    if len(rest) >= 1:
        item_id = rest[0]
        rest = rest[1:]
    if rest:
        raise InvalidUri("记忆路径段过多")
    if item_id and not kind:
        raise InvalidUri("记忆条目缺少种类段")
    if sk in ("role", "persona") and (kind or item_id) and not subject:
        raise InvalidUri(f"{sk} 记忆路径缺少主体 id")
    _validate_memory_kind(sk, kind)
    is_dir = is_dir_hint and not item_id
    if item_id:
        is_dir = False
    return MemoryUri(sk, subject, kind, item_id, is_dir)


def parse(raw: str) -> LoreUri | LegacyConversationRef:
    text = (raw or "").strip()
    if not text:
        raise InvalidUri("空 URI")
    if text.startswith("conversation://"):
        tail = text[len("conversation://") :]
        parts = _split_segments(tail.split("#", 1)[0])
        if not parts:
            raise InvalidUri("conversation:// 缺少会话 id")
        if len(parts) > 2:
            raise InvalidUri("conversation:// 路径过深")
        cid = parts[0]
        mid = parts[1] if len(parts) == 2 else None
        return LegacyConversationRef(cid, mid)

    is_dir_hint = text.endswith("/")
    if "://" in text:
        scheme, _, rest = text.partition("://")
        if scheme.lower() != LORE_SCHEME:
            raise InvalidUri(f"未知 scheme: {scheme}")
        path = rest
    else:
        return _parse_kb_tail(text, is_dir_hint=is_dir_hint)

    path = path.lstrip("/")
    if not path:
        return LoreRoot()
    segments = _split_segments(path)
    if not segments:
        return LoreRoot()
    ns = segments[0]
    tail_segments = segments[1:]
    if ns == "kb":
        tail = "/".join(tail_segments)
        if is_dir_hint and tail and not tail.endswith("/"):
            tail = tail + "/"
        return _parse_kb_tail(tail, is_dir_hint=is_dir_hint or not tail_segments)
    if ns == "conversations":
        return _parse_conversation(tail_segments, is_dir_hint=is_dir_hint)
    if ns == "memory":
        return _parse_memory(tail_segments, is_dir_hint=is_dir_hint)
    raise InvalidUri(f"未知命名空间: {ns}")


def format_uri(uri: LoreUri | LegacyConversationRef) -> str:
    if isinstance(uri, LegacyConversationRef):
        if uri.message_id:
            return f"conversation://{uri.conversation_id}/{uri.message_id}"
        return f"conversation://{uri.conversation_id}"
    return uri.format()


def uri_path_key(uri: LoreUri) -> str:
    """用于前缀包含与去重；目录 URI 保证以 / 结尾。"""
    if isinstance(uri, LoreRoot):
        return LORE_ROOT
    if isinstance(uri, ConversationRoot):
        return f"{LORE_ROOT}conversations/"
    if isinstance(uri, MemoryRoot):
        return f"{LORE_ROOT}memory/"
    if isinstance(uri, KbUri):
        inner = uri.rel_path.replace("\\", "/")
        if not inner:
            return f"{LORE_ROOT}kb/"
        if uri.is_dir:
            return f"{LORE_ROOT}kb/{inner.rstrip('/')}/"
        return f"{LORE_ROOT}kb/{inner}"
    if isinstance(uri, ConversationUri):
        s = format_uri(uri)
        if uri.is_dir and not s.endswith("/"):
            return s + "/"
        return s
    if isinstance(uri, MemoryUri):
        s = format_uri(uri)
        if uri.is_dir and not s.endswith("/"):
            return s + "/"
        return s
    raise TypeError(uri)


def uri_covers(outer: LoreUri, inner: LoreUri) -> bool:
    """outer 是否包含 inner（同命名空间、整段前缀）。"""
    if isinstance(outer, LoreRoot):
        return True
    if isinstance(outer, ConversationRoot):
        return isinstance(inner, (ConversationRoot, ConversationUri))
    if isinstance(outer, MemoryRoot):
        return isinstance(inner, (MemoryRoot, MemoryUri))
    o = uri_path_key(outer).rstrip("/")
    i = uri_path_key(inner).rstrip("/")
    if not i.startswith(o):
        return False
    if len(i) == len(o):
        return True
    return i[len(o)] == "/"
