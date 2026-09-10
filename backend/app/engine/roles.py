"""
Role management: store, active conversation resolver, schedule coordination.
"""

import sqlite3
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

DEFAULT_ROLE_ID = "default"
DEFAULT_ROLE_NAME = "通用助手"


class RoleStore:
    """Roles database in {kb}/.kb/roles/roles.db"""

    def __init__(self, kb_root: Path):
        self.db_path = kb_root / ".kb" / "roles" / "roles.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS roles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    avatar TEXT,
                    system_prompt TEXT,
                    is_default INTEGER DEFAULT 0,
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS role_schedules (
                    id TEXT PRIMARY KEY,
                    role_id TEXT NOT NULL,
                    cron TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
                )
            """)
            conn.commit()

        # Ensure default role exists
        self.ensure_default_role()

    def ensure_default_role(self) -> dict[str, Any]:
        """Ensure default role exists, return it."""
        existing = self.get_role(DEFAULT_ROLE_ID)
        if existing:
            return existing

        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO roles (id, name, avatar, system_prompt, is_default, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, 0, ?, ?)
                """,
                (DEFAULT_ROLE_ID, DEFAULT_ROLE_NAME, None, None, now, now),
            )
            conn.commit()
        return self.get_role(DEFAULT_ROLE_ID)  # type: ignore

    def list_roles(self) -> list[dict[str, Any]]:
        """List all roles ordered by sort_order, created_at."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM roles ORDER BY sort_order, created_at"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_role(self, role_id: str) -> dict[str, Any] | None:
        """Get role by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
            return dict(row) if row else None

    def create_role(
        self,
        role_id: str,
        name: str,
        avatar: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Create a new role."""
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO roles (id, name, avatar, system_prompt, is_default, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, 999, ?, ?)
                """,
                (role_id, name, avatar, system_prompt, now, now),
            )
            conn.commit()
        return self.get_role(role_id)  # type: ignore

    def update_role(
        self,
        role_id: str,
        name: str | None = None,
        avatar: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any] | None:
        """Update role fields."""
        role = self.get_role(role_id)
        if not role:
            return None

        now = datetime.now(UTC).isoformat()
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if avatar is not None:
            updates.append("avatar = ?")
            params.append(avatar)
        if system_prompt is not None:
            updates.append("system_prompt = ?")
            params.append(system_prompt)

        if not updates:
            return role

        updates.append("updated_at = ?")
        params.append(now)
        params.append(role_id)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE roles SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()

        return self.get_role(role_id)

    def delete_role(self, role_id: str) -> bool:
        """Delete role (cannot delete default role)."""
        role = self.get_role(role_id)
        if not role or role.get("is_default"):
            return False

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
            conn.commit()
        return True

    # Schedules

    def list_schedules(self, role_id: str) -> list[dict[str, Any]]:
        """List schedules for a role."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM role_schedules WHERE role_id = ? ORDER BY created_at",
                (role_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        """Get schedule by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM role_schedules WHERE id = ?", (schedule_id,)
            ).fetchone()
            return dict(row) if row else None

    def create_schedule(
        self,
        schedule_id: str,
        role_id: str,
        cron: str,
        prompt: str,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create schedule."""
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO role_schedules (id, role_id, cron, prompt, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (schedule_id, role_id, cron, prompt, int(enabled), now, now),
            )
            conn.commit()
        return self.get_schedule(schedule_id)  # type: ignore

    def update_schedule(
        self,
        schedule_id: str,
        cron: str | None = None,
        prompt: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        """Update schedule."""
        schedule = self.get_schedule(schedule_id)
        if not schedule:
            return None

        now = datetime.now(UTC).isoformat()
        updates = []
        params = []

        if cron is not None:
            updates.append("cron = ?")
            params.append(cron)
        if prompt is not None:
            updates.append("prompt = ?")
            params.append(prompt)
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(int(enabled))

        if not updates:
            return schedule

        updates.append("updated_at = ?")
        params.append(now)
        params.append(schedule_id)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE role_schedules SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()

        return self.get_schedule(schedule_id)

    def delete_schedule(self, schedule_id: str) -> bool:
        """Delete schedule."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM role_schedules WHERE id = ?", (schedule_id,))
            conn.commit()
            return cursor.rowcount > 0


def resolve_active_conversation(
    role_id: str,
    conversations_store: Any,  # ConversationsStore
    continuity_idle_hours: float = 6.0,
) -> str:
    """
    Resolve or create active conversation for a role.
    
    1. Prefer empty conversation (message_count == 0) for this role
    2. Otherwise check most recent conversation: if within continuity window, reuse
    3. Otherwise create new conversation
    
    Returns conversation_id
    """
    from datetime import timedelta

    # 1. Check for empty conversation
    convs = conversations_store.list_conversations()
    empty = next(
        (c for c in convs if c.get("role_id") == role_id and c.get("message_count", 0) == 0),
        None,
    )
    if empty:
        return empty["id"]

    # 2. Check most recent conversation within continuity window
    role_convs = [c for c in convs if c.get("role_id") == role_id]
    if role_convs:
        most_recent = max(role_convs, key=lambda c: c.get("updated_at", ""))
        updated_at = datetime.fromisoformat(most_recent["updated_at"].replace("Z", "+00:00"))
        idle_delta = datetime.now(UTC) - updated_at
        if idle_delta < timedelta(hours=continuity_idle_hours):
            return most_recent["id"]

    # 3. Create new conversation
    new_conv = conversations_store.create_conversation(role_id=role_id)
    return new_conv["id"]
