import json


def _patch_merge_llm(client, monkeypatch) -> None:
    llm = client.app.state.container.llm

    def fake_chat(messages, big=True):  # noqa: ARG001
        prompt = messages[-1]["content"]
        if "请将以下文档合并成一篇" in prompt:
            return "# 合并文档\n\n这是合并后的内容。\n"
        if "新内容：" in prompt and "相关文档：" in prompt:
            return json.dumps(
                {
                    "action": "new",
                    "rel_path": "技术/merged.md",
                    "title": "合并文档",
                    "category": "技术",
                    "tags": ["合并"],
                    "ambiguous": False,
                    "reason": "测试合并",
                },
                ensure_ascii=False,
            )
        return "合并摘要"

    monkeypatch.setattr(llm, "chat", fake_chat)


def _seed_docs(client) -> tuple[str, str]:
    repo = client.app.state.container.repo
    a = "技术/a.md"
    b = "技术/b.md"
    repo.write_doc(a, {"title": "A"}, "A 内容\n", commit_msg="seed a")
    repo.write_doc(b, {"title": "B"}, "B 内容\n", commit_msg="seed b")
    return a, b


def _create_merge(client, *, instruction: str = "保留重点"):
    a, b = _seed_docs(client)
    r = client.post(
        "/api/docs/merge",
        json={"paths": [a, b], "instruction": instruction, "title": "合并文档"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "saved"
    assert body["merge_id"]
    assert body["rel_path"]
    return body, a, b


def test_merge_api_create_and_get(client, monkeypatch):
    _patch_merge_llm(client, monkeypatch)
    created, _, _ = _create_merge(client)

    r = client.get(f"/api/docs/merge/{created['merge_id']}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session"]["id"] == created["merge_id"]
    assert data["session"]["status"] == "pending_review"
    assert data["session"]["new_path"] == created["rel_path"]
    assert data["user_modified"] is False


def test_merge_active_by_path(client, monkeypatch):
    _patch_merge_llm(client, monkeypatch)
    created, _, _ = _create_merge(client)

    r = client.get("/api/docs/merge/active", params={"path": created["rel_path"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["session"]["id"] == created["merge_id"]
    assert data["user_modified"] is False

    updated = client.put(
        "/api/doc",
        json={"path": created["rel_path"], "body": "# 合并文档\n\n用户手工改过。\n"},
    )
    assert updated.status_code == 200, updated.text
    r2 = client.get("/api/docs/merge/active", params={"path": created["rel_path"]})
    assert r2.status_code == 200, r2.text
    assert r2.json()["user_modified"] is True


def test_merge_reject_flow(client, monkeypatch):
    _patch_merge_llm(client, monkeypatch)
    created, _, _ = _create_merge(client)

    reject = client.post(f"/api/docs/merge/{created['merge_id']}/reject")
    assert reject.status_code == 200, reject.text
    payload = reject.json()
    assert payload["status"] == "rejected"
    assert payload["merge_id"] == created["merge_id"]

    doc = client.get("/api/doc", params={"path": created["rel_path"]})
    assert doc.status_code == 404


def test_merge_accept_and_resolve_sources(client, monkeypatch):
    _patch_merge_llm(client, monkeypatch)
    created, a, b = _create_merge(client)

    accept = client.post(f"/api/docs/merge/{created['merge_id']}/accept")
    assert accept.status_code == 200, accept.text
    accepted = accept.json()
    assert accepted["status"] == "saved"
    assert accepted["question_id"]

    resolve = client.post(
        f"/api/questions/{accepted['question_id']}/resolve",
        json={"choices": [a]},
    )
    assert resolve.status_code == 200, resolve.text
    resolved = resolve.json()
    assert resolved["status"] == "saved"
    assert "已删除源文档" in resolved["message"]

    deleted = client.get("/api/doc", params={"path": a})
    kept = client.get("/api/doc", params={"path": b})
    assert deleted.status_code == 404
    assert kept.status_code == 200
