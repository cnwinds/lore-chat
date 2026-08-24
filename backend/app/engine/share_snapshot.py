"""分享快照：会话冻结、文档定版与公开 payload 物化。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.engine.disclosure import build_outline
from app.models.media_grants import build_media_grant_url
from app.storage.repo import KnowledgeRepo

_MSG_KEEP = frozenset(
    {
        "id",
        "role",
        "text",
        "ts",
        "status",
        "timeline",
        "sources",
        "attachments",
        "doc_context",
        "primary_doc",
    }
)


def validate_shareable_doc_path(repo: KnowledgeRepo, rel_path: str) -> str:
    norm = rel_path.replace("\\", "/").lstrip("/")
    if not norm or norm.startswith(".kb/") or norm.startswith(".git/"):
        raise ValueError("invalid doc path")
    if repo.is_protected(norm):
        raise ValueError("protected doc path")
    return norm


def snapshot_conversation(
    conversation: dict,
    *,
    shares_dir: Path,
    share_id: str,
    message_ids: list[str] | None = None,
) -> str:
    shares_dir.mkdir(parents=True, exist_ok=True)
    payload = materialize_conversation_snapshot(conversation, message_ids=message_ids)
    rel = f".kb/shares/{share_id}.json"
    abs_path = shares_dir / f"{share_id}.json"
    abs_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return rel


def materialize_conversation_snapshot(
    conversation: dict,
    *,
    message_ids: list[str] | None = None,
) -> dict:
    raw_msgs = [m for m in (conversation.get("messages") or []) if isinstance(m, dict)]
    if message_ids is not None:
        wanted = [str(x) for x in message_ids if str(x).strip()]
        if not wanted:
            raise ValueError("message_ids must not be empty")
        by_id = {str(m.get("id") or ""): m for m in raw_msgs if m.get("id")}
        missing = [mid for mid in wanted if mid not in by_id]
        if missing:
            raise ValueError(f"unknown message_ids: {', '.join(missing[:5])}")
        wanted_set = set(wanted)
        raw_msgs = [m for m in raw_msgs if str(m.get("id") or "") in wanted_set]
        if not raw_msgs:
            raise ValueError("message_ids must not be empty")
    messages = []
    for msg in raw_msgs:
        slim = {k: msg[k] for k in _MSG_KEEP if k in msg}
        messages.append(slim)
    return {
        "version": 1,
        "title": conversation.get("title") or "未命名对话",
        "created_at": conversation.get("created_at"),
        "messages": messages,
    }


def conversation_live_payload_ref(conversation_id: str) -> str:
    return f"conv:{conversation_id}"


def conversation_id_from_payload_ref(payload_ref: str) -> str | None:
    ref = payload_ref.replace("\\", "/")
    if ref.startswith("conv:"):
        cid = ref[5:].strip()
        return cid or None
    return None


def is_live_conversation_share(link) -> bool:
    opts = link.options if isinstance(link.options, dict) else {}
    if opts.get("pin_version") is False:
        return True
    if opts.get("pin_version") is True:
        return False
    return conversation_id_from_payload_ref(link.payload_ref) is not None


def load_conversation_for_share(
    link,
    *,
    kb_path: Path,
    conversations,
) -> dict:
    """快照或跟随 live 会话，返回与 snapshot JSON 同形的 dict。"""
    if not is_live_conversation_share(link):
        return load_conversation_snapshot(kb_path, link.payload_ref)
    opts = link.options if isinstance(link.options, dict) else {}
    cid = str(
        opts.get("conversation_id")
        or conversation_id_from_payload_ref(link.payload_ref)
        or ""
    ).strip()
    if not cid:
        raise ValueError("missing conversation_id")
    try:
        conv = conversations.get(cid)
    except KeyError as e:
        raise FileNotFoundError(cid) from e
    message_ids_raw = opts.get("message_ids")
    message_ids: list[str] | None = None
    if isinstance(message_ids_raw, list) and message_ids_raw:
        message_ids = [str(x) for x in message_ids_raw if str(x).strip()]
    return materialize_conversation_snapshot(conv, message_ids=message_ids)


def conversation_share_public_title(link, snapshot: dict) -> str:
    """快照用 link.title；跟随会话时用当前会话标题。"""
    base = (link.title or "").strip() or "对话分享"
    if not is_live_conversation_share(link):
        return base
    live = (snapshot.get("title") or "").strip()
    return live or base


def snapshot_doc_pinned(
    repo: KnowledgeRepo,
    rel_path: str,
    *,
    shares_dir: Path,
    share_id: str,
) -> str:
    shares_dir.mkdir(parents=True, exist_ok=True)
    doc = repo.read_doc(rel_path)
    abs_path = shares_dir / f"{share_id}.md"
    abs_path.write_text(doc.body, encoding="utf-8")
    return f".kb/shares/{share_id}.md"


def load_conversation_snapshot(kb_path: Path, payload_ref: str) -> dict:
    abs_path = _resolve_payload_path(kb_path, payload_ref)
    raw = json.loads(abs_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("invalid conversation snapshot")
    return raw


def load_doc_body(
    repo: KnowledgeRepo,
    kb_path: Path,
    link,
) -> str:
    pin_version = bool(link.options.get("pin_version", True))
    if pin_version:
        abs_path = _resolve_payload_path(kb_path, link.payload_ref)
        return abs_path.read_text(encoding="utf-8")
    return repo.read_doc(link.payload_ref).body


def build_public_conversation_payload(
    snapshot: dict,
    *,
    title: str,
    exp_iso: str | None,
    kb_path: Path,
    public_base_url: str,
    grant_ttl_sec: int,
) -> dict:
    messages = snapshot.get("messages") or []
    resolved = [
        _resolve_message_media(m, kb_path=kb_path, public_base_url=public_base_url, grant_ttl_sec=grant_ttl_sec)
        for m in messages
        if isinstance(m, dict)
    ]
    return {
        "type": "conversation",
        "title": title or snapshot.get("title") or "对话分享",
        "exp": exp_iso,
        "messages": resolved,
    }


def build_public_doc_payload(
    body: str,
    *,
    title: str,
    exp_iso: str | None,
    kb_path: Path,
    public_base_url: str,
    grant_ttl_sec: int,
) -> dict:
    outline = build_outline(body)
    rewritten = _rewrite_markdown_images(
        body,
        kb_path=kb_path,
        public_base_url=public_base_url,
        grant_ttl_sec=grant_ttl_sec,
    )
    out: dict = {
        "type": "doc",
        "title": title,
        "exp": exp_iso,
        "body": rewritten,
    }
    if outline:
        out["outline"] = outline
    return out


def _resolve_payload_path(kb_path: Path, payload_ref: str) -> Path:
    ref = payload_ref.replace("\\", "/")
    if not ref.startswith(".kb/shares/"):
        raise ValueError("invalid snapshot ref")
    abs_path = (kb_path / ref).resolve()
    kb_root = kb_path.resolve()
    if kb_root not in abs_path.parents and abs_path != kb_root:
        raise ValueError("path escape")
    if not abs_path.is_file():
        raise FileNotFoundError(ref)
    return abs_path


def _resolve_message_media(
    msg: dict,
    *,
    kb_path: Path,
    public_base_url: str,
    grant_ttl_sec: int,
) -> dict:
    out = dict(msg)
    if out.get("attachments"):
        out["attachments"] = [
            _grant_kb_path(p, kb_path=kb_path, public_base_url=public_base_url, grant_ttl_sec=grant_ttl_sec)
            for p in out["attachments"]
            if isinstance(p, str)
        ]
    sources = out.get("sources")
    if isinstance(sources, list):
        out["sources"] = [
            _resolve_source(s, kb_path=kb_path, public_base_url=public_base_url, grant_ttl_sec=grant_ttl_sec)
            for s in sources
            if isinstance(s, dict)
        ]
    return out


def _resolve_source(
    src: dict,
    *,
    kb_path: Path,
    public_base_url: str,
    grant_ttl_sec: int,
) -> dict:
    out = dict(src)
    if out.get("type") == "kb" and isinstance(out.get("path"), str):
        path = out["path"]
        # 参考图/视频物化为 grant；普通文档引用保留相对路径作展示标签
        if _looks_like_image(path) or _looks_like_video(path):
            out["path"] = _grant_kb_path(
                path,
                kb_path=kb_path,
                public_base_url=public_base_url,
                grant_ttl_sec=grant_ttl_sec,
            )
    return out


def _looks_like_image(path: str) -> bool:
    return bool(
        re.search(
            r"\.(png|jpe?g|gif|webp|bmp|svg|tif|tiff|ico)$",
            path.split("?")[0] or path,
            re.I,
        )
    )


def _looks_like_video(path: str) -> bool:
    return bool(
        re.search(r"\.(mp4|webm|mov|m4v)$", path.split("?")[0] or path, re.I)
    )


def _grant_kb_path(
    rel_path: str,
    *,
    kb_path: Path,
    public_base_url: str,
    grant_ttl_sec: int,
) -> str:
    norm = rel_path.replace("\\", "/").lstrip("/")
    if not norm or norm.startswith(".kb/") or norm.startswith(".git/"):
        return rel_path
    if norm.startswith(("http://", "https://", "data:", "/api/")):
        return rel_path
    abs_p = (kb_path / norm).resolve()
    if not abs_p.is_file():
        return rel_path
    try:
        return build_media_grant_url(
            public_base_url=public_base_url,
            rel_path=norm,
            kb_path=kb_path,
            ttl_sec=grant_ttl_sec,
        )
    except ValueError:
        return rel_path


def _rewrite_markdown_images(
    body: str,
    *,
    kb_path: Path,
    public_base_url: str,
    grant_ttl_sec: int,
) -> str:
    def repl(match: re.Match) -> str:
        alt, raw_src = match.group(1), match.group(2).strip()
        if raw_src.startswith(("http://", "https://", "data:", "/api/")):
            return match.group(0)
        url = _grant_kb_path(
            raw_src,
            kb_path=kb_path,
            public_base_url=public_base_url,
            grant_ttl_sec=grant_ttl_sec,
        )
        return f"![{alt}]({url})"

    return re.sub(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", repl, body)


def exp_to_iso(exp: float | None) -> str | None:
    if exp is None:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(exp, tz=timezone.utc).isoformat(timespec="seconds")


def grant_ttl_for_share(exp: float | None, *, now: float) -> int:
    """分享内嵌媒体 grant TTL：与分享剩余有效期对齐；永久链接按 7 天签发（每次公开访问重发）。"""
    if exp is None:
        return 7 * 24 * 3600
    remaining = int(exp - now)
    return max(3600, min(remaining, 7 * 24 * 3600))
