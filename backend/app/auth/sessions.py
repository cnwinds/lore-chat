from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path


class SessionStore:
    def __init__(self, kb_path: Path, ttl_days: int = 7) -> None:
        self._path = Path(kb_path) / ".kb" / "sessions.json"
        self._ttl = timedelta(days=ttl_days)

    def _read(self) -> dict:
        if not self._path.is_file():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def create(self) -> str:
        sid = secrets.token_urlsafe(32)
        data = self._read()
        data[sid] = {
            "expires_at": (datetime.now(timezone.utc) + self._ttl).isoformat()
        }
        self._write(data)
        return sid

    def validate(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        data = self._read()
        entry = data.get(session_id)
        if not entry:
            return False
        expires = datetime.fromisoformat(entry["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            data.pop(session_id, None)
            self._write(data)
            return False
        # 滑动过期
        data[session_id] = {
            "expires_at": (datetime.now(timezone.utc) + self._ttl).isoformat()
        }
        self._write(data)
        return True

    def revoke(self, session_id: str | None) -> None:
        if not session_id:
            return
        data = self._read()
        if session_id in data:
            data.pop(session_id)
            self._write(data)
