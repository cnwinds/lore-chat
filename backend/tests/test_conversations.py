from app.engine.conversations import ConversationStore


def _store(tmp_path):
    return ConversationStore(tmp_path / "conversations")


def test_create_and_get(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    conv = store.get(cid)
    assert conv["id"] == cid
    assert conv["title"] == "新对话"
    assert conv["messages"] == []


def test_list_all_sorted_by_updated(tmp_path):
    store = _store(tmp_path)
    cid1 = store.create()
    cid2 = store.create()
    store.append_exchange(cid1, "第一条", {"role": "assistant", "text": "回复"})
    items = store.list_all()
    assert len(items) == 2
    assert items[0]["id"] == cid1
    assert items[0]["message_count"] == 2


def test_append_exchange_sets_title(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    store.append_exchange(
        cid,
        "windows终端怎么设置utf8编码",
        {"role": "assistant", "text": "可以用 chcp 65001", "intent": "recall"},
    )
    conv = store.get(cid)
    assert conv["title"] == "windows终端怎么设置utf8编码"
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["role"] == "user"
    assert conv["messages"][1]["text"] == "可以用 chcp 65001"


def test_append_messages(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    store.append_messages(
        cid, [{"role": "assistant", "text": "已保存文件", "intent": "remember"}]
    )
    conv = store.get(cid)
    assert len(conv["messages"]) == 1


def test_delete(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    store.delete(cid)
    try:
        store.get(cid)
        assert False, "should raise"
    except KeyError:
        pass


def test_append_exchange_stores_timeline_and_ts(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    assistant = {
        "role": "assistant",
        "ts": "2026-07-10T10:00:00+08:00",
        "timeline": [
            {
                "type": "text",
                "ts": "2026-07-10T10:00:01+08:00",
                "content": "hi",
            }
        ],
        "sources": [],
    }
    store.append_exchange(
        cid, "hello", assistant, user_ts="2026-07-10T09:59:00+08:00"
    )
    conv = store.get(cid)
    assert conv["messages"][0]["ts"] == "2026-07-10T09:59:00+08:00"
    assert conv["messages"][1]["timeline"][0]["type"] == "text"


def test_persistence_across_instances(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    store.append_exchange(cid, "hi", {"role": "assistant", "text": "hello"})
    store2 = _store(tmp_path)
    assert len(store2.get(cid)["messages"]) == 2


def test_migrate_legacy_single_file(tmp_path):
    import json

    legacy = tmp_path / "conversations.json"
    legacy.write_text(
        json.dumps(
            {
                "abc123": {
                    "id": "abc123",
                    "title": "旧会话",
                    "created_at": "2026-07-10T10:00:00",
                    "updated_at": "2026-07-10T11:00:00",
                    "messages": [
                        {"role": "user", "text": "hi", "ts": "2026-07-10T10:00:00"}
                    ],
                    "summarized": False,
                    "summary_path": None,
                    "summarized_at": None,
                    "indexed_dirty": False,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    store = ConversationStore(legacy)
    conv = store.get("abc123")
    assert conv["title"] == "旧会话"
    assert conv["messages"][0]["text"] == "hi"
    assert not legacy.exists()
    assert (tmp_path / "conversations.json.bak").exists()
    assert (tmp_path / "conversations" / "conversations.db").exists()

    # 迁移落到 SQLite 后，重新打开 store 仍能读到同一份数据（不再依赖 JSON 分片）。
    store2 = ConversationStore(tmp_path / "conversations")
    assert store2.get("abc123")["title"] == "旧会话"


def test_begin_and_finalize_turn_assigns_message_ids(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid,
        user_text="你好",
        client_message_id="cli-1",
        observation_allowed=False,
    )
    assert turn["user_message"]["id"]
    assert turn["user_message"]["role"] == "user"
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "你好呀",
            "timeline": [{"type": "text", "content": "你好呀", "ts": "t"}],
            "sources": [],
            "status": "complete",
        },
    )
    conv = store.get(cid)
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["id"]
    assert conv["messages"][1]["in_reply_to_message_id"] == conv["messages"][0]["id"]


def test_finalize_turn_persists_assistant_attachments(tmp_path):
    """生图等工具结果的 attachments 须写入 messages.attachments_json，否则重载后消息脚无图。"""
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="画一只猫", client_message_id="cli-img", observation_allowed=False
    )
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "好的",
            "timeline": [
                {
                    "type": "tool",
                    "id": "t1",
                    "tool": "generate_image",
                    "status": "done",
                    "attachments": ["generated/2026/cat.png"],
                }
            ],
            "attachments": ["generated/2026/cat.png"],
            "sources": [],
            "status": "complete",
        },
    )
    assistant = store.get(cid)["messages"][1]
    assert assistant["attachments"] == ["generated/2026/cat.png"]


def test_message_row_backfills_attachments_from_timeline(tmp_path):
    """旧消息未写 attachments_json 时，读库从 timeline 工具块回填。"""
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="画", client_message_id="cli-old", observation_allowed=False
    )
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "ok",
            "timeline": [
                {
                    "type": "tool",
                    "id": "t1",
                    "tool": "generate_image",
                    "status": "done",
                    "attachments": ["generated/old.png"],
                }
            ],
            "sources": [],
            "status": "complete",
        },
    )
    # 模拟历史行：清空 attachments_json
    with store._lock:
        store.conn.execute(
            "UPDATE messages SET attachments_json = NULL WHERE role = 'assistant'"
        )
        store.conn.commit()
    assistant = store.get(cid)["messages"][1]
    assert assistant["attachments"] == ["generated/old.png"]


def test_duplicate_client_message_id_while_running_raises(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    store.begin_turn(cid, user_text="a", client_message_id="cli-1", observation_allowed=False)
    try:
        store.begin_turn(cid, user_text="a", client_message_id="cli-1", observation_allowed=False)
        assert False, "expected TurnInProgress"
    except Exception as e:
        assert e.__class__.__name__ == "TurnInProgress"


def test_begin_turn_blocks_different_client_message_id_while_running(tmp_path):
    """spec §6.1：单个会话同一时间只允许一个 active turn。"""
    store = _store(tmp_path)
    cid = store.create()
    turn1 = store.begin_turn(
        cid, user_text="a", client_message_id="cli-1", observation_allowed=False
    )
    try:
        store.begin_turn(
            cid, user_text="b", client_message_id="cli-2", observation_allowed=False
        )
        assert False, "expected TurnInProgress"
    except Exception as e:
        assert e.__class__.__name__ == "TurnInProgress"
        assert e.turn_id == turn1["turn_id"]

    store.finalize_turn(
        cid,
        turn_id=turn1["turn_id"],
        assistant={"text": "回复a", "timeline": [], "sources": [], "status": "complete"},
    )
    turn2 = store.begin_turn(
        cid, user_text="b", client_message_id="cli-2", observation_allowed=False
    )
    assert turn2["status"] == "running"
    assert turn2["turn_id"] != turn1["turn_id"]


def test_llm_history_from_timeline(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    store.append_exchange(
        cid,
        "第一轮问题",
        {
            "role": "assistant",
            "timeline": [
                {"type": "tool", "tool": "search_kb", "summary": "找到 1 条"},
                {"type": "text", "content": "第一轮回答"},
            ],
        },
    )
    store.append_exchange(
        cid,
        "追问一下",
        {"role": "assistant", "text": "第二轮回答"},
    )
    history = ConversationStore.llm_history(store.get(cid))
    assert history == [
        {"role": "user", "content": "第一轮问题"},
        {"role": "assistant", "content": "第一轮回答"},
        {"role": "user", "content": "追问一下"},
        {"role": "assistant", "content": "第二轮回答"},
    ]


def test_begin_turn_new_turn_has_running_status(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="你好", client_message_id="cli-1", observation_allowed=False
    )
    assert turn["status"] == "running"


def test_begin_turn_replay_after_complete(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="你好", client_message_id="cli-1", observation_allowed=False
    )
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "你好呀", "timeline": [], "sources": [], "status": "complete"},
    )
    replay = store.begin_turn(
        cid, user_text="你好", client_message_id="cli-1", observation_allowed=False
    )
    assert replay["turn_id"] == turn["turn_id"]
    assert replay["status"] == "complete"
    assert replay["user_message"]["id"] == turn["user_message"]["id"]
    assert replay["assistant_message"]["text"] == "你好呀"


def test_begin_turn_replay_after_interrupted(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="你好", client_message_id="cli-1", observation_allowed=False
    )
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "部分回复", "timeline": [], "sources": [], "status": "interrupted"},
    )
    replay = store.begin_turn(
        cid, user_text="你好", client_message_id="cli-1", observation_allowed=False
    )
    assert replay["status"] == "interrupted"
    assert replay["assistant_message"]["text"] == "部分回复"


def test_begin_turn_replay_after_complete_without_assistant_content(tmp_path):
    """finalize 时若 assistant 无任何内容（无 text/timeline/sources/error），
    不会创建助手消息；重放时 replay 应无 assistant_message 键。"""
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="你好", client_message_id="cli-1", observation_allowed=False
    )
    store.finalize_turn(
        cid, turn_id=turn["turn_id"], assistant={"status": "interrupted"}
    )
    replay = store.begin_turn(
        cid, user_text="你好", client_message_id="cli-1", observation_allowed=False
    )
    assert replay["status"] == "interrupted"
    assert "assistant_message" not in replay


def test_finalize_turn_idempotent_does_not_duplicate_assistant(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="你好", client_message_id="cli-1", observation_allowed=False
    )
    first = store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "第一次", "timeline": [], "sources": [], "status": "complete"},
    )
    second = store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "第二次（应被忽略）", "timeline": [], "sources": [], "status": "complete"},
    )
    assert second is not None
    assert second["id"] == first["id"]
    assert second["text"] == "第一次"
    conv = store.get(cid)
    assert len(conv["messages"]) == 2


def test_finalize_turn_idempotent_returns_none_without_assistant_message(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="你好", client_message_id="cli-1", observation_allowed=False
    )
    store.finalize_turn(cid, turn_id=turn["turn_id"], assistant={"status": "interrupted"})
    result = store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "不应被写入", "status": "complete"},
    )
    assert result is None
    conv = store.get(cid)
    assert len(conv["messages"]) == 1


def test_llm_history_truncates_by_turns(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    for i in range(3):
        store.append_exchange(
            cid,
            f"问题{i}",
            {"role": "assistant", "text": f"回答{i}"},
        )
    history = ConversationStore.llm_history(store.get(cid), max_turns=2)
    assert history == [
        {"role": "user", "content": "问题1"},
        {"role": "assistant", "content": "回答1"},
        {"role": "user", "content": "问题2"},
        {"role": "assistant", "content": "回答2"},
    ]
