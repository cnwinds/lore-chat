def test_ingest_then_ask(client):
    r = client.post("/api/ingest", json={"text": "docker ps 查看容器"})
    assert r.status_code == 200
    assert r.json()["status"] == "saved"

    r2 = client.post("/api/ask", json={"query": "docker"})
    assert r2.status_code == 200
    body = r2.json()
    assert "sources" in body and "text" in body


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
