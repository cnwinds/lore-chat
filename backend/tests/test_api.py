"""HTTP API 集成测试。

灌库与只读问答优先使用同步机器 API（/api/ingest、/api/ask），
结果确定、无需解析 SSE。产品行为测 /api/chat。见
docs/superpowers/specs/2026-07-12-ingest-ask-api-design.md
"""
import json


def _parse_sse_events(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_type = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_type and data is not None:
            events.append((event_type, data))
    return events


def _assert_sse_events_have_ts(events: list[tuple[str, dict]]) -> None:
    for event_type, data in events:
        assert "ts" in data, f"event {event_type} missing ts"


def test_ingest_rejects_question(client):
    r = client.post("/api/ingest", json={"text": "windows终端怎么设置utf8编码"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["rel_path"] is None


def test_ingest_then_ask(client):
    r = client.post("/api/ingest", json={"text": "docker ps 查看容器"})
    assert r.status_code == 200
    assert r.json()["status"] == "saved"

    r2 = client.post("/api/ask", json={"query": "docker"})
    assert r2.status_code == 200
    body = r2.json()
    assert "sources" in body and "text" in body


def test_chat_returns_sse_stream(client):
    r = client.post("/api/chat", json={"text": "docker 怎么用"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    events = _parse_sse_events(r.text)
    event_types = [t for t, _ in events]
    assert "done" in event_types
    _assert_sse_events_have_ts(events)
    done_data = next(data for t, data in events if t == "done")
    assert "total_duration_ms" in done_data
    assert isinstance(done_data["total_duration_ms"], int)


def test_chat_accepts_web_enabled_flag(client):
    r = client.post("/api/chat", json={"text": "hello", "web_enabled": False})
    assert r.status_code == 200
    r2 = client.post("/api/chat", json={"text": "hello", "web_enabled": True})
    assert r2.status_code == 200


def test_chat_rejects_primary_not_in_active_paths(client):
    r = client.post(
        "/api/chat",
        json={
            "text": "hi",
            "active_doc_paths": ["a.md"],
            "primary_doc_path": "b.md",
        },
    )
    assert r.status_code == 400


def test_chat_accepts_multi_doc_context(client):
    r = client.post(
        "/api/chat",
        json={
            "text": "合并",
            "active_doc_paths": ["a.md", "b.md"],
            "primary_doc_path": "a.md",
            "web_enabled": False,
        },
    )
    assert r.status_code == 200


def test_chat_recall_via_sse(client):
    client.post("/api/ingest", json={"text": "docker ps 查看容器列表"})
    r = client.post("/api/chat", json={"text": "docker 怎么用"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    events = _parse_sse_events(r.text)
    event_types = [t for t, _ in events]
    assert "text_delta" in event_types
    assert "done" in event_types
    _assert_sse_events_have_ts(events)
    tool_results = [data for t, data in events if t == "tool_result"]
    assert tool_results, "expected tool_result events during recall"
    for data in tool_results:
        assert "duration_ms" in data
        assert isinstance(data["duration_ms"], int)


def test_tree_lists_docs(client):
    client.post("/api/ingest", json={"text": "内容一"})
    r = client.get("/api/tree")
    assert r.status_code == 200
    assert any(p.endswith(".md") for p in r.json()["docs"])


def test_discover_skills_nested(client):
    files = {"file": ("SKILL.md", b"# skill\n", "text/markdown")}
    r = client.post(
        "/api/kb/import",
        files=files,
        data={"directory": "skill/职业规划/张雪峰"},
    )
    assert r.status_code == 200
    r2 = client.get("/api/kb/discover-skills", params={"from_dir": "skill"})
    assert r2.status_code == 200
    assert "skill/职业规划/张雪峰" in r2.json()["roots"]


def test_chat_rejects_skill_as_primary(client):
    r = client.post(
        "/api/chat",
        json={
            "text": "hi",
            "doc_context": [
                {"path": "skill/pkg", "kind": "skill_root"},
                {"path": "a.md", "kind": "document"},
            ],
            "primary_doc_path": "skill/pkg",
        },
    )
    assert r.status_code == 400


def test_chat_rejects_invalid_doc_context_kind(client):
    r = client.post(
        "/api/chat",
        json={
            "text": "hi",
            "doc_context": [{"path": "x.md", "kind": "not_a_kind"}],
        },
    )
    assert r.status_code == 422


def test_chat_rejects_missing_skill_root(client):
    r = client.post(
        "/api/chat",
        json={
            "text": "hi",
            "doc_context": [{"path": "no/such/skill", "kind": "skill_root"}],
        },
    )
    assert r.status_code == 400
    assert "SKILL.md" in r.json()["detail"]


def test_upload_and_download(client):
    content = "kubernetes 部署方案".encode("utf-8")
    files = {"file": ("plan.txt", content, "text/plain")}
    r = client.post(
        "/api/kb/import",
        files=files,
        data={"directory": "技术/docker"},
    )
    assert r.status_code == 200
    path = r.json()["rel_path"]
    assert path == "技术/docker/plan.txt"
    assert path in client.get("/api/tree").json()["docs"]
    r2 = client.get("/api/download", params={"path": path})
    assert r2.status_code == 200
    assert r2.content == content


def test_download_zip_directory(client):
    files = {"file": ("note.md", b"# a\n", "text/markdown")}
    r = client.post("/api/kb/import", files=files, data={"directory": "导出目录"})
    assert r.status_code == 200
    r2 = client.get("/api/download-zip", params={"path": "导出目录"})
    assert r2.status_code == 200
    assert "zip" in r2.headers.get("content-type", "")
    import zipfile
    from io import BytesIO

    with zipfile.ZipFile(BytesIO(r2.content)) as z:
        assert "导出目录/note.md" in z.namelist()


def test_kb_import_conflict(client):
    files = {"file": ("note.md", b"# a\n", "text/markdown")}
    r = client.post("/api/kb/import", files=files, data={"directory": "导入测试"})
    assert r.status_code == 200
    r2 = client.post("/api/kb/import", files=files, data={"directory": "导入测试"})
    assert r2.status_code == 409
    detail = r2.json()["detail"]
    assert detail["code"] == "PATH_EXISTS"
    assert "suggested_filename" in detail


def test_doc_endpoint(client):
    client.post("/api/ingest", json={"text": "内容 X"})
    tree = client.get("/api/tree").json()["docs"]
    r = client.get("/api/doc", params={"path": tree[0]})
    assert r.status_code == 200
    assert "body" in r.json()


def test_put_doc_updates_body(client):
    client.post("/api/ingest", json={"text": "原始内容"})
    path = client.get("/api/tree").json()["docs"][0]
    new_body = "更新后的正文\n"
    r = client.put("/api/doc", json={"path": path, "body": new_body})
    assert r.status_code == 200
    data = r.json()
    assert data["rel_path"] == path
    assert data["body"] == new_body
    assert "meta" in data

    r2 = client.get("/api/doc", params={"path": path})
    assert r2.status_code == 200
    assert r2.json()["body"] == new_body


def test_put_doc_not_found(client):
    r = client.put("/api/doc", json={"path": "不存在/文档.md", "body": "x"})
    assert r.status_code == 404


def test_put_doc_protected(client):
    r = client.put(
        "/api/doc",
        json={"path": "系统/戒律.md", "body": "用户修订\n"},
    )
    assert r.status_code == 200
    assert r.json()["body"] == "用户修订\n"

    r2 = client.put(
        "/api/doc",
        json={"path": ".kb/foo.md", "body": "篡改"},
    )
    assert r2.status_code == 403


def test_conversations_crud(client):
    r = client.post("/api/conversations")
    assert r.status_code == 200
    cid = r.json()["id"]

    r2 = client.get("/api/conversations")
    assert r2.status_code == 200
    assert any(c["id"] == cid for c in r2.json()["conversations"])

    r3 = client.get(f"/api/conversations/{cid}")
    assert r3.status_code == 200
    assert r3.json()["messages"] == []

    r4 = client.delete(f"/api/conversations/{cid}")
    assert r4.status_code == 200
    assert client.get(f"/api/conversations/{cid}").status_code == 404


def test_delete_conversation_clears_fts_and_vector_indexes(client):
    container = client.app.state.container
    store = container.conversations
    fts = container.conversation_fts
    vec = container.conversation_vector
    llm = container.llm

    cid = store.create()
    turn = store.begin_turn(
        cid,
        user_text="人脑结构测试",
        client_message_id="del-index-1",
        observation_allowed=False,
    )
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "关于人脑结构的回答",
            "timeline": [{"type": "text", "content": "关于人脑结构的回答"}],
            "sources": [],
            "status": "complete",
        },
    )
    assert container.derivation_worker.drain(max_jobs=10) >= 2
    assert fts.query("人脑", k=5)
    assert vec.query(llm.embed(["人脑"])[0], k=5)

    r = client.delete(f"/api/conversations/{cid}")
    assert r.status_code == 200

    assert fts.query("人脑", k=5) == []
    assert vec.query(llm.embed(["人脑"])[0], k=5) == []


def test_chat_saves_to_conversation(client):
    r = client.post("/api/conversations")
    cid = r.json()["id"]

    client.post("/api/ingest", json={"text": "docker ps 查看容器列表"})
    r2 = client.post(
        "/api/chat",
        json={"text": "docker 怎么用", "conversation_id": cid},
    )
    assert r2.status_code == 200

    conv = client.get(f"/api/conversations/{cid}").json()
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["role"] == "user"
    assert conv["messages"][0]["text"] == "docker 怎么用"
    assert "ts" in conv["messages"][0]
    assert conv["messages"][1]["role"] == "assistant"
    assert "timeline" in conv["messages"][1]
    assert "ts" in conv["messages"][1]
    timeline = conv["messages"][1]["timeline"]
    assert timeline, "assistant message should persist non-empty timeline"
    assert any(b.get("type") == "tool" for b in timeline)
    for block in timeline:
        assert "ts" in block
    tool_blocks = [b for b in timeline if b.get("type") == "tool" and b.get("status") == "done"]
    assert tool_blocks
    assert all("duration_ms" in b for b in tool_blocks)
    assert conv["title"] == "docker 怎么用"


def test_resolve_legacy_agent_multi_select(client, tmp_path):
    """旧版 ask_user 待确认项（空 payload、无 kind）应支持多选 resolve。"""
    pending_path = tmp_path / "knowledge" / ".kb" / "pending.json"
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    qid = "legacy123abc"
    pending_path.write_text(
        json.dumps(
            {
                qid: {
                    "id": qid,
                    "question": "以下哪些想记录？（可多选，我来整理）",
                    "options": [
                        {"id": "basic", "label": "基本信息"},
                        {"id": "today", "label": "今日进展"},
                    ],
                    "payload": {},
                    "status": "open",
                    "choice": None,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    r = client.post(f"/api/questions/{qid}/resolve", json={"choices": ["basic", "today"]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "saved"
    open_ids = {q["id"] for q in client.get("/api/questions").json()["questions"]}
    assert qid not in open_ids


def test_resolve_legacy_agent_single_choice(client, tmp_path):
    """多选征询只选一项时，用 choice 字段也应能 resolve。"""
    pending_path = tmp_path / "knowledge" / ".kb" / "pending.json"
    pending_path.parent.mkdir(parents=True, exist_ok=True)
    qid = "legacy456def"
    pending_path.write_text(
        json.dumps(
            {
                qid: {
                    "id": qid,
                    "question": "以下哪些想记录？（可多选，我来整理）",
                    "options": [{"id": "basic", "label": "基本信息"}],
                    "payload": {},
                    "status": "open",
                    "choice": None,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    r = client.post(f"/api/questions/{qid}/resolve", json={"choice": "basic"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "saved"
