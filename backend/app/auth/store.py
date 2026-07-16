from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.auth.passwords import hash_password, verify_password

_MIN_LEN = 8


class AuthAlreadySetupError(Exception):
    pass


class AuthError(Exception):
    pass


class AuthStore:
    def __init__(self, kb_path: Path) -> None:
        self._path = Path(kb_path) / ".kb" / "auth.json"

    def _read(self) -> dict | None:
        if not self._path.is_file():
            return None
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def is_setup_required(self) -> bool:
        data = self._read()
        return not (data and data.get("password_hash"))

    def set_password(self, password: str) -> None:
        if self.is_setup_required() is False:
            raise AuthAlreadySetupError("password already set")
        if len(password) < _MIN_LEN:
            raise AuthError(f"password must be at least {_MIN_LEN} characters")
        self._write(
            {
                "password_hash": hash_password(password),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def verify(self, password: str) -> bool:
        data = self._read()
        if not data or not data.get("password_hash"):
            return False
        return verify_password(password, data["password_hash"])

    def change_password(self, old_password: str, new_password: str) -> None:
        if not self.verify(old_password):
            raise AuthError("old password incorrect")
        if len(new_password) < _MIN_LEN:
            raise AuthError(f"password must be at least {_MIN_LEN} characters")
        self._write(
            {
                "password_hash": hash_password(new_password),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
