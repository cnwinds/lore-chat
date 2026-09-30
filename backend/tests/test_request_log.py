"""请求快照：分段、采集、保留、API。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.engine.agent.message_builder import build_agent_messages
from app.engine.agent.prompt_parts import PARTS_KEY, copy_tag_history, tag
from app.engine.agent.prompts import build_system_prompt, build_role_collab_block
from app.engine.usage.request_capture import request_capture_context
from app.engine.usage.request_detail import build_request_detail
from app.engine.usage.request_log import (
    REQUEST_LOG_TURNS_PER_CONVERSATION,
    RequestLogRecorder,
    RequestLogStore,
)
from app.engine.usage.request_segment import (
    annotate,
    sanitize_api_message,
    segments_for_api_message,
)
from app.engine.usage.context_stats import build_context_stats
from app.engine.usage.tokens import estimate_tokens
from app.main import create_app
from app.models.llm import OpenAILLMClient, ToolCall


class _Models:
    def context_limit(self, _model, _provider):
        return 128000


class _Usage:
    def conversation_usage_totals(self, _cid):
        return {
            "last_prompt_tokens": 50,
            "last_model": "m",
            "cache_tokens": 0,
            "prompt_tokens": 0,
            "cost_total": None,
            "turns_with_usage": 0,
        }


def test_build_system_prompt_unchanged_with_parts():
    from app.engine.agent.prompts import build_system_prompt_parts

    kwargs = {
        "mode": "default",
        "system_layer_text": "规则",
        "user_memory": "记忆",
        "role_system_prompt": "人设",
        "role_cards": "卡片",
    }
    joined = "".join(p["text"] for p in build_system_prompt_parts(**kwargs))
    assert joined == build_system_prompt(**kwargs)


def test_sanitize_preserves_text_urls():
    msg = {
        "role": "user",
        "content": "见 https://example.com/path?token=secret#frag",
    }
    out = sanitize_api_message(msg)
    assert out["content"] == msg["content"]


def test_sanitize_media_strips_query():
    msg = {
        "role": "user",
        "content": [
            {"type": "text", "text": "图"},
            {
                "type": "image_url",
                "image_url": {"url": "https://cdn/x.png?sig=abc"},
            },
        ],
    }
    out = sanitize_api_message(msg)
    url = out["content"][1]["image_url"]["url"]
    assert "sig=" not in url
    assert url.endswith("/x.png")


def test_sanitize_data_url_in_media():
    raw = "data:image/png;base64," + ("A" * 80)
    msg = {
        "role": "user",
        "content": [{"type": "image_url", "image_url": {"url": raw}}],
    }
    out = sanitize_api_message(msg)
    stored = json.dumps(out)
    assert "base64" not in stored
    assert "data:" in out["content"][0]["image_url"]["url"]


def test_annotate_leading_whitespace():
    text = "\n【块】\n正文"
    parts = [{"kind": "rules", "label": "块", "text": "【块】\n正文"}]
    segs = annotate(text, parts)
    assert "".join(s["text"] for s in segs) == text


def test_full_assembly_segments(tmp_path):
    from app.models.candidate import ModelCandidate

    kb = tmp_path / "knowledge"
    (kb / "uploads").mkdir(parents=True)
    (kb / "uploads" / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    llm = OpenAILLMClient(Settings(kb_path=kb))
    cand = ModelCandidate(
        id="vision",
        model="gpt-4o",
        api_key="k",
        base_url="https://example.com/v1",
        image=True,
        video=False,
    )
    role_list = [{"id": "r1", "name": "A", "system_prompt": "职责"}]
    collab = build_role_collab_block(role_list, current_role_id="r1")
    extra = [
        tag({"role": "system", "content": "【Skill 目录】\nx"}, "skill_catalog", label="Skill 目录"),
        tag({"role": "system", "content": "【已激活 Skill】\ny"}, "skill_active", label="pkg"),
        tag({"role": "system", "content": "【预取】\nz"}, "prefetch", label="预取上下文"),
        tag({"role": "system", "content": collab}, "role_collab", label="角色协作"),
        tag({"role": "system", "content": "【附加】\nextra"}, "extra", label="附加"),
    ]
    history = [
        copy_tag_history({"role": "user", "content": "主人话"}),
        copy_tag_history({"role": "assistant", "content": "助手话"}),
        copy_tag_history({"role": "user", "content": "【同伴消息】\n同伴"}),
        copy_tag_history({"role": "user", "content": "【系统通知】\n通知"}),
    ]
    messages = build_agent_messages(
        "正文问题",
        mode="default",
        web_enabled=False,
        system_layer_text="心法戒律",
        user_memory="主人记忆体",
        role_system_prompt="角色人设",
        role_cards="卡片正文",
        history=history,
        active_doc_path="docs/a.md",
        active_doc_paths=["docs/a.md"],
        primary_doc_path="docs/a.md",
        extra_system_messages=extra,
        turn_cards="轮卡片",
        attachments=["uploads/pic.png"],
    )
    api, ann = llm._materialize(messages, cand)
    assert PARTS_KEY not in json.dumps(api)
    assert len(api) == 6  # 合并后 system + 4 条历史 + 本轮多模态 user
    sys_body, sys_segs = None, None
    user_body, user_segs = None, None
    history_segs: list[list] = []
    for i, m in enumerate(api):
        segs = segments_for_api_message(m, ann[i])
        if m["role"] == "system" and sys_body is None:
            sys_body, sys_segs = m, segs
        elif m["role"] == "user" and isinstance(m.get("content"), list):
            user_body, user_segs = m, segs
        elif any(s["kind"] == "history" for s in segs):
            history_segs.append(segs)
    assert sys_body is not None and user_body is not None
    assert len(history_segs) == 4
    history_labels = [s[0]["label"] for s in history_segs]
    assert history_labels == ["主人", "助手", "同伴消息", "系统通知"]
    sys_text = sys_body["content"]
    assert "".join(s["text"] for s in sys_segs) == sys_text
    assert not any(s["kind"] == "unlabeled" for s in sys_segs)
    kinds = [s["kind"] for s in sys_segs]
    for k in ("rules", "role", "role_cards", "owner_memory", "tray", "skill_catalog", "skill_active", "prefetch", "role_collab", "extra"):
        assert k in kinds
    user_text = "".join(
        p["text"] for p in user_body["content"] if p.get("type") == "text"
    )
    assert "".join(s["text"] for s in user_segs if not s.get("media")) == user_text
    assert not any(s["kind"] == "unlabeled" for s in user_segs if not s.get("media"))
    assert any(s["kind"] == "attachment" for s in user_segs)
    assert user_segs[0]["kind"] == "time"


def test_parts_not_in_api_messages():
    llm = OpenAILLMClient(Settings())
    cand = MagicMock()
    msgs = build_agent_messages(
        "你好",
        mode="default",
        web_enabled=False,
        system_layer_text="层",
        user_memory="",
        history=None,
        active_doc_path=None,
        active_doc_paths=None,
        primary_doc_path=None,
    )
    api, _ = llm._materialize(msgs, cand)
    assert PARTS_KEY not in json.dumps(api)


def test_token_allocation_consistent(tmp_path):
    store = RequestLogStore(tmp_path / "r.db")
    rec = RequestLogRecorder(store)
    tools = [{"type": "function", "function": {"name": "read_doc", "description": "读", "parameters": {}}}]
    msg = [
        {"role": "system", "content": "sys " * 100},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "read_doc", "arguments": '{"path":"a"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": '{"ok":true}'},
    ]
    ann = [{"parts": []}, {"parts": [{"kind": "tool_call", "label": "调用 read_doc", "text": ""}]}, {"parts": []}]
    with request_capture_context(conversation_id="c1", turn_id="t1", round=1):
        cid = rec.begin(
            model="m",
            model_label="M",
            candidate_id="c",
            api_messages=msg,
            annotations=ann,
            tools=tools,
            params={},
        )
        rec.finish(cid, status="ok", prompt_tokens=500)
    row = store.get_call_row("c1", cid)
    detail = build_request_detail(store, row, limit_tokens=128000)
    cat_sum = sum(c["tokens"] for c in detail["categories"])
    msg_sum = sum(m["tokens"] for m in detail["messages"])
    tool_sum = sum(t["tokens"] for t in detail["tools"])
    assert cat_sum == 500 == msg_sum + tool_sum
    asst = next(m for m in detail["messages"] if m["role"] == "assistant")
    assert asst["tokens"] > 0


@pytest.mark.asyncio
async def test_tool_loop_capture_two_rounds(tmp_path):
    from app.engine.agent.tool_loop import AgentToolLoop
    from app.engine.agent.tools import ToolRegistry
    from app.engine.organizer import Organizer
    from app.engine.pending import PendingStore
    from app.engine.retriever import Retriever
    from app.engine.web.fetcher import WebFetcher
    from app.engine.web.search import WebSearch
    from app.index.indexer import Indexer
    from app.models.cooldown import CooldownStore
    from app.models.llm import ChatStreamChunk, ChatWithToolsResult
    from app.storage.repo import KnowledgeRepo
    from tests.helpers import make_writer, make_search_index

    settings = Settings(
        kb_path=tmp_path / "knowledge",
        chat_models=[{"id": "c1", "model": "m", "provider": "p", "base_url": "http://x", "api_key": "k"}],
    )
    store = RequestLogStore(tmp_path / "knowledge/.kb/usage/requests.db")
    llm = OpenAILLMClient(settings, request_log=RequestLogRecorder(store))
    repo = KnowledgeRepo(tmp_path / "knowledge")
    si = make_search_index(tmp_path, llm)
    retr = Retriever(si, llm)
    pending = PendingStore(tmp_path / "knowledge/.kb/pending.json")
    writer = make_writer(repo, tmp_path)
    org = Organizer(repo=repo, retriever=retr, pending=pending, llm=llm, knowledge_writer=writer)
    registry = ToolRegistry(
        retr,
        repo,
        org,
        WebFetcher(5, 1000),
        WebSearch(settings, cooldown=CooldownStore(settings.kb_path / ".kb/s.json")),
        pending,
        writer,
    )
    captured: list[dict] = []
    rounds = 0

    def _chunk(content=None, tool_calls=None, finish_reason=None, usage=None):
        delta = SimpleNamespace(content=content, tool_calls=tool_calls or [])
        choice = SimpleNamespace(delta=delta, finish_reason=finish_reason)
        return SimpleNamespace(choices=[choice], usage=usage)

    def _stream_factory(round_idx):
        def _gen():
            if round_idx == 1:
                yield _chunk(
                    tool_calls=[
                        SimpleNamespace(
                            index=0,
                            id="1",
                            function=SimpleNamespace(
                                name="search_kb",
                                arguments='{"query":"x"}',
                            ),
                        )
                    ],
                    finish_reason="tool_calls",
                    usage=SimpleNamespace(prompt_tokens=10, completion_tokens=1),
                )
            else:
                yield _chunk(
                    content="done",
                    finish_reason="stop",
                    usage=SimpleNamespace(prompt_tokens=20, completion_tokens=2),
                )

        return _gen()

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = (
        lambda **kw: (_stream_factory(1), captured.append(kw))[0]
        if len(captured) == 0
        else (_stream_factory(2), captured.append(kw))[0]
    )
    llm._client_for = lambda _c: mock_client  # type: ignore[method-assign]
    llm._select = lambda **kw: SimpleNamespace(  # type: ignore[method-assign]
        candidate=SimpleNamespace(
            id="c1",
            model="m",
            provider="p",
            thinking=False,
            effort="",
            effort_options=(),
            provider_label=None,
            base_url="http://x",
            api_key="k",
        ),
        failover=False,
        skipped=[],
    )

    loop = AgentToolLoop(settings, llm, registry)
    async for _ in loop.stream(
        [{"role": "user", "content": "q"}],
        tools_for_run=[{"type": "function", "function": {"name": "search_kb", "description": "d", "parameters": {}}}],
        conversation_id="cid",
        active_doc_path=None,
        turn_id="t1",
    ):
        pass
    calls = store.list_calls("cid")
    assert len(calls) == 2
    assert calls[0]["round"] == 2
    assert PARTS_KEY not in json.dumps(captured)
    bodies = store.load_message_bodies(int(calls[0]["id"]))
    roles = [b[0]["role"] for b in bodies]
    assert "assistant" in roles and "tool" in roles
    by_round = {c["round"]: c for c in calls}
    assert [by_round[1]["prompt_tokens"], by_round[2]["prompt_tokens"]] == [10, 20]
    assert {c["status"] for c in calls} == {"ok"}
    kinds = [s["kind"] for _, segs in bodies for s in segs]
    assert "tool_result" in kinds
    for rnd, sent in ((1, captured[0]), (2, captured[1])):
        raw = store.build_raw_request(store.get_call_row("cid", by_round[rnd]["id"]))
        assert json.loads(json.dumps(raw)) == json.loads(json.dumps(sent))


def test_abort_and_error_status(tmp_path):
    store = RequestLogStore(tmp_path / "r.db")
    rec = RequestLogRecorder(store)
    msg = [{"role": "user", "content": "hi"}]
    with request_capture_context(conversation_id="c1", turn_id="t1", round=1):
        cid = rec.begin(
            model="m",
            model_label="M",
            candidate_id="c",
            api_messages=msg,
            annotations=[{"parts": []}],
            tools=None,
            params={},
        )
        rec.finish(cid, status="aborted", error="用户中断")
    row = store.get_call_row("c1", cid)
    assert row["status"] == "aborted"
    with request_capture_context(conversation_id="c1", turn_id="t1", round=2):
        cid2 = rec.begin(
            model="m",
            model_label="M",
            candidate_id="c",
            api_messages=msg,
            annotations=[{"parts": []}],
            tools=None,
            params={},
        )
        rec.finish(cid2, status="error", error="provider down")
    assert store.get_call_row("c1", cid2)["error"] == "provider down"


def test_begin_failure_does_not_break(tmp_path):
    store = RequestLogStore(tmp_path / "r.db")
    with patch.object(store, "_begin_impl", side_effect=RuntimeError("boom")):
        rec = RequestLogRecorder(store)
        with request_capture_context(conversation_id="c", turn_id="t", round=1):
            assert rec.begin(
                model="m",
                model_label="M",
                candidate_id="c",
                api_messages=[{"role": "user", "content": "x"}],
                annotations=[{}],
                tools=None,
                params={},
            ) is None


def test_begin_failure_mid_write_leaves_no_partial_rows(tmp_path):
    store = RequestLogStore(tmp_path / "r.db")
    rec = RequestLogRecorder(store)
    # 第二条消息无法序列化：调用行与第一条的 blob 已写入，之后才失败
    with request_capture_context(conversation_id="c1", turn_id="bad", round=1):
        assert rec.begin(
            model="m",
            model_label="M",
            candidate_id="c",
            api_messages=[
                {"role": "user", "content": "partial"},
                {"role": "user", "content": object()},
            ],
            annotations=[{}, {}],
            tools=None,
            params={},
        ) is None
    _record_call(
        rec,
        conversation_id="c1",
        turn_id="good",
        messages=[{"role": "user", "content": "ok"}],
    )
    assert [r["turn_id"] for r in store.list_calls("c1")] == ["good"]
    assert _blob_count(store) == 1


def test_no_capture_without_turn_id(tmp_path):
    store = RequestLogStore(tmp_path / "r.db")
    rec = RequestLogRecorder(store)
    with request_capture_context(conversation_id="c1", turn_id="", round=1):
        assert rec.begin(
            model="m",
            model_label="M",
            candidate_id="c",
            api_messages=[{"role": "user", "content": "x"}],
            annotations=[{}],
            tools=None,
            params={},
        ) is None


def _record_call(rec, *, conversation_id, turn_id, messages, tools=None, round=1):
    with request_capture_context(
        conversation_id=conversation_id, turn_id=turn_id, round=round
    ):
        call_id = rec.begin(
            model="m",
            model_label="M",
            candidate_id="c",
            api_messages=messages,
            annotations=[{} for _ in messages],
            tools=tools,
            params={},
        )
    rec.finish(call_id, status="ok", prompt_tokens=1)
    return call_id


def _blob_count(store) -> int:
    with store._lock:
        return store.conn.execute("SELECT COUNT(*) FROM request_blobs").fetchone()[0]


def test_retention_drops_oldest_turn_and_its_blobs(tmp_path):
    store = RequestLogStore(tmp_path / "r.db")
    rec = RequestLogRecorder(store)
    shared = {"role": "system", "content": "shared"}
    for i in range(REQUEST_LOG_TURNS_PER_CONVERSATION + 1):
        _record_call(
            rec,
            conversation_id="c1",
            turn_id=f"t{i}",
            messages=[shared, {"role": "user", "content": f"only{i}"}],
        )
    turns = [r["turn_id"] for r in store.list_calls("c1")]
    assert len(turns) == REQUEST_LOG_TURNS_PER_CONVERSATION
    assert "t0" not in turns
    # 共享的 system 一份 + 留下的每个回合各一条独占 user
    assert _blob_count(store) == 1 + REQUEST_LOG_TURNS_PER_CONVERSATION


def test_global_cap_evicts_oldest_calls_and_their_blobs(tmp_path, monkeypatch):
    monkeypatch.setattr("app.engine.usage.request_log.REQUEST_LOG_MAX_CALLS", 3)
    store = RequestLogStore(tmp_path / "r.db")
    rec = RequestLogRecorder(store)
    for i in range(5):
        _record_call(
            rec,
            conversation_id=f"c{i}",
            turn_id="t",
            messages=[{"role": "user", "content": f"only{i}"}],
        )
    remaining = [c["conversation_id"] for i in range(5) for c in store.list_calls(f"c{i}")]
    assert remaining == ["c2", "c3", "c4"]
    assert _blob_count(store) == 3


def test_store_operations_do_not_deadlock(tmp_path):
    import threading

    store = RequestLogStore(tmp_path / "r.db")
    rec = RequestLogRecorder(store)
    tools = [{"type": "function", "function": {"name": "f", "description": "d"}}]
    errors: list[BaseException] = []
    done = threading.Event()

    def _work():
        try:
            for i in range(REQUEST_LOG_TURNS_PER_CONVERSATION + 2):
                _record_call(
                    rec,
                    conversation_id="c1",
                    turn_id=f"t{i}",
                    messages=[{"role": "user", "content": f"q{i}"}],
                    tools=tools,
                )
                row = store.get_call_row("c1", "latest")
                build_request_detail(store, row, limit_tokens=None)
                store.build_raw_request(row)
                store.pick_stats_row("c1")
            store.delete_conversation("c1")
        except BaseException as e:  # noqa: BLE001
            errors.append(e)
        finally:
            done.set()

    worker = threading.Thread(target=_work, daemon=True)
    worker.start()
    worker.join(timeout=10)
    assert done.is_set(), "请求记录存储疑似死锁：10 秒内未完成"
    assert not errors, errors
    assert store.list_calls("c1") == []
    assert _blob_count(store) == 0


def test_delete_for_role(tmp_path):
    from app.engine.conversations import ConversationStore
    from app.engine.roles import RoleStore

    kb = tmp_path / "knowledge"
    store = RequestLogStore(kb / ".kb/usage/requests.db")
    convs = ConversationStore(kb / ".kb/conversations")
    convs._request_log_store = store
    roles = RoleStore(kb / ".kb/roles")
    role = roles.create(name="r", system_prompt="p")
    cid = convs.create(role_id=role["id"])
    rec = RequestLogRecorder(store)
    with request_capture_context(conversation_id=cid, turn_id="t1", round=1):
        call_id = rec.begin(
            model="m",
            model_label="M",
            candidate_id="c",
            api_messages=[{"role": "user", "content": "x"}],
            annotations=[{"parts": []}],
            tools=None,
            params={},
        )
        rec.finish(call_id, status="ok", prompt_tokens=1)
    convs.delete_for_role(role["id"])
    assert store.list_calls(cid) == []


@pytest.fixture
def client(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge")
    app = create_app(settings=settings)
    with TestClient(app) as c:
        sid = app.state.session_store.create()
        c.cookies.set("lorechat_session", sid)
        yield c, app


def test_api_requests(client):
    c, app = client
    cid = c.post("/api/conversations", json={"title": "r"}).json()["id"]
    assert c.get(f"/api/conversations/{cid}/requests").json()["calls"] == []
    assert c.get("/api/conversations/nope/requests/1").status_code == 404
    assert c.get(f"/api/conversations/{cid}/requests/not-a-number").status_code == 404


def test_api_requests_detail_and_scoping(client):
    c, app = client
    cid_a = c.post("/api/conversations", json={"title": "a"}).json()["id"]
    cid_b = c.post("/api/conversations", json={"title": "b"}).json()["id"]
    rec = RequestLogRecorder(app.state.container.request_log_store)
    tools = [
        {
            "type": "function",
            "function": {"name": "f", "description": "d", "parameters": {}},
        }
    ]
    ids = []
    for rnd in (1, 2):
        with request_capture_context(conversation_id=cid_a, turn_id="t1", round=rnd):
            call_id = rec.begin(
                model="m",
                model_label="M",
                candidate_id="c",
                api_messages=[{"role": "user", "content": f"r{rnd}"}],
                annotations=[{}],
                tools=tools,
                params={"temperature": 0.2, "stream": True},
            )
        rec.finish(call_id, status="ok", prompt_tokens=30)
        ids.append(call_id)

    listed = c.get(f"/api/conversations/{cid_a}/requests").json()["calls"]
    assert [x["id"] for x in listed] == [ids[1], ids[0]]
    assert listed[0]["tool_count"] == 1

    latest = c.get(f"/api/conversations/{cid_a}/requests/latest").json()
    assert latest["id"] == ids[1]
    assert [t["name"] for t in latest["tools"]] == ["f"]
    parts_total = sum(m["tokens"] for m in latest["messages"]) + sum(
        t["tokens"] for t in latest["tools"]
    )
    assert parts_total == 30 == sum(cat["tokens"] for cat in latest["categories"])

    assert c.get(f"/api/conversations/{cid_b}/requests/{ids[0]}").status_code == 404
    assert c.get(f"/api/conversations/{cid_b}/requests/{ids[0]}/raw").status_code == 404

    raw = c.get(f"/api/conversations/{cid_a}/requests/{ids[0]}/raw").json()
    assert raw == {
        "model": "m",
        "messages": [{"role": "user", "content": "r1"}],
        "tools": tools,
        "temperature": 0.2,
        "stream": True,
    }


def test_context_stats_with_capture(client):
    c, app = client
    cid = c.post("/api/conversations", json={"title": "s"}).json()["id"]
    store = app.state.container.request_log_store
    rec = RequestLogRecorder(store)
    with request_capture_context(conversation_id=cid, turn_id="t1", round=1):
        call_id = rec.begin(
            model="m",
            model_label="M",
            candidate_id="c",
            api_messages=[{"role": "user", "content": "hello"}],
            annotations=[{"parts": [{"kind": "user_text", "label": "主人", "text": "hello"}]}],
            tools=None,
            params={},
        )
        rec.finish(call_id, status="ok", prompt_tokens=42)
    body = c.get(f"/api/conversations/{cid}/context-stats").json()
    assert body["latest_call_id"] == call_id
    assert sum(s["tokens"] for s in body["segments"]) == 42
    assert body["context"]["used_tokens"] == 42


def test_context_stats_fallback(client):
    c, _ = client
    cid = c.post("/api/conversations", json={"title": "old"}).json()["id"]
    body = c.get(f"/api/conversations/{cid}/context-stats").json()
    assert body["segments"] == []
    assert body["latest_call_id"] is None
