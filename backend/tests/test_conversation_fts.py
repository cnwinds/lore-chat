from app.index.conversation_fts import ConversationFTS
from app.index.message_chunk import MessageChunk


def test_upsert_and_query_by_message(tmp_path):
    fts = ConversationFTS(tmp_path / "fts.db")
    chunks = [
        MessageChunk(0, 0, 5, "你好世界"),
        MessageChunk(1, 5, 10, "漫剧工具"),
    ]
    fts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-07-14T10:00:00",
        conversation_title="测试",
        chunks=chunks,
    )
    hits = fts.query("漫剧", k=5)
    assert hits
    assert hits[0].message_id == "m1"
    assert hits[0].conversation_id == "c1"


def test_delete_conversation_removes_all_chunks(tmp_path):
    fts = ConversationFTS(tmp_path / "fts.db")
    fts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="t",
        chunks=[MessageChunk(0, 0, 2, "ab")],
    )
    fts.delete_conversation("c1")
    assert fts.query("ab", k=5) == []


def test_latin_keywords_match_when_not_adjacent(tmp_path):
    fts = ConversationFTS(tmp_path / "fts.db")
    text = "Grok Bot 定时任务结果通知 Slack 集成 scheduled task"
    fts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="assistant",
        ts="t",
        conversation_title="调研",
        chunks=[MessageChunk(0, 0, len(text), text)],
    )
    assert fts.query("grok", k=5)
    assert fts.query("slack", k=5)
    out = fts.query_with_tier("grok slack", k=5)
    assert out.hits
    assert out.hits[0].message_id == "m1"
    assert out.tier in ("strict", "relaxed", "like")


def test_latin_keywords_or_when_only_one_word_present(tmp_path):
    fts = ConversationFTS(tmp_path / "fts.db")
    text = "Grok Bot 深度调研会话，没有提到另一个产品。"
    fts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="assistant",
        ts="t",
        conversation_title="调研",
        chunks=[MessageChunk(0, 0, len(text), text)],
    )
    out = fts.query_with_tier("grok slack", k=5)
    assert out.hits
    assert out.tier in ("relaxed", "like")


def test_query_excludes_conversation(tmp_path):
    fts = ConversationFTS(tmp_path / "fts.db")
    fts.upsert_message_chunks(
        conversation_id="current",
        message_id="m1",
        role="user",
        ts="t1",
        conversation_title="当前",
        chunks=[MessageChunk(0, 0, 4, "人脑结构")],
    )
    fts.upsert_message_chunks(
        conversation_id="past",
        message_id="m2",
        role="user",
        ts="t2",
        conversation_title="历史",
        chunks=[MessageChunk(0, 0, 4, "人脑结构")],
    )
    hits = fts.query("人脑", k=5, exclude_conversation_id="current")
    assert len(hits) == 1
    assert hits[0].conversation_id == "past"
    assert hits[0].ts == "t2"
    assert hits[0].conversation_title == "历史"


def test_query_filters_by_ts_range(tmp_path):
    fts = ConversationFTS(tmp_path / "fts.db")
    fts.upsert_message_chunks(
        conversation_id="old",
        message_id="m-old",
        role="user",
        ts="2026-08-12T10:00:00+08:00",
        conversation_title="八月",
        chunks=[MessageChunk(0, 0, 5, "马尔可夫链")],
    )
    fts.upsert_message_chunks(
        conversation_id="yday",
        message_id="m-y",
        role="user",
        ts="2026-09-17T15:30:00+08:00",
        conversation_title="昨天",
        chunks=[MessageChunk(0, 0, 5, "马尔可夫链")],
    )
    hits = fts.query(
        "马尔可夫链",
        k=5,
        ts_after="2026-09-17T00:00:00+08:00",
        ts_before="2026-09-18T00:00:00+08:00",
    )
    assert len(hits) == 1
    assert hits[0].conversation_id == "yday"
