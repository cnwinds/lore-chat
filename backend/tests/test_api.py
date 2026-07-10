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
    assert "event: done" in r.text
    assert '"ts"' in r.text


def test_chat_recall_via_sse(client):
    client.post("/api/ingest", json={"text": "docker ps 查看容器列表"})
    r = client.post("/api/chat", json={"text": "docker 怎么用"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    assert "event: text_delta" in r.text
    assert "event: done" in r.text


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
    assert conv["messages"][1]["role"] == "assistant"
    assert "timeline" in conv["messages"][1]
    assert conv["title"] == "docker 怎么用"
