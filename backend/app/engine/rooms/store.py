"""房间参与者与 peer_dm 查找。与 ConversationStore 共用 conn/lock。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.engine.conversation.shared import new_id, now_iso
from app.engine.rooms.schema import (
    ACTOR_ROLE,
    ACTOR_USER,
    KIND_GROUP,
    KIND_OWNER_DM,
    KIND_PEER_DM,
    OWNER_ACTOR_ID,
    ROOM_ROLE_PLACEHOLDER,
    ensure_room_schema,
)

if TYPE_CHECKING:
    from app.engine.conversations import ConversationStore


def peer_key_for(role_a: str, role_b: str) -> str:
    a, b = sorted([(role_a or "").strip(), (role_b or "").strip()])
    if not a or not b or a == b:
        raise ValueError("peer_dm 需要两个不同角色")
    return f"{a}|{b}"


class RoomStore:
    def __init__(self, conversations: ConversationStore) -> None:
        self._store = conversations

    def ensure_schema(self) -> None:
        ensure_room_schema(self._store.conn)

    def backfill_owner_dms(self) -> None:
        """旧会话补 kind=owner_dm 与 user+role 参与者；消息补 speaker。"""
        store = self._store
        from app.engine.roles import DEFAULT_ROLE_ID

        rows = store.conn.execute("SELECT id, role_id, kind FROM conversations").fetchall()
        for row in rows:
            cid = row["id"]
            try:
                kind = (row["kind"] or KIND_OWNER_DM).strip() or KIND_OWNER_DM
            except (KeyError, IndexError):
                kind = KIND_OWNER_DM
            if kind != KIND_OWNER_DM:
                continue
            n = store.conn.execute(
                "SELECT COUNT(*) AS n FROM conversation_participants WHERE conversation_id = ?",
                (cid,),
            ).fetchone()["n"]
            if int(n) > 0:
                continue
            try:
                rid = (row["role_id"] or DEFAULT_ROLE_ID).strip() or DEFAULT_ROLE_ID
            except (KeyError, IndexError):
                rid = DEFAULT_ROLE_ID
            if rid == ROOM_ROLE_PLACEHOLDER:
                continue
            self._add_participant_unlocked(
                cid, ACTOR_USER, OWNER_ACTOR_ID, membership="member"
            )
            self._add_participant_unlocked(cid, ACTOR_ROLE, rid, membership="member")

        store.conn.execute(
            """
            UPDATE messages
            SET speaker_kind = 'user', speaker_id = ?
            WHERE role = 'user' AND (speaker_id IS NULL OR TRIM(speaker_id) = '')
            """,
            (OWNER_ACTOR_ID,),
        )
        # assistant 行：用所属会话 role_id（owner_dm）
        store.conn.execute(
            """
            UPDATE messages
            SET speaker_kind = 'role',
                speaker_id = (
                    SELECT CASE
                        WHEN TRIM(COALESCE(c.role_id, '')) IN ('', ?) THEN ?
                        ELSE c.role_id
                    END
                    FROM conversations c WHERE c.id = messages.conversation_id
                )
            WHERE role = 'assistant' AND (speaker_id IS NULL OR TRIM(speaker_id) = '')
            """,
            (ROOM_ROLE_PLACEHOLDER, DEFAULT_ROLE_ID),
        )

    def _add_participant_unlocked(
        self,
        cid: str,
        actor_kind: str,
        actor_id: str,
        *,
        membership: str = "member",
    ) -> None:
        self._store.conn.execute(
            """
            INSERT OR IGNORE INTO conversation_participants(
                conversation_id, actor_kind, actor_id, membership, last_read_at
            ) VALUES (?, ?, ?, ?, NULL)
            """,
            (cid, actor_kind, actor_id, membership),
        )

    def add_owner_dm_participants(self, cid: str, role_id: str) -> None:
        store = self._store
        with store._lock:
            self._add_participant_unlocked(
                cid, ACTOR_USER, OWNER_ACTOR_ID, membership="member"
            )
            self._add_participant_unlocked(
                cid, ACTOR_ROLE, role_id, membership="member"
            )
            store.conn.commit()

    def conversation_kind(self, cid: str) -> str:
        store = self._store
        with store._lock:
            row = store._conversation_row(cid)
            try:
                kind = (row["kind"] or KIND_OWNER_DM).strip()
            except (KeyError, IndexError):
                kind = KIND_OWNER_DM
            return kind or KIND_OWNER_DM

    def list_role_participants(self, cid: str) -> list[str]:
        store = self._store
        with store._lock:
            rows = store.conn.execute(
                """
                SELECT actor_id FROM conversation_participants
                WHERE conversation_id = ? AND actor_kind = ?
                ORDER BY actor_id
                """,
                (cid, ACTOR_ROLE),
            ).fetchall()
            return [str(r["actor_id"]) for r in rows]

    def is_role_participant(self, cid: str, role_id: str) -> bool:
        store = self._store
        with store._lock:
            row = store.conn.execute(
                """
                SELECT 1 FROM conversation_participants
                WHERE conversation_id = ? AND actor_kind = ? AND actor_id = ?
                """,
                (cid, ACTOR_ROLE, role_id),
            ).fetchone()
            return row is not None

    def find_peer_dm(self, role_a: str, role_b: str) -> str | None:
        key = peer_key_for(role_a, role_b)
        store = self._store
        with store._lock:
            row = store.conn.execute(
                "SELECT id FROM conversations WHERE peer_key = ? AND kind = ?",
                (key, KIND_PEER_DM),
            ).fetchone()
            return str(row["id"]) if row else None

    def find_or_create_peer_dm(
        self,
        role_a: str,
        role_b: str,
        *,
        title: str,
    ) -> str:
        existing = self.find_peer_dm(role_a, role_b)
        if existing:
            return existing
        key = peer_key_for(role_a, role_b)
        store = self._store
        cid = new_id()
        stamp = now_iso()
        with store._lock:
            again = store.conn.execute(
                "SELECT id FROM conversations WHERE peer_key = ? AND kind = ?",
                (key, KIND_PEER_DM),
            ).fetchone()
            if again:
                return str(again["id"])
            store.conn.execute(
                """
                INSERT INTO conversations(
                    id, title, created_at, updated_at, active_turn_id,
                    indexed_dirty, role_id, kind, peer_key
                ) VALUES (?, ?, ?, ?, NULL, 0, ?, ?, ?)
                """,
                (
                    cid,
                    title or "角色协作",
                    stamp,
                    stamp,
                    ROOM_ROLE_PLACEHOLDER,
                    KIND_PEER_DM,
                    key,
                ),
            )
            self._add_participant_unlocked(
                cid, ACTOR_USER, OWNER_ACTOR_ID, membership="observer"
            )
            self._add_participant_unlocked(cid, ACTOR_ROLE, role_a, membership="member")
            self._add_participant_unlocked(cid, ACTOR_ROLE, role_b, membership="member")
            store.conn.commit()
        return cid

    def list_participating_room_ids(self, role_id: str) -> list[str]:
        store = self._store
        with store._lock:
            rows = store.conn.execute(
                """
                SELECT c.id
                FROM conversations c
                JOIN conversation_participants p ON p.conversation_id = c.id
                WHERE p.actor_kind = ? AND p.actor_id = ?
                  AND c.kind IN (?, ?)
                """,
                (ACTOR_ROLE, role_id, KIND_PEER_DM, KIND_GROUP),
            ).fetchall()
            return [str(r["id"]) for r in rows]

    def peer_counterpart(self, cid: str, role_id: str) -> str | None:
        others = [r for r in self.list_role_participants(cid) if r != role_id]
        if len(others) == 1:
            return others[0]
        return None

    def last_responding_role_id(self, cid: str) -> str | None:
        store = self._store
        with store._lock:
            row = store.conn.execute(
                """
                SELECT responding_role_id FROM turns
                WHERE conversation_id = ?
                  AND responding_role_id IS NOT NULL
                  AND TRIM(responding_role_id) != ''
                  AND responding_role_id != ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (cid, ROOM_ROLE_PLACEHOLDER),
            ).fetchone()
            if row is not None:
                rid = str(row["responding_role_id"] or "").strip()
                if rid:
                    return rid
            row = store.conn.execute(
                """
                SELECT speaker_id FROM messages
                WHERE conversation_id = ? AND speaker_kind = ?
                  AND speaker_id IS NOT NULL AND TRIM(speaker_id) != ''
                ORDER BY ts DESC
                LIMIT 1
                """,
                (cid, ACTOR_ROLE),
            ).fetchone()
            if row is None:
                return None
            rid = str(row["speaker_id"] or "").strip()
            return rid or None

    def queued_count(self, room_id: str) -> int:
        store = self._store
        with store._lock:
            row = store.conn.execute(
                """
                SELECT COUNT(*) AS n FROM role_inbound_queue
                WHERE room_id = ? AND status = 'queued'
                """,
                (room_id,),
            ).fetchone()
            return int(row["n"] if row is not None else 0)

    def _row_avatar(self, row) -> str | None:
        try:
            raw = row["avatar"]
        except (KeyError, IndexError):
            return None
        return (str(raw).strip() or None) if raw is not None else None

    def create_group(
        self, *, title: str, role_ids: list[str], avatar: str | None = None
    ) -> str:
        ids: list[str] = []
        seen: set[str] = set()
        for raw in role_ids:
            rid = (raw or "").strip()
            if not rid or rid == ROOM_ROLE_PLACEHOLDER or rid in seen:
                continue
            seen.add(rid)
            ids.append(rid)
        if len(ids) < 2:
            raise ValueError("建群至少需要两个角色")
        name = (title or "").strip() or "群聊"
        pic = (avatar or "").strip() or None
        store = self._store
        cid = new_id()
        stamp = now_iso()
        with store._lock:
            store.conn.execute(
                """
                INSERT INTO conversations(
                    id, title, created_at, updated_at, active_turn_id,
                    indexed_dirty, role_id, kind, peer_key, avatar
                ) VALUES (?, ?, ?, ?, NULL, 0, ?, ?, NULL, ?)
                """,
                (
                    cid,
                    name,
                    stamp,
                    stamp,
                    ROOM_ROLE_PLACEHOLDER,
                    KIND_GROUP,
                    pic,
                ),
            )
            self._add_participant_unlocked(
                cid, ACTOR_USER, OWNER_ACTOR_ID, membership="member"
            )
            for rid in ids:
                self._add_participant_unlocked(
                    cid, ACTOR_ROLE, rid, membership="member"
                )
            store.conn.commit()
        return cid

    def _require_group_unlocked(self, cid: str):
        store = self._store
        row = store._conversation_row(cid)
        try:
            kind = (row["kind"] or "").strip()
        except (KeyError, IndexError):
            kind = ""
        if kind != KIND_GROUP:
            raise ValueError("不是群聊")
        return row

    def update_group(
        self,
        cid: str,
        *,
        title: str | None = None,
        avatar: str | None | object = ...,
        role_ids: list[str] | None = None,
    ) -> dict:
        store = self._store
        stamp = now_iso()
        with store._lock:
            row = self._require_group_unlocked(cid)
            new_title = row["title"]
            if title is not None:
                new_title = (title or "").strip() or "群聊"
            new_avatar = self._row_avatar(row)
            if avatar is not ...:
                new_avatar = (str(avatar).strip() or None) if avatar else None
            store.conn.execute(
                """
                UPDATE conversations
                SET title = ?, avatar = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_title, new_avatar, stamp, cid),
            )
            if role_ids is not None:
                ids: list[str] = []
                seen: set[str] = set()
                for raw in role_ids:
                    rid = (raw or "").strip()
                    if not rid or rid == ROOM_ROLE_PLACEHOLDER or rid in seen:
                        continue
                    seen.add(rid)
                    ids.append(rid)
                if len(ids) < 2:
                    raise ValueError("群至少需要两个角色")
                store.conn.execute(
                    """
                    DELETE FROM conversation_participants
                    WHERE conversation_id = ? AND actor_kind = ?
                    """,
                    (cid, ACTOR_ROLE),
                )
                for rid in ids:
                    self._add_participant_unlocked(
                        cid, ACTOR_ROLE, rid, membership="member"
                    )
            store.conn.commit()
        return self.get_group(cid)

    def delete_group(self, cid: str) -> None:
        store = self._store
        with store._lock:
            self._require_group_unlocked(cid)
        store.delete(cid)

    def get_group(self, cid: str) -> dict:
        store = self._store
        with store._lock:
            row = self._require_group_unlocked(cid)
            return self._group_row_to_dict(row)

    def _group_row_to_dict(self, row) -> dict:
        cid = str(row["id"])
        participants = [
            str(r["actor_id"])
            for r in self._store.conn.execute(
                """
                SELECT actor_id FROM conversation_participants
                WHERE conversation_id = ? AND actor_kind = ?
                ORDER BY actor_id
                """,
                (cid, ACTOR_ROLE),
            ).fetchall()
        ]
        return {
            "id": cid,
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "kind": KIND_GROUP,
            "avatar": self._row_avatar(row),
            "participant_role_ids": participants,
        }

    def group_card_for_role(self, cid: str, role_id: str) -> dict | None:
        """角色时间线用：该角色在此群的最近一次应声，不是群全文。"""
        store = self._store
        rid = (role_id or "").strip()
        if not rid:
            return None
        with store._lock:
            row = store.conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (cid,)
            ).fetchone()
            if row is None:
                return None
            try:
                kind = (row["kind"] or "").strip()
            except (KeyError, IndexError):
                kind = ""
            if kind != KIND_GROUP:
                return None
            last = store.conn.execute(
                """
                SELECT text, ts FROM messages
                WHERE conversation_id = ? AND role = 'assistant'
                  AND speaker_id = ?
                ORDER BY seq DESC
                LIMIT 1
                """,
                (cid, rid),
            ).fetchone()
            active = store.conn.execute(
                """
                SELECT t.id FROM turns t
                JOIN conversations c ON c.active_turn_id = t.id
                WHERE c.id = ? AND t.status = 'running'
                  AND t.responding_role_id = ?
                """,
                (cid, rid),
            ).fetchone()
            excerpt = (last["text"] or "").strip()[:160] if last else ""
            if not excerpt and active is None:
                return None
            created = last["ts"] if last else row["created_at"]
            participants = [
                str(r["actor_id"])
                for r in store.conn.execute(
                    """
                    SELECT actor_id FROM conversation_participants
                    WHERE conversation_id = ? AND actor_kind = ?
                    ORDER BY actor_id
                    """,
                    (cid, ACTOR_ROLE),
                ).fetchall()
            ]
            return {
                "id": cid,
                "title": row["title"],
                "created_at": created,
                "updated_at": row["updated_at"],
                "role_id": rid,
                "kind": "group_card",
                "room_id": cid,
                "avatar": self._row_avatar(row),
                "excerpt": excerpt,
                "card_status": "working" if active is not None else "done",
                "message_count": 1,
                "participant_role_ids": participants,
            }

    def last_activity_for_ids(
        self, ids: list[str], *, max_chars: int = 80
    ) -> dict[str, dict[str, str]]:
        """每个群最近一条消息的时间与单行预览，供左栏与角色混排。"""
        cleaned = [str(i).strip() for i in ids if str(i or "").strip()]
        if not cleaned:
            return {}
        placeholders = ",".join("?" * len(cleaned))
        with self._store._lock:
            rows = self._store.conn.execute(
                f"""
                SELECT m.conversation_id, m.text, m.ts
                FROM messages m
                INNER JOIN (
                    SELECT conversation_id, MAX(seq) AS max_seq
                    FROM messages
                    WHERE conversation_id IN ({placeholders})
                    GROUP BY conversation_id
                ) latest
                  ON latest.conversation_id = m.conversation_id
                 AND latest.max_seq = m.seq
                """,
                cleaned,
            ).fetchall()
        limit = max(16, min(int(max_chars or 80), 200))
        out: dict[str, dict[str, str]] = {}
        for row in rows:
            cid = str(row["conversation_id"])
            collapsed = " ".join((row["text"] or "").split())
            if len(collapsed) > limit:
                collapsed = collapsed[:limit].rstrip() + "…"
            stamp = str(row["ts"] or "").strip()
            out[cid] = {
                "last_active_at": stamp,
                "preview": collapsed,
            }
        return out

    def list_groups(self) -> list[dict]:
        store = self._store
        with store._lock:
            rows = store.conn.execute(
                """
                SELECT id, title, created_at, updated_at, avatar
                FROM conversations
                WHERE kind = ?
                ORDER BY updated_at DESC
                """,
                (KIND_GROUP,),
            ).fetchall()
            return [self._group_row_to_dict(row) for row in rows]

    def list_rooms_for_role(self, role_id: str) -> list[dict]:
        store = self._store
        rid = (role_id or "").strip()
        if not rid:
            return []
        with store._lock:
            rows = store.conn.execute(
                """
                SELECT c.id, c.title, c.created_at, c.updated_at, c.kind, c.avatar
                FROM conversations c
                JOIN conversation_participants p ON p.conversation_id = c.id
                WHERE p.actor_kind = ? AND p.actor_id = ?
                  AND c.kind IN (?, ?)
                ORDER BY c.updated_at DESC
                """,
                (ACTOR_ROLE, rid, KIND_PEER_DM, KIND_GROUP),
            ).fetchall()
            out: list[dict] = []
            for row in rows:
                cid = str(row["id"])
                participants = [
                    str(r["actor_id"])
                    for r in store.conn.execute(
                        """
                        SELECT actor_id FROM conversation_participants
                        WHERE conversation_id = ? AND actor_kind = ?
                        ORDER BY actor_id
                        """,
                        (cid, ACTOR_ROLE),
                    ).fetchall()
                ]
                kind = str(row["kind"] or KIND_PEER_DM)
                out.append(
                    {
                        "id": cid,
                        "title": row["title"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "kind": kind,
                        "avatar": self._row_avatar(row),
                        "participant_role_ids": participants,
                        "peer_role_id": next(
                            (p for p in participants if p != rid), None
                        )
                        if kind == KIND_PEER_DM
                        else None,
                    }
                )
            return out
