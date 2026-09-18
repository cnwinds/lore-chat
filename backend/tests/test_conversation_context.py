from app.engine.conversation_context import read_conversation_context
from app.engine.conversations import ConversationStore


def _store(tmp_path):
    return ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")


def _finalize(store, cid, turn_id, text):
    store.finalize_turn(
        cid,
        turn_id=turn_id,
        assistant={
            "text": text,
            "timeline": [],
            "sources": [],
            "status": "complete",
        },
    )


def test_read_context_before_after_and_mask(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid,
        user_text="key=sk-abcdefghijklmnopqrstuvwxyz012345",
        client_message_id="c1",
        observation_allowed=False,
    )
    _finalize(store, cid, turn["turn_id"], "收到，已记录")
    turn2 = store.begin_turn(
        cid, user_text="第二条用户消息", client_message_id="c2", observation_allowed=False
    )
    _finalize(store, cid, turn2["turn_id"], "好的")
    msgs = store.get(cid)["messages"]
    anchor_id = msgs[0]["id"]

    out = read_conversation_context(
        store,
        conversation_id=cid,
        message_id=anchor_id,
        before_messages=0,
        after_messages=1,
        max_chars=12000,
    )
    assert out["anchor"]["message_id"] == anchor_id
    assert len(out["messages"]) == 2
    masked = out["messages"][0]["text"]
    assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in masked
    assert "•" in masked
    assert out["messages"][0]["offset_version"] == "unicode-codepoint-v1"
    assert out["messages"][0]["source_available"] is True


def test_read_context_clamps_before_after(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="only", client_message_id="c1", observation_allowed=False
    )
    mid = turn["user_message"]["id"]
    out = read_conversation_context(
        store,
        conversation_id=cid,
        message_id=mid,
        before_messages=99,
        after_messages=99,
        max_chars=12000,
    )
    assert len(out["messages"]) == 1


def test_read_context_truncates_at_char_cap(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    long_text = "甲" * 8000
    turn = store.begin_turn(
        cid, user_text=long_text, client_message_id="c1", observation_allowed=False
    )
    _finalize(store, cid, turn["turn_id"], "乙" * 8000)
    turn2 = store.begin_turn(
        cid, user_text="anchor", client_message_id="c2", observation_allowed=False
    )
    anchor = turn2["user_message"]["id"]
    out = read_conversation_context(
        store,
        conversation_id=cid,
        message_id=anchor,
        before_messages=10,
        after_messages=0,
        max_chars=12000,
    )
    total = sum(len(m["text"]) for m in out["messages"])
    assert total <= 12000
    assert out["truncated"] is True


def test_read_context_tail_without_message_id(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    store.append_exchange(cid, "方案草稿", {"role": "assistant", "text": "先写大纲"})
    store.append_exchange(cid, "继续", {"role": "assistant", "text": "已补细节"})
    out = read_conversation_context(store, conversation_id=cid)
    texts = " ".join(m["text"] for m in out["messages"])
    assert "方案草稿" in texts
    assert "已补细节" in texts
    assert out["anchor"]["conversation_id"] == cid
    assert out["anchor"]["message_id"]


def test_read_context_omitted_ids_uses_prior_segment(tmp_path):
    store = _store(tmp_path)
    prior = store.create()
    store.append_exchange(
        prior, "帮我统计最近一个月的新闻做一个视频", {"role": "assistant", "text": "先对齐范围"}
    )
    current = store.create()
    out = read_conversation_context(store, current_conversation_id=current)
    texts = " ".join(m["text"] for m in out["messages"])
    assert "新闻" in texts
    assert out["anchor"]["conversation_id"] == prior


def test_read_context_no_prior_segment(tmp_path):
    store = _store(tmp_path)
    current = store.create()
    out = read_conversation_context(store, current_conversation_id=current)
    assert out["error"] == "no_prior"
    assert out["messages"] == []


def test_read_context_tail_skips_non_dialogue_roles(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    store.append_exchange(cid, "真正要接续的方案", {"role": "assistant", "text": "记下了"})
    store.append_messages(
        cid,
        [{"role": "tool", "text": "search_kb 命中熔岩尾焰鸟"}] * 12,
    )
    out = read_conversation_context(store, conversation_id=cid)
    texts = " ".join(m["text"] for m in out["messages"])
    assert "真正要接续的方案" in texts
    assert "熔岩尾焰鸟" not in texts
    assert all(m["role"] in ("user", "assistant") for m in out["messages"])


def test_read_context_message_id_resolves_own_conversation(tmp_path):
    store = _store(tmp_path)
    prior = store.create()
    store.append_exchange(prior, "不相关的上一会话", {"role": "assistant", "text": "旧段"})
    target = store.create()
    store.append_exchange(target, "马尔可夫链笔记", {"role": "assistant", "text": "已整理"})
    current = store.create()
    mid = store.get(target)["messages"][0]["id"]
    out = read_conversation_context(
        store,
        message_id=mid,
        current_conversation_id=current,
        before_messages=0,
        after_messages=1,
    )
    texts = " ".join(m["text"] for m in out["messages"])
    assert "马尔可夫链" in texts
    assert "不相关" not in texts
    assert out["anchor"]["conversation_id"] == target


def test_read_context_unknown_message_id_is_not_found(tmp_path):
    store = _store(tmp_path)
    current = store.create()
    out = read_conversation_context(
        store, message_id="missing", current_conversation_id=current
    )
    assert out["error"] == "not_found"
    assert out["messages"] == []
