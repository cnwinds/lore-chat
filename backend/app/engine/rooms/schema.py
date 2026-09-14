"""房间相关列与表。由 ConversationStore 启动时 ensure。"""

from __future__ import annotations

KIND_OWNER_DM = "owner_dm"
KIND_PEER_DM = "peer_dm"
KIND_GROUP = "group"
ROOM_KINDS = frozenset({KIND_OWNER_DM, KIND_PEER_DM, KIND_GROUP})

OWNER_ACTOR_ID = "owner"
ROOM_ROLE_PLACEHOLDER = "_room"
MAX_HOP = 4
ACTOR_USER = "user"
ACTOR_ROLE = "role"
ACTOR_SYSTEM = "system"


def ensure_room_schema(conn) -> None:
    conv_cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
    if "kind" not in conv_cols:
        conn.execute(
            "ALTER TABLE conversations ADD COLUMN kind TEXT NOT NULL DEFAULT 'owner_dm'"
        )
    if "peer_key" not in conv_cols:
        conn.execute("ALTER TABLE conversations ADD COLUMN peer_key TEXT")
    if "avatar" not in conv_cols:
        conn.execute("ALTER TABLE conversations ADD COLUMN avatar TEXT")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_conversations_peer_key
        ON conversations(peer_key)
        WHERE peer_key IS NOT NULL AND TRIM(peer_key) != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_kind_updated
        ON conversations(kind, updated_at)
        """
    )

    msg_cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()}
    if "speaker_kind" not in msg_cols:
        conn.execute(
            "ALTER TABLE messages ADD COLUMN speaker_kind TEXT NOT NULL DEFAULT 'user'"
        )
    if "speaker_id" not in msg_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN speaker_id TEXT")
    if "speaker_name" not in msg_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN speaker_name TEXT")
    if "causation_id" not in msg_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN causation_id TEXT")
    if "hop" not in msg_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN hop INTEGER NOT NULL DEFAULT 0")

    turn_cols = {r[1] for r in conn.execute("PRAGMA table_info(turns)").fetchall()}
    if "responding_role_id" not in turn_cols:
        conn.execute("ALTER TABLE turns ADD COLUMN responding_role_id TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_participants (
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            actor_kind TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            membership TEXT NOT NULL DEFAULT 'member',
            last_read_at TEXT,
            PRIMARY KEY (conversation_id, actor_kind, actor_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_participants_actor
        ON conversation_participants(actor_kind, actor_id)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS role_inbound_queue (
            id TEXT PRIMARY KEY,
            role_id TEXT NOT NULL,
            room_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            wake_in TEXT NOT NULL DEFAULT 'peer_dm',
            expect_reply INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'queued',
            created_at TEXT NOT NULL,
            claimed_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_inbound_queue_role_status
        ON role_inbound_queue(role_id, status, created_at)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS group_assignments (
            id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            assigner_role_id TEXT NOT NULL,
            assignee_role_id TEXT NOT NULL,
            source_message_id TEXT,
            receipt_message_id TEXT,
            brief TEXT,
            due_in_minutes INTEGER,
            due_at TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            inquired_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_assignments_room_status
        ON group_assignments(room_id, status, created_at)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_group_assignments_due
        ON group_assignments(due_at)
        WHERE due_at IS NOT NULL AND status IN ('open', 'working')
        """
    )
