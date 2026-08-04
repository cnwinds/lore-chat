from app.engine.organizer import Organizer
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.storage.repo import KnowledgeRepo
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.models.llm import FakeLLMClient


def _make(tmp_path, chat_responses):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(chat_responses=chat_responses, embed_dim=8)
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm)
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
    org = Organizer(repo=repo, retriever=retr, indexer=idx, pending=pending, llm=llm)
    return org, repo, pending


def test_ingest_rejects_question_only(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    result = org.ingest_text(
        "windows终端怎么设置utf8编码",
        forced_rel_path="技术/终端/编码.md",
    )
    assert result.status == "rejected"
    assert result.rel_path is None
    assert repo.list_tree() == []


def test_ingest_rejects_missing_path(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    result = org.ingest_text("可写入的内容", forced_rel_path="")
    assert result.status == "rejected"
    assert repo.list_tree() == []


def test_ingest_new_doc(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    result = org.ingest_text(
        "docker ps 用来查看容器",
        forced_rel_path="技术/docker/常用命令.md",
    )
    assert result.status == "saved"
    assert result.rel_path == "技术/docker/常用命令.md"
    doc = repo.read_doc("技术/docker/常用命令.md")
    assert "docker ps" in doc.body


def test_ingest_merge_into_existing(tmp_path):
    merged_body = "docker ps\n\ndocker logs 看日志\n"
    org, repo, pending = _make(tmp_path, [merged_body])
    repo.write_doc("技术/docker/常用命令.md", {"title": "常用命令"}, "docker ps\n", commit_msg="seed")
    org.indexer.reindex_doc("技术/docker/常用命令.md", "docker ps\n")
    result = org.ingest_text(
        "docker logs 看日志",
        forced_rel_path="技术/docker/常用命令.md",
    )
    assert result.status == "saved"
    assert result.rel_path == "技术/docker/常用命令.md"
    doc = repo.read_doc("技术/docker/常用命令.md")
    assert "docker logs" in doc.body


def test_ingest_records_changelog(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    org.ingest_text("内容", forced_rel_path="笔记/a.md")
    changelog = (repo.root / ".kb" / "changelog.md").read_text(encoding="utf-8")
    assert "笔记/a.md" in changelog


def test_resolve_agent_choices_returns_continue(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    qid = pending.create(
        "选哪些内容？",
        [
            {"id": "basic", "label": "基本信息"},
            {"id": "progress", "label": "今日进展"},
        ],
        {"kind": "agent", "context": "lorechat 项目启动"},
        multi_select=True,
    )
    result = org.resolve_agent_choices(
        qid, ["basic", "progress"], conversation_context="用户：开始开发 lorechat"
    )
    assert result.status == "continue"
    assert result.continue_prompt
    assert "基本信息" in result.continue_prompt
    assert "开始开发 lorechat" in result.continue_prompt
    assert pending.get(qid)["status"] == "resolved"


def test_resolve_agent_done_after_write_acknowledges_path(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    qid = pending.create(
        "能补充一些细节吗？",
        [{"id": "done", "label": "就这样，够了"}],
        {
            "kind": "agent",
            "context": "已创建待办：小程序版本，保存在 projects/mini-app/version-todo.md",
        },
    )
    result = org.resolve_agent_choices(qid, ["done"])
    assert result.status == "saved"
    assert result.rel_path == "projects/mini-app/version-todo.md"
    assert "已记录到" in result.message


def test_resolve_agent_done_without_write_says_confirmed(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    qid = pending.create(
        "已足够，不需要改动？",
        [{"id": "done", "label": "已足够，不需要改动"}],
        {"kind": "agent", "context": "已有文档路径：projects/lorechat/start.md"},
    )
    result = org.resolve_agent_choices(qid, ["done"])
    assert result.status == "acknowledged"
    assert result.message == "好的，已确认。"


def test_ingest_forced_path_creates_new_file(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    result = org.ingest_text(
        "全新内容段落",
        forced_rel_path="技术/llm/指定路径.md",
    )
    assert result.status == "saved"
    assert result.rel_path == "技术/llm/指定路径.md"
    doc = repo.read_doc("技术/llm/指定路径.md")
    assert "全新内容段落" in doc.body


def test_legacy_pending_resolves_to_continue_with_write_kb_hint(tmp_path):
    org, repo, pending = _make(tmp_path, [])
    qid = pending.create(
        "记录哪部分？",
        [{"id": "a", "label": "要点 A"}],
        {"context": "背景说明"},
    )
    result = org.resolve_agent_choices(qid, ["a"])
    assert result.status == "continue"
    assert "list_kb_structure" in result.continue_prompt
    assert "write_kb" in result.continue_prompt
