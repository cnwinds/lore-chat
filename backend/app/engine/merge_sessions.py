from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.engine.content_hash import is_body_modified
from app.time import now_iso_seconds


def _now() -> str:
    return now_iso_seconds()


class MergeSessionStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({})

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def create(
        self,
        *,
        new_path: str,
        source_paths: list[str],
        instruction: str,
        order: list[str],
        generated_content_hash: str,
    ) -> str:
        data = self._read()
        sid = uuid.uuid4().hex[:12]
        stamp = _now()
        data[sid] = {
            "id": sid,
            "status": "pending_review",
            "new_path": new_path,
            "source_paths": source_paths,
            "instruction": instruction,
            "order": order,
            "generated_content_hash": generated_content_hash,
            "created_at": stamp,
            "updated_at": stamp,
        }
        self._write(data)
        return sid

    def get(self, sid: str) -> dict:
        return self._read()[sid]

    def update(self, sid: str, **fields) -> dict:
        data = self._read()
        data[sid].update(fields)
        data[sid]["updated_at"] = _now()
        self._write(data)
        return data[sid]

    def find_active_by_path(self, path: str) -> dict | None:
        for session in self._read().values():
            if session["status"] == "pending_review" and session["new_path"] == path:
                return session
        return None

    def user_modified(self, sid: str, current_body: str) -> bool:
        session = self.get(sid)
        return is_body_modified(current_body, session["generated_content_hash"])
