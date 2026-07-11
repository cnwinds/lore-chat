import json

from app.engine.merge_sessions import MergeSessionStore
from app.engine.organizer import MergeResult
from app.engine.content_hash import body_hash
from tests.test_organizer import _make


def test_merge_documents_creates_new_file(tmp_path):
    decision = json.dumps(
        {
            "action": "merge",
            "rel_path": "技术/错误路径.md",
            "title": "错误标题",
            "category": "技术",
            "tags": ["合并"],
            "ambiguous": False,
            "reason": "测试决策",
        }
    )
    merged_body = "# 合并文档\n\n来自 A 和 B。\n"
    org, repo, _ = _make(tmp_path, [merged_body, "摘要", decision])
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")
    repo.write_doc("技术/a.md", {"title": "A"}, "A 内容\n", commit_msg="seed a")
    repo.write_doc("技术/b.md", {"title": "B"}, "B 内容\n", commit_msg="seed b")

    result = org.merge_documents(
        ["技术/a.md", "技术/b.md"],
        instruction="保留核心结论",
        merge_sessions=sessions,
        title_hint="合并标题",
    )

    assert isinstance(result, MergeResult)
    assert result.status == "saved"
    assert result.rel_path is not None
    assert result.merge_id is not None
    doc = repo.read_doc(result.rel_path)
    assert "来自 A 和 B" in doc.body
    assert doc.meta.get("source") == "merge"
    assert doc.meta.get("merged_from") == ["技术/a.md", "技术/b.md"]

    session = sessions.get(result.merge_id)
    assert session["status"] == "pending_review"
    assert session["new_path"] == result.rel_path
    assert session["source_paths"] == ["技术/a.md", "技术/b.md"]
    assert session["generated_content_hash"] == body_hash(doc.body)


def test_merge_rejects_system_paths(tmp_path):
    org, repo, _ = _make(tmp_path, [])
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")
    repo.write_doc("技术/a.md", {"title": "A"}, "A 内容\n", commit_msg="seed a")
    repo.write_doc(".kb/system.md", {"title": "S"}, "系统内容\n", commit_msg="seed system")

    result = org.merge_documents(
        ["技术/a.md", ".kb/system.md"],
        merge_sessions=sessions,
    )

    assert result.status == "rejected"
    assert result.rel_path is None
    assert result.merge_id is None


def test_merge_rejects_less_than_two(tmp_path):
    org, repo, _ = _make(tmp_path, [])
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")
    repo.write_doc("技术/a.md", {"title": "A"}, "A 内容\n", commit_msg="seed a")

    result = org.merge_documents(["技术/a.md"], merge_sessions=sessions)

    assert result.status == "rejected"
    assert result.rel_path is None
    assert result.merge_id is None


def test_merge_regenerate_overwrites_same_path(tmp_path):
    decision = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/merged.md",
            "title": "合并文档",
            "category": "技术",
            "tags": ["合并"],
            "ambiguous": False,
            "reason": "首次合并",
        }
    )
    decision_regen = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/other.md",
            "title": "不应生效",
            "category": "技术",
            "tags": ["合并"],
            "ambiguous": False,
            "reason": "应被 target_path 覆盖",
        }
    )
    org, repo, _ = _make(
        tmp_path,
        [
            "# 初版\n\n内容 A\n",
            "摘要1",
            decision,
            "# 再生成\n\n内容 B\n",
            "摘要2",
            decision_regen,
        ],
    )
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")
    repo.write_doc("技术/a.md", {"title": "A"}, "A 内容\n", commit_msg="seed a")
    repo.write_doc("技术/b.md", {"title": "B"}, "B 内容\n", commit_msg="seed b")

    first = org.merge_documents(
        ["技术/a.md", "技术/b.md"],
        instruction="第一次",
        merge_sessions=sessions,
    )
    assert first.status == "saved"
    assert first.merge_id is not None
    original_path = first.rel_path

    regen = org.regenerate_merge(first.merge_id, merge_sessions=sessions)

    assert regen.status == "saved"
    assert regen.merge_id == first.merge_id
    assert regen.rel_path == original_path
    assert "内容 B" in repo.read_doc(original_path).body


def test_merge_reject_deletes_new_doc(tmp_path):
    decision = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/merged.md",
            "title": "合并文档",
            "category": "技术",
            "tags": ["合并"],
            "ambiguous": False,
            "reason": "测试拒绝",
        }
    )
    org, repo, _ = _make(tmp_path, ["# 合并文档\n", "摘要", decision])
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")
    repo.write_doc("技术/a.md", {"title": "A"}, "A 内容\n", commit_msg="seed a")
    repo.write_doc("技术/b.md", {"title": "B"}, "B 内容\n", commit_msg="seed b")
    merged = org.merge_documents(["技术/a.md", "技术/b.md"], merge_sessions=sessions)
    assert merged.merge_id is not None
    assert merged.rel_path is not None

    result = org.reject_merge(merged.merge_id, merge_sessions=sessions)

    assert result.status == "rejected"
    assert result.rel_path == merged.rel_path
    with __import__("pytest").raises(FileNotFoundError):
        repo.read_doc(merged.rel_path)
    assert sessions.get(merged.merge_id)["status"] == "rejected"


def test_merge_accept_creates_source_question(tmp_path):
    decision = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/merged.md",
            "title": "合并文档",
            "category": "技术",
            "tags": ["合并"],
            "ambiguous": False,
            "reason": "测试接受",
        }
    )
    org, repo, pending = _make(tmp_path, ["# 合并文档\n", "摘要", decision])
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")
    repo.write_doc("技术/a.md", {"title": "A"}, "A 内容\n", commit_msg="seed a")
    repo.write_doc("技术/b.md", {"title": "B"}, "B 内容\n", commit_msg="seed b")
    merged = org.merge_documents(["技术/a.md", "技术/b.md"], merge_sessions=sessions)
    assert merged.merge_id is not None
    assert merged.rel_path is not None

    result = org.accept_merge(merged.merge_id, merge_sessions=sessions)

    assert result.status == "saved"
    assert result.question_id is not None
    assert sessions.get(merged.merge_id)["status"] == "accepted"
    q = pending.get(result.question_id)
    assert q["multi_select"] is True
    assert q["payload"]["kind"] == "merge_sources"
    assert q["payload"]["merge_id"] == merged.merge_id
    assert q["payload"]["new_path"] == merged.rel_path
    assert q["payload"]["source_paths"] == ["技术/a.md", "技术/b.md"]
    assert "是否删除以下源文档" in q["question"]
    assert q["options"] == [
        {"id": "技术/a.md", "label": "技术/a.md"},
        {"id": "技术/b.md", "label": "技术/b.md"},
    ]


def test_resolve_merge_sources_deletes_selected(tmp_path):
    decision = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/merged.md",
            "title": "合并文档",
            "category": "技术",
            "tags": ["合并"],
            "ambiguous": False,
            "reason": "测试删除源文档",
        }
    )
    org, repo, _ = _make(tmp_path, ["# 合并文档\n", "摘要", decision])
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")
    repo.write_doc("技术/a.md", {"title": "A"}, "A 内容\n", commit_msg="seed a")
    repo.write_doc("技术/b.md", {"title": "B"}, "B 内容\n", commit_msg="seed b")
    merged = org.merge_documents(["技术/a.md", "技术/b.md"], merge_sessions=sessions)
    assert merged.merge_id is not None

    result = org.resolve_merge_sources(
        merged.merge_id,
        ["技术/a.md"],
        merge_sessions=sessions,
    )

    assert result.status == "saved"
    with __import__("pytest").raises(FileNotFoundError):
        repo.read_doc("技术/a.md")
    assert repo.read_doc("技术/b.md").body
    assert "已删除源文档" in result.message
    assert "技术/a.md" in result.message


def test_merge_regenerate_overwrites_same_path(tmp_path):
    decision = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/merged.md",
            "title": "合并文档",
            "category": "技术",
            "tags": ["合并"],
            "ambiguous": False,
            "reason": "首次合并",
        }
    )
    decision_regen = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/other.md",
            "title": "不应生效",
            "category": "技术",
            "tags": ["合并"],
            "ambiguous": False,
            "reason": "应被 target_path 覆盖",
        }
    )
    org, repo, _ = _make(
        tmp_path,
        [
            "# 初版\n\n内容 A\n",
            "摘要1",
            decision,
            "# 再生成\n\n内容 B\n",
            "摘要2",
            decision_regen,
        ],
    )
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")
    repo.write_doc("技术/a.md", {"title": "A"}, "A 内容\n", commit_msg="seed a")
    repo.write_doc("技术/b.md", {"title": "B"}, "B 内容\n", commit_msg="seed b")

    first = org.merge_documents(
        ["技术/a.md", "技术/b.md"],
        instruction="第一次",
        merge_sessions=sessions,
    )
    assert first.status == "saved"
    assert first.merge_id is not None
    original_path = first.rel_path

    regen = org.regenerate_merge(first.merge_id, merge_sessions=sessions)

    assert regen.status == "saved"
    assert regen.merge_id == first.merge_id
    assert regen.rel_path == original_path
    assert "内容 B" in repo.read_doc(original_path).body


def test_merge_reject_deletes_new_doc(tmp_path):
    decision = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/merged.md",
            "title": "合并文档",
            "category": "技术",
            "tags": ["合并"],
            "ambiguous": False,
            "reason": "测试拒绝",
        }
    )
    org, repo, _ = _make(tmp_path, ["# 合并文档\n", "摘要", decision])
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")
    repo.write_doc("技术/a.md", {"title": "A"}, "A 内容\n", commit_msg="seed a")
    repo.write_doc("技术/b.md", {"title": "B"}, "B 内容\n", commit_msg="seed b")
    merged = org.merge_documents(["技术/a.md", "技术/b.md"], merge_sessions=sessions)
    assert merged.merge_id is not None
    assert merged.rel_path is not None

    result = org.reject_merge(merged.merge_id, merge_sessions=sessions)

    assert result.status == "rejected"
    assert result.rel_path == merged.rel_path
    with __import__("pytest").raises(FileNotFoundError):
        repo.read_doc(merged.rel_path)
    assert sessions.get(merged.merge_id)["status"] == "rejected"


def test_merge_accept_creates_source_question(tmp_path):
    decision = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/merged.md",
            "title": "合并文档",
            "category": "技术",
            "tags": ["合并"],
            "ambiguous": False,
            "reason": "测试接受",
        }
    )
    org, repo, pending = _make(tmp_path, ["# 合并文档\n", "摘要", decision])
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")
    repo.write_doc("技术/a.md", {"title": "A"}, "A 内容\n", commit_msg="seed a")
    repo.write_doc("技术/b.md", {"title": "B"}, "B 内容\n", commit_msg="seed b")
    merged = org.merge_documents(["技术/a.md", "技术/b.md"], merge_sessions=sessions)
    assert merged.merge_id is not None
    assert merged.rel_path is not None

    result = org.accept_merge(merged.merge_id, merge_sessions=sessions)

    assert result.status == "saved"
    assert result.question_id is not None
    assert sessions.get(merged.merge_id)["status"] == "accepted"
    q = pending.get(result.question_id)
    assert q["multi_select"] is True
    assert q["payload"]["kind"] == "merge_sources"
    assert q["payload"]["merge_id"] == merged.merge_id
    assert q["payload"]["new_path"] == merged.rel_path
    assert q["payload"]["source_paths"] == ["技术/a.md", "技术/b.md"]
    assert "是否删除以下源文档" in q["question"]
    assert q["options"] == [
        {"id": "技术/a.md", "label": "技术/a.md"},
        {"id": "技术/b.md", "label": "技术/b.md"},
    ]


def test_resolve_merge_sources_deletes_selected(tmp_path):
    decision = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/merged.md",
            "title": "合并文档",
            "category": "技术",
            "tags": ["合并"],
            "ambiguous": False,
            "reason": "测试删除源文档",
        }
    )
    org, repo, _ = _make(tmp_path, ["# 合并文档\n", "摘要", decision])
    sessions = MergeSessionStore(tmp_path / "knowledge" / ".kb" / "merge_sessions.json")
    repo.write_doc("技术/a.md", {"title": "A"}, "A 内容\n", commit_msg="seed a")
    repo.write_doc("技术/b.md", {"title": "B"}, "B 内容\n", commit_msg="seed b")
    merged = org.merge_documents(["技术/a.md", "技术/b.md"], merge_sessions=sessions)
    assert merged.merge_id is not None

    result = org.resolve_merge_sources(
        merged.merge_id,
        ["技术/a.md"],
        merge_sessions=sessions,
    )

    assert result.status == "saved"
    with __import__("pytest").raises(FileNotFoundError):
        repo.read_doc("技术/a.md")
    assert repo.read_doc("技术/b.md").body
    assert "已删除源文档" in result.message
    assert "技术/a.md" in result.message
