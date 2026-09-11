from types import SimpleNamespace

from app.engine.workspace_search import (
    file_hit_from_retriever,
    hit_has_query_evidence,
    match_roles,
    message_hit_from_retriever,
    search_workspace,
    _snippet,
)


def test_match_roles_by_name_or_prompt():
    roles = [
        {"id": "a", "name": "新闻助手", "system_prompt": "写快讯", "avatar": None},
        {"id": "b", "name": "通用", "system_prompt": "知识沉淀", "avatar": None},
    ]
    hits = match_roles(roles, "新闻", k=10)
    assert [h["role_id"] for h in hits] == ["a"]
    prompt_hits = match_roles(roles, "知识", k=10)
    assert [h["role_id"] for h in prompt_hits] == ["b"]


def test_message_and_file_hit_mapping():
    conversations = SimpleNamespace(get_role_id=lambda cid: "default")
    roles = SimpleNamespace(
        get=lambda rid: {"name": "通用", "avatar": None},
    )
    raw = SimpleNamespace(
        source="conv:c1",
        message_id="m1",
        role="user",
        conversation_title="标题",
        chunk="命中片段",
        ts="2026-09-11T00:00:00+08:00",
    )
    msg = message_hit_from_retriever(raw, conversations=conversations, roles=roles)
    assert msg["kind"] == "message"
    assert msg["conversation_id"] == "c1"
    assert msg["role_name"] == "通用"

    file_hit = file_hit_from_retriever(
        SimpleNamespace(source="笔记/a.md", chunk="正文")
    )
    assert file_hit["kind"] == "file"
    assert file_hit["path"] == "笔记/a.md"
    assert file_hit_from_retriever(SimpleNamespace(source="conv:c1", chunk="x")) is None


class _Page:
    def __init__(self, hits, strength="strong"):
        self.hits = hits
        self.match_strength = strength


def test_search_workspace_empty_and_scope():
    retriever = SimpleNamespace(search=lambda *a, **k: _Page([]))
    conversations = SimpleNamespace(list_all=lambda: [], get_role_id=lambda cid: "default")
    roles = SimpleNamespace(list_all=lambda: [], get=lambda rid: {"name": "通用"})
    assert search_workspace(
        retriever=retriever,
        conversations=conversations,
        roles=roles,
        q="  ",
    ) == {"hits": [], "tier": "none"}

    roles = SimpleNamespace(
        list_all=lambda: [
            {"id": "r1", "name": "新闻助手", "system_prompt": "", "avatar": None}
        ],
        get=lambda rid: {"name": "新闻助手", "avatar": None},
    )
    out = search_workspace(
        retriever=retriever,
        conversations=conversations,
        roles=roles,
        q="新闻",
        scope="roles",
    )
    assert out["hits"][0]["kind"] == "role"
    assert out["tier"] == "name"


def test_hit_has_query_evidence_requires_visible_term():
    assert hit_has_query_evidence("请用 svg 画一个角标", "svg")
    assert hit_has_query_evidence("SVG 大师", "svg")
    assert not hit_has_query_evidence("1", "svg")
    assert not hit_has_query_evidence("3", "svg")
    assert not hit_has_query_evidence("先看这张图", "svg")


def test_hit_has_query_evidence_latin_keywords_need_not_be_adjacent():
    blob = "Grok Bot 定时任务结果通知 Slack 集成 scheduled task"
    assert hit_has_query_evidence(blob, "grok slack")
    assert hit_has_query_evidence("只提到了 Grok Bot 深度调研", "grok slack")
    assert not hit_has_query_evidence("完全无关的内容", "grok slack")


def test_match_roles_latin_keywords_need_not_be_adjacent():
    roles = [
        {
            "id": "g",
            "name": "Grok Bot",
            "system_prompt": "把结果发到 Slack 频道",
            "avatar": None,
        },
        {"id": "n", "name": "新闻助手", "system_prompt": "写快讯", "avatar": None},
    ]
    hits = match_roles(roles, "grok slack", k=10)
    assert [h["role_id"] for h in hits] == ["g"]


def test_snippet_centers_on_query():
    text = "前面垫很多无关的字。" * 8 + "这里出现 svg 画法。"
    snippet = _snippet(text, "svg")
    assert "svg" in snippet.casefold()
    assert snippet.startswith("…")


def test_search_workspace_drops_vector_neighbors_without_query():
    conversations = SimpleNamespace(get_role_id=lambda cid: "default")
    roles = SimpleNamespace(
        list_all=lambda: [],
        get=lambda rid: {"name": "通用", "avatar": None},
    )

    def search(query, k=5, **kwargs):
        return _Page(
            [
                SimpleNamespace(
                    source="conv:c-noise",
                    message_id="m-1",
                    role="assistant",
                    conversation_title="1",
                    chunk="1",
                    ts="2026-09-11T00:00:00+08:00",
                ),
                SimpleNamespace(
                    source="conv:c-hit",
                    message_id="m-svg",
                    role="user",
                    conversation_title="发型",
                    chunk="我用 svg 画了这撮头发",
                    ts="2026-09-11T00:00:00+08:00",
                ),
            ]
        )

    out = search_workspace(
        retriever=SimpleNamespace(search=search),
        conversations=conversations,
        roles=roles,
        q="svg",
        scope="messages",
    )
    assert [h["message_id"] for h in out["hits"]] == ["m-svg"]
    assert "svg" in out["hits"][0]["snippet"].casefold()
