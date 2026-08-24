"""分享链接存储：不透明 share_id → 会话/文档快照或 live 路径。"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_STORE_VERSION = 1
_SHARE_ID_BYTES = 18
_MAX_RECENT_VIEWS = 20
_REFERER_MAX_LEN = 200


@dataclass(frozen=True)
class ShareLink:
    share_id: str
    type: str  # conversation | doc
    title: str
    created_at: str
    exp: float | None
    revoked: bool
    view_count: int
    payload_ref: str
    options: dict
    last_viewed_at: str | None = None
    recent_views: tuple[dict, ...] = ()


class ShareLinkStore:
    """持久化到 `{kb_path}/.kb/share_links.json`。"""

    def __init__(self, kb_path: Path) -> None:
        self._kb_path = Path(kb_path)
        self._path = self._kb_path / ".kb" / "share_links.json"
        self.shares_dir = self._kb_path / ".kb" / "shares"

    def create(
        self,
        *,
        type: str,
        title: str,
        payload_ref: str,
        ttl_sec: int | None,
        options: dict | None = None,
        now: float | None = None,
        share_id: str | None = None,
    ) -> ShareLink:
        if type not in ("conversation", "doc"):
            raise ValueError("invalid share type")
        now = time.time() if now is None else now
        sid = share_id or secrets.token_urlsafe(_SHARE_ID_BYTES)
        if not _share_id_ok(sid):
            raise ValueError("invalid share_id")
        exp: float | None = None
        if ttl_sec is not None:
            exp = now + max(60, int(ttl_sec))
        created_at = datetime.fromtimestamp(now, tz=timezone.utc).isoformat(
            timespec="seconds"
        )
        row = {
            "type": type,
            "title": title,
            "created_at": created_at,
            "exp": exp,
            "revoked": False,
            "view_count": 0,
            "last_viewed_at": None,
            "recent_views": [],
            "payload_ref": payload_ref.replace("\\", "/").lstrip("/")
            if not payload_ref.startswith(".kb/")
            else payload_ref.replace("\\", "/"),
            "options": options or {},
        }
        data = self._load()
        items: dict[str, dict] = data.setdefault("items", {})
        self._prune(items, now=now)
        items[sid] = row
        self._save(data)
        return self._to_link(sid, row)

    def list_all(self, *, now: float | None = None) -> list[ShareLink]:
        now = time.time() if now is None else now
        data = self._load()
        items: dict[str, dict] = data.get("items") or {}
        self._prune(items, now=now)
        self._save(data)
        out = [self._to_link(sid, row) for sid, row in items.items() if isinstance(row, dict)]
        return sorted(out, key=lambda s: s.created_at, reverse=True)

    def revoke(self, share_id: str) -> bool:
        if not _share_id_ok(share_id):
            return False
        data = self._load()
        items: dict[str, dict] = data.get("items") or {}
        row = items.get(share_id)
        if not isinstance(row, dict):
            return False
        row["revoked"] = True
        self._save(data)
        return True

    def resolve_public(
        self,
        share_id: str,
        *,
        now: float | None = None,
        increment_view: bool = False,
        referer: str | None = None,
    ) -> tuple[ShareLink | None, str]:
        """返回 (link, status)；status 为 ok | expired | revoked | not_found。"""
        if not _share_id_ok(share_id):
            return None, "not_found"
        now = time.time() if now is None else now
        data = self._load()
        items: dict[str, dict] = data.get("items") or {}
        row = items.get(share_id)
        if not isinstance(row, dict):
            return None, "not_found"
        if row.get("revoked"):
            return None, "revoked"
        exp = row.get("exp")
        if exp is not None:
            try:
                if float(exp) < now:
                    return None, "expired"
            except (TypeError, ValueError):
                return None, "not_found"
        if increment_view:
            self._record_view(row, now=now, referer=referer)
            self._save(data)
        return self._to_link(share_id, row), "ok"

    def resolve(
        self,
        share_id: str,
        *,
        now: float | None = None,
        increment_view: bool = False,
        referer: str | None = None,
    ) -> ShareLink | None:
        link, status = self.resolve_public(
            share_id, now=now, increment_view=increment_view, referer=referer
        )
        return link if status == "ok" else None

    def get(self, share_id: str) -> ShareLink | None:
        if not _share_id_ok(share_id):
            return None
        data = self._load()
        row = (data.get("items") or {}).get(share_id)
        if not isinstance(row, dict):
            return None
        return self._to_link(share_id, row)

    @staticmethod
    def _record_view(row: dict, *, now: float, referer: str | None) -> None:
        try:
            row["view_count"] = int(row.get("view_count") or 0) + 1
        except (TypeError, ValueError):
            row["view_count"] = 1
        ts = datetime.fromtimestamp(now, tz=timezone.utc).isoformat(timespec="seconds")
        row["last_viewed_at"] = ts
        entry: dict = {"ts": ts}
        ref = (referer or "").strip()
        if ref:
            entry["referer"] = ref[:_REFERER_MAX_LEN]
        recent = row.get("recent_views")
        if not isinstance(recent, list):
            recent = []
        recent = [x for x in recent if isinstance(x, dict)]
        recent.append(entry)
        if len(recent) > _MAX_RECENT_VIEWS:
            recent = recent[-_MAX_RECENT_VIEWS:]
        row["recent_views"] = recent

    @staticmethod
    def _to_link(share_id: str, row: dict) -> ShareLink:
        exp = row.get("exp")
        try:
            exp_val = float(exp) if exp is not None else None
        except (TypeError, ValueError):
            exp_val = None
        opts = row.get("options")
        recent_raw = row.get("recent_views")
        recent: list[dict] = []
        if isinstance(recent_raw, list):
            for item in recent_raw:
                if isinstance(item, dict) and item.get("ts"):
                    recent.append(
                        {
                            "ts": str(item["ts"]),
                            **(
                                {"referer": str(item["referer"])}
                                if item.get("referer")
                                else {}
                            ),
                        }
                    )
        last = row.get("last_viewed_at")
        return ShareLink(
            share_id=share_id,
            type=str(row.get("type") or ""),
            title=str(row.get("title") or ""),
            created_at=str(row.get("created_at") or ""),
            exp=exp_val,
            revoked=bool(row.get("revoked")),
            view_count=int(row.get("view_count") or 0),
            payload_ref=str(row.get("payload_ref") or ""),
            options=opts if isinstance(opts, dict) else {},
            last_viewed_at=str(last) if last else None,
            recent_views=tuple(recent),
        )

    def _load(self) -> dict:
        if not self._path.is_file():
            return {"version": _STORE_VERSION, "items": {}}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": _STORE_VERSION, "items": {}}
        if not isinstance(raw, dict):
            return {"version": _STORE_VERSION, "items": {}}
        if not isinstance(raw.get("items"), dict):
            raw["items"] = {}
        return raw

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": _STORE_VERSION, "items": data.get("items") or {}}
        self._path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _prune(items: dict[str, dict], *, now: float) -> None:
        dead: list[str] = []
        for sid, row in items.items():
            if not isinstance(row, dict):
                dead.append(sid)
                continue
            if row.get("revoked"):
                continue
            exp = row.get("exp")
            if exp is None:
                continue
            try:
                if float(exp) < now:
                    dead.append(sid)
            except (TypeError, ValueError):
                dead.append(sid)
        for sid in dead:
            items.pop(sid, None)


def _share_id_ok(share_id: str) -> bool:
    if len(share_id) < 16 or len(share_id) > 64:
        return False
    return all(ch.isalnum() or ch in "-_" for ch in share_id)


def build_share_url(*, public_base_url: str, share_id: str) -> str:
    base = public_base_url.rstrip("/")
    return f"{base}/share/{share_id}"


def public_options(options: dict) -> dict:
    """列表/创建响应用：剥离 password_hash，保留 has_password / message_ids 等。"""
    out = {k: v for k, v in options.items() if k != "password_hash"}
    if options.get("password_hash"):
        out["has_password"] = True
    elif "has_password" not in out:
        out["has_password"] = False
    return out
