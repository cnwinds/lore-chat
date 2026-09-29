from app.engine.chat.role_context_prefetch import (
    build_prior_segment_pointer,
    should_prefetch_role_context,
)
from app.engine.conversations import ConversationStore
from app.engine.roles import DEFAULT_ROLE_ID


def _store(tmp_path):
    return ConversationStore(tmp_path / "conversations")


def test_should_prefetch_role_context():
    assert should_prefetch_role_context([]) is True
    assert should_prefetch_role_context(None) is True
    assert should_prefetch_role_context([{"role": "assistant", "content": "x"}]) is True
    assert should_prefetch_role_context([{"role": "user", "content": "hi"}]) is False


def test_pointer_names_prior_segment_without_transcript(tmp_path):
    store = _store(tmp_path)
    prior = store.create(role_id=DEFAULT_ROLE_ID)
    turn = store.begin_turn(
        prior,
        user_text="帮我统计最近一个月的 AI 新闻做一个视频",
        client_message_id="cli-prior",
        observation_allowed=False,
    )
    store.finalize_turn(
        prior,
        turn_id=turn["turn_id"],
        assistant={
            "text": "先对齐范围再动手",
            "timeline": [],
            "sources": [],
            "status": "complete",
        },
    )
    current = store.create(role_id=DEFAULT_ROLE_ID)
    text = build_prior_segment_pointer(store, conversation_id=current)
    assert text is not None
    assert text.startswith("【上一会话段】")
    assert f"conversation://{prior}" in text
    assert "帮我统计最近一个月的 AI 新闻做一个视频" in text
    assert "北京时间" in text
    assert "对话 2 条" in text
    # 只给事实：不带原文，也不复述取回路由（路由以《戒律》「跨段接续」与工具描述为准）
    assert "先对齐范围再动手" not in text
    assert "read_conversation_context" not in text
    assert len(text) < 300


def test_pointer_counts_dialogue_not_tool_rows(tmp_path):
    store = _store(tmp_path)
    prior = store.create(role_id=DEFAULT_ROLE_ID)
    store.append_exchange(prior, "要接续的方案", {"role": "assistant", "text": "已记下"})
    store.append_messages(
        prior, [{"role": "tool", "text": "search_kb 熔岩尾焰鸟"}] * 12
    )
    current = store.create(role_id=DEFAULT_ROLE_ID)
    text = build_prior_segment_pointer(store, conversation_id=current)
    assert text is not None
    assert "对话 2 条" in text


def test_no_prior_segment_injects_nothing(tmp_path):
    store = _store(tmp_path)
    current = store.create(role_id=DEFAULT_ROLE_ID)
    assert build_prior_segment_pointer(store, conversation_id=current) is None


def test_channel_conversation_gets_no_pointer(tmp_path):
    store = _store(tmp_path)
    owner_dm = store.create(role_id=DEFAULT_ROLE_ID)
    store.append_exchange(owner_dm, "主人私聊内容", {"role": "assistant", "text": "好"})
    channel = store.create(role_id=DEFAULT_ROLE_ID, origin="feishu")
    assert build_prior_segment_pointer(store, conversation_id=channel) is None


def test_pointer_masks_secrets_in_title(tmp_path):
    store = _store(tmp_path)
    prior = store.create(role_id=DEFAULT_ROLE_ID)
    store.begin_turn(
        prior,
        user_text="用 sk-abcdefghijklmnopqrstuvwxyz 调接口",
        client_message_id="cli-secret",
        observation_allowed=False,
    )
    current = store.create(role_id=DEFAULT_ROLE_ID)
    text = build_prior_segment_pointer(store, conversation_id=current)
    assert text is not None
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in text
