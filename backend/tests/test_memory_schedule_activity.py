"""记忆调度不得污染侧栏活跃时间 / 用户消息 CAS 时钟。"""

from app.engine.conversation.activity_times import repair_activity_times
from app.engine.conversations import ConversationStore


def test_mark_dirty_without_at_keeps_clocks(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    store.begin_turn(cid, "我偏好茶", "c1", observation_allowed=True)
    before = store.conn.execute(
        "SELECT updated_at, last_user_message_at, memory_dirty FROM conversations WHERE id = ?",
        (cid,),
    ).fetchone()
    assert before["memory_dirty"] == 1
    store.conn.execute(
        "UPDATE conversations SET memory_dirty = 0, updated_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00+08:00", cid),
    )
    store.conn.commit()
    frozen_updated = "2026-01-01T00:00:00+08:00"
    last_user = before["last_user_message_at"]

    store.mark_memory_dirty(cid)  # 回填路径：无 at
    row = store.conn.execute(
        "SELECT updated_at, last_user_message_at, memory_dirty FROM conversations WHERE id = ?",
        (cid,),
    ).fetchone()
    assert row["memory_dirty"] == 1
    assert row["updated_at"] == frozen_updated
    assert row["last_user_message_at"] == last_user


def test_batch_mark_dirty_does_not_bump_sidebar_updated_at(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    store.begin_turn(cid, "我偏好茶", "c1", observation_allowed=True)
    store.conn.execute(
        "UPDATE conversations SET updated_at = ?, memory_dirty = 0 WHERE id = ?",
        ("2026-02-02T00:00:00+08:00", cid),
    )
    store.conn.commit()
    last_user = store.get_last_user_message_at(cid)

    n = store.batch_mark_dirty_and_enqueue_session_observe(
        [cid], mark_dirty=True, immediate=True
    )
    assert n == 1
    row = store.conn.execute(
        "SELECT updated_at, last_user_message_at, memory_dirty FROM conversations WHERE id = ?",
        (cid,),
    ).fetchone()
    assert row["updated_at"] == "2026-02-02T00:00:00+08:00"
    assert row["last_user_message_at"] == last_user
    assert row["memory_dirty"] == 1


def test_clear_dirty_does_not_bump_updated_at(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    store.begin_turn(cid, "我偏好茶", "c1", observation_allowed=True)
    store.conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        ("2026-03-03T00:00:00+08:00", cid),
    )
    store.conn.commit()
    snap = store.get_last_user_message_at(cid)
    rev = store.clear_memory_dirty(cid, expected_last_user_message_at=snap)
    assert rev is not None
    row = store.conn.execute(
        "SELECT updated_at, memory_dirty FROM conversations WHERE id = ?",
        (cid,),
    ).fetchone()
    assert row["updated_at"] == "2026-03-03T00:00:00+08:00"
    assert row["memory_dirty"] == 0


def test_repair_activity_times_restores_from_turns_and_summary(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    store.begin_turn(cid, "旧会话内容", "c1", observation_allowed=True)
    # 消息/回合在归档之前；归档抬高侧栏
    msg_at = "2026-08-07T10:00:00+08:00"
    turn_started = "2026-08-07T10:00:01+08:00"
    archive_at = "2026-08-08T20:00:00+08:00"
    store.conn.execute(
        "UPDATE messages SET ts = ? WHERE conversation_id = ?",
        (msg_at, cid),
    )
    store.conn.execute(
        "UPDATE turns SET started_at = ? WHERE conversation_id = ?",
        (turn_started, cid),
    )
    store.conn.execute(
        """
        INSERT INTO conversation_summaries(
            conversation_id, doc_path, revision, covered_through_message_id,
            status, is_primary, created_at
        ) VALUES (?, '归档/旧.md', 1, NULL, 'current', 1, ?)
        """,
        (cid, archive_at),
    )
    # 污染：模拟全量重抽把时钟刷成「现在」
    store.conn.execute(
        """
        UPDATE conversations
        SET updated_at = ?, last_user_message_at = ?
        WHERE id = ?
        """,
        ("2026-08-09T13:06:35+08:00", "2026-08-09T13:06:35+08:00", cid),
    )
    store.conn.commit()

    n = repair_activity_times(store)
    assert n == 1
    row = store.conn.execute(
        "SELECT updated_at, last_user_message_at FROM conversations WHERE id = ?",
        (cid,),
    ).fetchone()
    assert row["last_user_message_at"] == turn_started
    assert row["updated_at"] == archive_at
