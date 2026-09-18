from types import SimpleNamespace

from app.engine.chat.role_context_prefetch import (
    build_prefetch_system_message,
    should_prefetch_role_context,
)
from app.engine.conversations import ConversationStore
from app.engine.roles import DEFAULT_ROLE_ID


class _KeywordRetriever:
    def __init__(self, hits):
        self.hits = hits

    def search(self, query, **kwargs):
        del query
        if kwargs.get("scope") == "knowledge":
            return SimpleNamespace(hits=[])
        return SimpleNamespace(hits=self.hits)


def _store(tmp_path):
    return ConversationStore(tmp_path / "conversations")


def test_should_prefetch_role_context():
    assert should_prefetch_role_context([]) is True
    assert should_prefetch_role_context(None) is True
    assert should_prefetch_role_context([{"role": "assistant", "content": "x"}]) is True
    assert should_prefetch_role_context([{"role": "user", "content": "hi"}]) is False


def test_prefetch_includes_prior_segment_not_just_keyword_hits(tmp_path):
    store = _store(tmp_path)
    prior = store.create(role_id=DEFAULT_ROLE_ID)
    store.append_exchange(
        prior,
        "帮我统计最近一个月的 AI 新闻做一个视频",
        {"role": "assistant", "text": "先对齐范围再动手"},
    )
    current = store.create(role_id=DEFAULT_ROLE_ID)
    old_hit = SimpleNamespace(
        chunk="熔岩尾焰鸟单键三态方案",
        source="conv:oldgame",
        conversation_title="熔岩尾焰鸟",
        message_id="m1",
        role="assistant",
        ts="2026-08-12T10:28:41+08:00",
    )
    text = build_prefetch_system_message(
        retriever=_KeywordRetriever([old_hit]),
        conversations=store,
        query="帮我把这个方案记入备忘录里面，作为一个待办。",
        role_id=DEFAULT_ROLE_ID,
        exclude_conversation_id=current,
    )
    assert text is not None
    assert "本角色上一会话段" in text
    assert "AI 新闻做一个视频" in text
    assert "默认指向此段" in text
    assert "熔岩尾焰鸟" in text
    assert "相关历史会话（按相关度，可能早于上一会话段）" in text


def test_prefetch_without_retriever_still_injects_prior(tmp_path):
    store = _store(tmp_path)
    prior = store.create(role_id=DEFAULT_ROLE_ID)
    store.append_exchange(prior, "接着做", {"role": "assistant", "text": "好"})
    current = store.create(role_id=DEFAULT_ROLE_ID)
    text = build_prefetch_system_message(
        retriever=None,
        conversations=store,
        query="把那个记一下",
        role_id=DEFAULT_ROLE_ID,
        exclude_conversation_id=current,
    )
    assert text is not None
    assert "接着做" in text
    assert "（无足够相关命中）" in text


def test_prefetch_prior_tail_skips_tool_rows(tmp_path):
    store = _store(tmp_path)
    prior = store.create(role_id=DEFAULT_ROLE_ID)
    store.append_exchange(prior, "要接续的方案", {"role": "assistant", "text": "已记下"})
    store.append_messages(
        prior, [{"role": "tool", "text": "search_kb 熔岩尾焰鸟"}] * 12
    )
    current = store.create(role_id=DEFAULT_ROLE_ID)
    text = build_prefetch_system_message(
        retriever=None,
        conversations=store,
        query="把那个记一下",
        role_id=DEFAULT_ROLE_ID,
        exclude_conversation_id=current,
    )
    assert text is not None
    assert "要接续的方案" in text
    assert "熔岩尾焰鸟" not in text
