from types import SimpleNamespace

from app.engine.workspace_search import (
    file_hit_from_retriever,
    match_roles,
    message_hit_from_retriever,
    search_workspace,
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
