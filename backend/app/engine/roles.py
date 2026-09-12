"""角色目录：默认通用角色 + 可扩展多角色（ADR 2026-09-09）。"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.engine.role_schedules import RoleScheduleStore

DEFAULT_ROLE_ID = "default"
DEFAULT_ROLE_NAME = "通用"
API_ROLE_PREFIX = "api_"
VISIBILITY_SIDEBAR = "sidebar"
VISIBILITY_HIDDEN = "hidden"


def is_api_role_id(role_id: str | None) -> bool:
    return (role_id or "").startswith(API_ROLE_PREFIX)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS roles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    avatar TEXT,
    system_prompt TEXT NOT NULL DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    onboarding_status TEXT NOT NULL DEFAULT 'none',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_roles_sort ON roles(sort_order, created_at);
"""

_PERSONA_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_personas (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    avatar TEXT,
    system_prompt TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class RoleStore:
    """角色持久化（`{kb}/.kb/roles/roles.db`）。启动时确保存在唯一默认角色。"""

    def __init__(self, path: str | Path):
        self.dir = Path(path)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.dir / "roles.db"
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript(_SCHEMA)
            self._migrate_onboarding_status()
            self._migrate_visibility_and_persona()
            self.conn.executescript(_PERSONA_SCHEMA)
            self.conn.commit()
            self.ensure_default_role()
        self.schedules = RoleScheduleStore(self.conn, self._lock)

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def _migrate_onboarding_status(self) -> None:
        """确保 onboarding_status 列存在，并为旧记录设置合理默认值。"""
        cursor = self.conn.execute("PRAGMA table_info(roles)")
        columns = {row[1] for row in cursor.fetchall()}
        if "onboarding_status" not in columns:
            self.conn.execute(
                "ALTER TABLE roles ADD COLUMN onboarding_status TEXT NOT NULL DEFAULT 'none'"
            )
            self.conn.execute(
                """
                UPDATE roles
                SET onboarding_status = CASE
                    WHEN system_prompt != '' THEN 'completed'
                    ELSE 'none'
                END
                WHERE onboarding_status = 'none'
                """
            )

    def _migrate_visibility_and_persona(self) -> None:
        cursor = self.conn.execute("PRAGMA table_info(roles)")
        columns = {row[1] for row in cursor.fetchall()}
        if "visibility" not in columns:
            self.conn.execute(
                "ALTER TABLE roles ADD COLUMN visibility TEXT NOT NULL DEFAULT "
                f"'{VISIBILITY_SIDEBAR}'"
            )
        if "persona_id" not in columns:
            self.conn.execute("ALTER TABLE roles ADD COLUMN persona_id TEXT")

    def ensure_default_role(self) -> str:
        """保证存在唯一 is_default 角色；返回其 id。"""
        row = self.conn.execute(
            "SELECT id FROM roles WHERE is_default = 1 LIMIT 1"
        ).fetchone()
        if row is not None:
            return row["id"]
        existing = self.conn.execute(
            "SELECT id FROM roles WHERE id = ?", (DEFAULT_ROLE_ID,)
        ).fetchone()
        stamp = _now()
        if existing is not None:
            self.conn.execute(
                "UPDATE roles SET is_default = 1, updated_at = ? WHERE id = ?",
                (stamp, DEFAULT_ROLE_ID),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO roles(
                    id, name, avatar, system_prompt, is_default, sort_order,
                    created_at, updated_at
                ) VALUES (?, ?, NULL, '', 1, 0, ?, ?)
                """,
                (DEFAULT_ROLE_ID, DEFAULT_ROLE_NAME, stamp, stamp),
            )
        self.conn.commit()
        return DEFAULT_ROLE_ID

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        try:
            onboarding_status = row["onboarding_status"]
        except (KeyError, IndexError):
            onboarding_status = "none"
        try:
            visibility = row["visibility"]
        except (KeyError, IndexError):
            visibility = VISIBILITY_SIDEBAR
        try:
            persona_id = row["persona_id"]
        except (KeyError, IndexError):
            persona_id = None
        return {
            "id": row["id"],
            "name": row["name"],
            "avatar": row["avatar"],
            "system_prompt": row["system_prompt"] or "",
            "is_default": bool(row["is_default"]),
            "sort_order": int(row["sort_order"]),
            "onboarding_status": onboarding_status or "none",
            "visibility": (visibility or VISIBILITY_SIDEBAR).strip()
            or VISIBILITY_SIDEBAR,
            "persona_id": (persona_id or "").strip() or None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_all(self, *, visibility: str | None = None) -> list[dict]:
        with self._lock:
            self.ensure_default_role()
            rows = self.conn.execute(
                "SELECT * FROM roles ORDER BY sort_order ASC, created_at ASC"
            ).fetchall()
            items = [self._row_to_dict(r) for r in rows]
        if visibility:
            want = visibility.strip()
            items = [r for r in items if r.get("visibility") == want]
        return items

    def get(self, role_id: str) -> dict:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM roles WHERE id = ?", (role_id,)
            ).fetchone()
            if row is None:
                raise KeyError(role_id)
            return self._row_to_dict(row)

    def get_default(self) -> dict:
        with self._lock:
            rid = self.ensure_default_role()
            row = self.conn.execute(
                "SELECT * FROM roles WHERE id = ?", (rid,)
            ).fetchone()
            assert row is not None
            return self._row_to_dict(row)

    def create(
        self,
        *,
        name: str,
        system_prompt: str = "",
        avatar: str | None = None,
        role_id: str | None = None,
        visibility: str = VISIBILITY_SIDEBAR,
        persona_id: str | None = None,
        onboarding_status: str | None = None,
    ) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("角色名称不能为空")
        rid = (role_id or _new_id()).strip()
        stamp = _now()
        vis = (visibility or VISIBILITY_SIDEBAR).strip()
        if vis not in (VISIBILITY_SIDEBAR, VISIBILITY_HIDDEN):
            vis = VISIBILITY_SIDEBAR
        status = onboarding_status
        if status is None:
            status = "completed" if system_prompt or vis == VISIBILITY_HIDDEN else "active"
        pid = (persona_id or "").strip() or None
        with self._lock:
            self.ensure_default_role()
            max_order = self.conn.execute(
                "SELECT COALESCE(MAX(sort_order), 0) AS m FROM roles"
            ).fetchone()["m"]
            self.conn.execute(
                """
                INSERT INTO roles(
                    id, name, avatar, system_prompt, is_default, sort_order,
                    onboarding_status, visibility, persona_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rid,
                    name,
                    avatar,
                    system_prompt or "",
                    int(max_order) + 1,
                    status,
                    vis,
                    pid,
                    stamp,
                    stamp,
                ),
            )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT * FROM roles WHERE id = ?", (rid,)
            ).fetchone()
            assert row is not None
            return self._row_to_dict(row)

    def update(
        self,
        role_id: str,
        *,
        name: str | None = None,
        system_prompt: str | None = None,
        avatar: str | None = None,
        onboarding_status: str | None = None,
    ) -> dict:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM roles WHERE id = ?", (role_id,)
            ).fetchone()
            if row is None:
                raise KeyError(role_id)
            new_name = row["name"] if name is None else name.strip()
            if not new_name:
                raise ValueError("角色名称不能为空")
            new_prompt = (
                row["system_prompt"] if system_prompt is None else system_prompt
            )
            new_avatar = row["avatar"] if avatar is None else avatar
            try:
                current_onboarding = row["onboarding_status"]
            except (KeyError, IndexError):
                current_onboarding = "none"
            new_onboarding = (
                current_onboarding if onboarding_status is None else onboarding_status
            )
            if new_onboarding not in ("none", "active", "completed", "skipped"):
                raise ValueError(
                    "onboarding_status 必须是 none/active/completed/skipped"
                )
            stamp = _now()
            self.conn.execute(
                """
                UPDATE roles
                SET name = ?, system_prompt = ?, avatar = ?, onboarding_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_name, new_prompt or "", new_avatar, new_onboarding, stamp, role_id),
            )
            self.conn.commit()
            updated = self.conn.execute(
                "SELECT * FROM roles WHERE id = ?", (role_id,)
            ).fetchone()
            assert updated is not None
            return self._row_to_dict(updated)

    def delete(self, role_id: str) -> None:
        with self._lock:
            row = self.conn.execute(
                "SELECT is_default FROM roles WHERE id = ?", (role_id,)
            ).fetchone()
            if row is None:
                raise KeyError(role_id)
            if row["is_default"]:
                raise ValueError("不能删除默认角色")
            self.conn.execute(
                "DELETE FROM role_schedules WHERE role_id = ?", (role_id,)
            )
            self.conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
            self.conn.commit()

    def default_id(self) -> str:
        with self._lock:
            return self.ensure_default_role()

    def _persona_to_dict(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "avatar": row["avatar"],
            "system_prompt": row["system_prompt"] or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_personas(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM api_personas ORDER BY created_at ASC"
            ).fetchall()
            return [self._persona_to_dict(r) for r in rows]

    def get_persona(self, persona_id: str) -> dict:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM api_personas WHERE id = ?", (persona_id,)
            ).fetchone()
            if row is None:
                raise KeyError(persona_id)
            return self._persona_to_dict(row)

    def create_persona(
        self,
        *,
        name: str,
        system_prompt: str = "",
        avatar: str | None = None,
        persona_id: str | None = None,
    ) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("人设名称不能为空")
        pid = (persona_id or _new_id()).strip()
        stamp = _now()
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO api_personas(
                    id, name, avatar, system_prompt, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (pid, name, avatar, system_prompt or "", stamp, stamp),
            )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT * FROM api_personas WHERE id = ?", (pid,)
            ).fetchone()
            assert row is not None
            return self._persona_to_dict(row)

    def update_persona(
        self,
        persona_id: str,
        *,
        name: str | None = None,
        system_prompt: str | None = None,
        avatar: str | None = None,
    ) -> dict:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM api_personas WHERE id = ?", (persona_id,)
            ).fetchone()
            if row is None:
                raise KeyError(persona_id)
            new_name = row["name"] if name is None else name.strip()
            if not new_name:
                raise ValueError("人设名称不能为空")
            new_prompt = (
                row["system_prompt"] if system_prompt is None else system_prompt
            )
            new_avatar = row["avatar"] if avatar is None else avatar
            stamp = _now()
            self.conn.execute(
                """
                UPDATE api_personas
                SET name = ?, system_prompt = ?, avatar = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_name, new_prompt or "", new_avatar, stamp, persona_id),
            )
            self.conn.commit()
            updated = self.conn.execute(
                "SELECT * FROM api_personas WHERE id = ?", (persona_id,)
            ).fetchone()
            assert updated is not None
            return self._persona_to_dict(updated)

    def delete_persona(self, persona_id: str) -> None:
        with self._lock:
            row = self.conn.execute(
                "SELECT id FROM api_personas WHERE id = ?", (persona_id,)
            ).fetchone()
            if row is None:
                raise KeyError(persona_id)
            self.conn.execute("DELETE FROM api_personas WHERE id = ?", (persona_id,))
            self.conn.commit()

    def count_roles_for_persona(self, persona_id: str) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) AS n FROM roles WHERE persona_id = ?",
                (persona_id,),
            ).fetchone()
            return int(row["n"] if row else 0)
