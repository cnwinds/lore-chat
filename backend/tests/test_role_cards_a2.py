"""角色知识卡 P0 · 包 A2（注入、HTTP、工具、人设修订、清卡）。"""

import pytest

from app.deps import build_container
from app.config import Settings
from app.engine.agent.message_builder import build_agent_messages
from app.engine.agent.prompts import (
    MODE_API,
    MODE_DEFAULT,
    build_role_identity_block,
    build_system_prompt,
    wrap_role_cards,
)
from app.engine.agent.system_layer import SystemLayer, is_unmodified_official
from app.engine.agent.tool_catalog import select_tools
from app.engine.memory.cards import persona_scope, role_scope
from app.engine.roles import RoleStore
from app.engine.usage.request_capture import request_capture_context
from app.engine.usage.request_detail import build_request_detail
from app.engine.usage.request_log import RequestLogRecorder
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


@pytest.fixture
def container(tmp_path):
    kb = tmp_path / "knowledge"
    kb.mkdir(exist_ok=True)
    return build_container(Settings(kb_path=kb))


def _seed_card(cards, scope: str, *, statement: str, card_id: str = "c1") -> str:
    st = cards.store(scope)
    st.upsert_fact(
        slot_key="domain.topic",
        category="domain",
        statement=statement,
        normalized_value_hash=f"h-{card_id}",
        origin="direct",
        status="confirmed",
        fact_id=card_id,
    )
    if cards.index is not None:
        with cards.scope_lock(scope):
            cards.index.sync_scope_locked(scope)
    return card_id


def test_system_prompt_role_cards_between_role_and_memory():
    role_block = build_role_identity_block(name="编辑", system_prompt="你是编辑")
    prompt = build_system_prompt(
        "default",
        "规则",
        user_memory="- 偏好简洁",
        role_system_prompt=role_block,
        role_cards="## 领域知识\n- 先查目录",
    )
    assert prompt.index("【当前角色】") < prompt.index("【角色知识卡】")
    assert prompt.index("【角色知识卡】") < prompt.index("【用户记忆】")
    assert "先查目录" in prompt


def test_system_prompt_omits_role_cards_title_when_empty():
    prompt = build_system_prompt(
        "default",
        role_system_prompt=build_role_identity_block(name="R", system_prompt="人设"),
        role_cards="",
    )
    assert "【角色知识卡】" not in prompt


def test_channel_turn_default_omits_owner_memory(container):
    role = container.roles.create(name="通道用", system_prompt="")
    persona = container.roles.create_persona(name="API人设", system_prompt="客服")
    inst = container.channel_instances.create(
        type_id="script_api",
        name="测试通道",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    container.memory_service.remember("记住我偏好简洁")
    cid = container.conversations.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    inj = container.system_layer.card_injection(
        conversation_id=cid,
        role_id=role["id"],
    )
    assert inj.owner_memory == ""
    prompt = build_system_prompt("default", user_memory=inj.owner_memory)
    assert "【用户记忆】" not in prompt


def test_channel_turn_include_owner_memory_when_enabled(container):
    role = container.roles.create(name="通道用", system_prompt="")
    persona = container.roles.create_persona(name="API人设", system_prompt="客服")
    inst = container.channel_instances.create(
        type_id="script_api",
        name="测试通道",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    container.channel_instances.update(inst["id"], include_owner_memory=True)
    container.memory_service.remember("记住我偏好简洁")
    cid = container.conversations.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    inj = container.system_layer.card_injection(
        conversation_id=cid,
        role_id=role["id"],
    )
    assert "简洁" in inj.owner_memory


def test_patch_channel_instance_include_owner_memory(client):
    persona = client.post(
        "/api/channel-plugins/personas",
        json={"name": "P", "system_prompt": "客服"},
    ).json()
    inst = client.post(
        "/api/channel-plugins/instances",
        json={
            "type_id": "script_api",
            "name": "通道",
            "persona_id": persona["id"],
        },
    ).json()
    assert inst.get("include_owner_memory") is False
    patched = client.patch(
        f"/api/channel-plugins/instances/{inst['id']}",
        json={"include_owner_memory": True},
    ).json()
    assert patched["include_owner_memory"] is True
    listed = client.get("/api/channel-plugins/instances").json()["instances"]
    found = next(i for i in listed if i["id"] == inst["id"])
    assert found["include_owner_memory"] is True


def test_context_stats_system_includes_role_cards(container):
    role = container.roles.create(name="策划", system_prompt="你是策划")
    scope = role_scope(role["id"])
    _seed_card(container.knowledge_cards, scope, statement="归档前先查目录")
    cid = container.conversations.create(role_id=role["id"])
    inj = container.system_layer.card_injection(
        conversation_id=cid, role_id=role["id"]
    )
    messages = build_agent_messages(
        "问",
        mode="default",
        web_enabled=False,
        system_layer_text=container.system_layer.compose_rules(),
        user_memory=inj.owner_memory,
        role_cards=inj.role_cards,
        history=None,
        active_doc_path=None,
        active_doc_paths=None,
        primary_doc_path=None,
        role_system_prompt=role["system_prompt"],
    )
    from unittest.mock import MagicMock

    llm = container.llm
    mock_cand = MagicMock()
    mock_cand.model = "test"
    mock_cand.id = "test"
    mock_cand.thinking = False
    mock_cand.effort = ""
    mock_cand.effort_options = ()
    mock_cand.provider = None
    mock_cand.provider_label = None
    api, ann = llm._materialize(messages, mock_cand)
    store = container.request_log_store
    rec = RequestLogRecorder(store)
    with request_capture_context(conversation_id=cid, turn_id="turn1", round=1):
        call_id = rec.begin(
            model="test",
            model_label="test",
            candidate_id="test",
            api_messages=api,
            annotations=ann,
            tools=None,
            params={},
        )
        rec.finish(call_id, status="ok", prompt_tokens=500)
    row = store.get_call_row(cid, call_id)
    detail = build_request_detail(store, row, limit_tokens=128000)
    sys_msg = next(m for m in detail["messages"] if m["role"] == "system")
    kinds = [s["kind"] for s in sys_msg["segments"]]
    assert "role_cards" in kinds
    blob = " ".join(s["text"] for s in sys_msg["segments"])
    assert "归档前先查目录" in blob


def test_prompt_cache_order_unchanged_with_role_cards():
    messages = build_agent_messages(
        "问题",
        mode="default",
        web_enabled=False,
        system_layer_text="",
        user_memory="",
        role_cards="",
        history=[{"role": "user", "content": "之前"}],
        active_doc_path=None,
        active_doc_paths=None,
        primary_doc_path=None,
    )
    assert "当前时刻" not in messages[0]["content"]
    assert messages[-1]["content"].startswith("【当前时间】")


def test_persona_revision_on_prompt_change(tmp_path):
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="R", system_prompt="初稿")
    revs = roles.list_persona_revisions("role", role["id"])
    assert any(r["source"] == "create" for r in revs)
    roles.update(role["id"], system_prompt="初稿")
    assert len(roles.list_persona_revisions("role", role["id"])) == len(revs)
    roles.update(role["id"], system_prompt="改稿")
    revs2 = roles.list_persona_revisions("role", role["id"])
    assert revs2[0]["source"] == "manual"
    assert revs2[0]["body"] == "改稿"


def test_persona_revision_tool_and_onboarding_sources(tmp_path):
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="R", system_prompt="")
    roles.update(role["id"], system_prompt="工具改", revision_source="tool")
    assert roles.list_persona_revisions("role", role["id"])[0]["source"] == "tool"
    roles.update(role["id"], system_prompt="引导定稿", revision_source="onboarding")
    assert roles.list_persona_revisions("role", role["id"])[0]["source"] == "onboarding"


def test_persona_revision_delete_clears(tmp_path):
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="R", system_prompt="有内容")
    persona = roles.create_persona(name="P", system_prompt="人设")
    assert roles.list_persona_revisions("role", role["id"])
    assert roles.list_persona_revisions("persona", persona["id"])
    roles.delete(role["id"])
    roles.delete_persona(persona["id"])
    assert roles.list_persona_revisions("role", role["id"]) == []
    assert roles.list_persona_revisions("persona", persona["id"]) == []


def test_persona_revision_baseline_only_on_empty_table(tmp_path):
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="已有", system_prompt="旧角色")
    assert not any(
        r["source"] == "baseline"
        for r in roles.list_persona_revisions("role", role["id"])
    )
    roles2 = RoleStore(tmp_path / "roles2")
    roles2.conn.execute(
        "INSERT INTO roles(id, name, avatar, system_prompt, is_default, sort_order, created_at, updated_at) "
        "VALUES ('r1', '种子', NULL, '种子正文', 0, 1, 't', 't')"
    )
    roles2.conn.commit()
    RoleStore(tmp_path / "roles2")
    revs = roles2.list_persona_revisions("role", "r1")
    assert len(revs) == 1
    assert revs[0]["source"] == "baseline"


def test_card_http_list_edit_forget_confirm_reject(client):
    container = client.app.state.container
    role = container.roles.create(name="编辑", system_prompt="")
    scope = role_scope(role["id"])
    card_id = _seed_card(
        container.knowledge_cards,
        scope,
        statement="先列目录",
        card_id="card1",
    )
    listed = client.get("/api/cards", params={"scope": scope}).json()
    assert listed["count"] == 1
    assert listed["cards"][0]["statement"] == "先列目录"
    edited = client.patch(
        f"/api/cards/{card_id}",
        params={"scope": scope},
        json={"statement": "先查目录再写"},
    ).json()
    assert edited["ok"] is True
    st = container.knowledge_cards.store(scope)
    st.upsert_fact(
        slot_key="practice.x",
        category="practice",
        statement="待确认",
        normalized_value_hash="hc",
        origin="direct",
        status="candidate",
        fact_id="cand1",
    )
    assert client.post(
        "/api/cards/cand1/confirm", params={"scope": scope}
    ).json()["ok"] is True
    st.upsert_fact(
        slot_key="lesson.y",
        category="lesson",
        statement="待驳回",
        normalized_value_hash="hr",
        origin="direct",
        status="candidate",
        fact_id="cand2",
    )
    assert client.post(
        "/api/cards/cand2/reject", params={"scope": scope}
    ).json()["ok"] is True
    assert client.post(
        f"/api/cards/{card_id}/forget", params={"scope": scope}
    ).json()["ok"] is True
    assert client.get("/api/cards", params={"scope": scope}).json()["count"] == 1


def test_card_http_invalid_scope_and_owner(client):
    assert client.get("/api/cards", params={"scope": "owner"}).status_code == 400
    assert client.get("/api/cards", params={"scope": "bad"}).status_code == 400
    assert (
        client.get("/api/cards", params={"scope": "role:missing"}).status_code == 404
    )


def test_card_http_scopes_isolated(client):
    container = client.app.state.container
    r1 = container.roles.create(name="A", system_prompt="")
    r2 = container.roles.create(name="B", system_prompt="")
    s1 = role_scope(r1["id"])
    s2 = role_scope(r2["id"])
    _seed_card(container.knowledge_cards, s1, statement="A 专属", card_id="a1")
    assert client.get("/api/cards", params={"scope": s1}).json()["count"] == 1
    assert client.get("/api/cards", params={"scope": s2}).json()["count"] == 0


def test_select_tools_default_and_api_both_include_search():
    default_names = {
        d["function"]["name"] for d in select_tools(MODE_DEFAULT, web_enabled=False)
    }
    api_names = {d["function"]["name"] for d in select_tools(MODE_API, web_enabled=False)}
    assert "search" in default_names
    assert "search" in api_names
    assert "recall_cards" not in default_names


@pytest.mark.asyncio
async def test_recall_cards_current_and_other_roles(container):
    role = container.roles.create(name="研究员", system_prompt="研究")
    scope = role_scope(role["id"])
    _seed_card(container.knowledge_cards, scope, statement="查论文先读摘要")
    cid = container.conversations.create(role_id=role["id"])
    out = await container.agent.tools.execute(
        "search",
        {"query": "摘要", "paths": [f"lore://memory/role/{role['id']}/"]},
        conversation_id=cid,
    )
    memory = out.get("memory") or []
    assert len(memory) == 1
    other = container.roles.create(name="编辑", system_prompt="")
    other_scope = role_scope(other["id"])
    _seed_card(container.knowledge_cards, other_scope, statement="编辑先通读", card_id="e1")
    out2 = await container.agent.tools.execute(
        "search",
        {
            "query": "通读",
            "paths": [f"lore://memory/role/{other['id']}/"],
        },
        conversation_id=cid,
    )
    assert len(out2.get("memory") or []) == 1
    assert "通读" in out2["memory"][0]["text"]


@pytest.mark.asyncio
async def test_recall_cards_persona_and_not_found(container):
    persona = container.roles.create_persona(name="共用", system_prompt="")
    scope = persona_scope(persona["id"])
    _seed_card(container.knowledge_cards, scope, statement="共用领域规则", card_id="p1")
    cid = container.conversations.create(role_id=container.roles.default_id())
    out = await container.agent.tools.execute(
        "search",
        {"query": "规则", "paths": [f"lore://memory/persona/{persona['id']}/"]},
        conversation_id=cid,
    )
    assert len(out.get("memory") or []) == 1
    missing = await container.agent.tools.execute(
        "search",
        {"query": "x", "paths": ["lore://memory/role/不存在/"]},
        conversation_id=cid,
    )
    assert missing["error"] == "not_found"


@pytest.mark.asyncio
async def test_recall_cards_rejects_channel_session(container):
    role = container.roles.create(name="通道", system_prompt="")
    persona = container.roles.create_persona(name="P", system_prompt="")
    inst = container.channel_instances.create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    cid = container.conversations.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    out = await container.agent.tools.execute(
        "search",
        {"query": "x", "paths": ["lore://memory/role/"]},
        conversation_id=cid,
    )
    assert out["error"] == "out_of_scope"


def test_old_precepts_hash_recognized_as_official(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    old_body = """# 戒律 · 行为规约

## 六、用户生成 Skill

5. **长期规矩回本文件**：用户立「以后写 Skill / 写库都要怎样」的规矩 → 修订本文件（先读最小改），不写画像、不写进正在生成的 Skill。判定：规范的是助手怎么做事 → 本文件；规范的是主人是谁 → 画像。
"""
    assert is_unmodified_official(old_body) is False
    layer = SystemLayer(repo)
    seeded = repo.read_doc("系统/戒律.md").body
    assert is_unmodified_official(seeded) is True
    from app.engine.agent import system_layer as sl

    old_full = sl._PRECEPTS_BODY.replace("`search`", "`search_kb`", 1)
    assert (
        sl._seed_hash(old_full)
        == "056728c9070524f12472eda25326e3a40ccf60ee65bce7b731bc895aaddfbaed"
    )
    repo.write_doc(
        "系统/戒律.md",
        {"title": "戒律", "source": "system"},
        old_full,
        commit_msg="old",
    )
    assert is_unmodified_official(old_full) is True


def test_delete_role_purges_cards(client):
    container = client.app.state.container
    role = container.roles.create(name="待删", system_prompt="")
    scope = role_scope(role["id"])
    _seed_card(container.knowledge_cards, scope, statement="会消失", card_id="d1")
    assert client.get("/api/cards", params={"scope": scope}).json()["count"] == 1
    other = container.roles.create(name="保留", system_prompt="")
    other_scope = role_scope(other["id"])
    _seed_card(container.knowledge_cards, other_scope, statement="保留", card_id="k1")
    assert client.delete(f"/api/roles/{role['id']}").status_code == 200
    assert container.knowledge_cards.render(scope) == ""
    assert container.knowledge_cards.render(other_scope)


def test_delete_persona_purges_cards(container):
    persona = container.roles.create_persona(name="待删人设", system_prompt="")
    scope = persona_scope(persona["id"])
    _seed_card(container.knowledge_cards, scope, statement="人设卡", card_id="pd1")
    other = container.roles.create_persona(name="保留人设", system_prompt="")
    other_scope = persona_scope(other["id"])
    _seed_card(container.knowledge_cards, other_scope, statement="留着", card_id="pk1")
    container.open_api.delete_persona(persona["id"])
    assert container.knowledge_cards.render(scope) == ""
    assert "留着" in container.knowledge_cards.render(other_scope)
