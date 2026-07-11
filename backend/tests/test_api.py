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


def test_upload_and_download(client):
    content = "kubernetes 部署方案".encode("utf-8")
    files = {"file": ("plan.txt", content, "text/plain")}
    r = client.post("/api/upload", files=files, data={"category": "技术/docker"})
    assert r.status_code == 200
    path = r.json()["attachment"]
    assert path.endswith("attachments/plan.txt")
    r2 = client.get("/api/download", params={"path": path})
    assert r2.status_code == 200
    assert r2.content == content


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
