import json
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
    result = org.ingest_text("windows终端怎么设置utf8编码")
    assert result.status == "rejected"
    assert result.rel_path is None
    assert repo.list_tree() == []


def test_ingest_new_doc(tmp_path):
    decision = json.dumps({"action": "new", "rel_path": "技术/docker/常用命令.md",
                           "title": "常用命令", "category": "技术/docker",
                           "tags": ["docker"], "ambiguous": False, "reason": "全新主题"})
    # chat 调用顺序：1)理解摘要 2)决策JSON
    org, repo, pending = _make(tmp_path, ["docker 命令摘要", decision])
    result = org.ingest_text("docker ps 用来查看容器")
    assert result.status == "saved"
    assert result.rel_path == "技术/docker/常用命令.md"
    doc = repo.read_doc("技术/docker/常用命令.md")
    assert "docker ps" in doc.body


def test_ingest_ambiguous_creates_question_when_no_related(tmp_path):
    decision = json.dumps({"action": "merge", "rel_path": "技术/docker/常用命令.md",
                           "title": "常用命令", "category": "技术/docker",
                           "tags": ["docker"], "ambiguous": True, "reason": "可能与已有重叠"})
    org, repo, pending = _make(tmp_path, ["摘要", decision])
    result = org.ingest_text("docker logs 看日志")
    assert result.status == "question"
    assert result.question_id is not None
    assert len(pending.list_open()) == 1


def test_ingest_auto_merges_when_related_exists(tmp_path):
    decision = json.dumps({"action": "merge", "rel_path": "技术/docker/常用命令.md",
                           "title": "常用命令", "category": "技术/docker",
                           "tags": ["docker"], "ambiguous": True, "reason": "同一主题"})
    merged_body = "docker ps\n\ndocker logs 看日志\n"
    org, repo, pending = _make(tmp_path, ["摘要", decision, merged_body])
    repo.write_doc("技术/docker/常用命令.md", {"title": "常用命令"}, "docker ps\n", commit_msg="seed")
    org.indexer.reindex_doc("技术/docker/常用命令.md", "docker ps\n")
    result = org.ingest_text("docker logs 看日志")
    assert result.status == "saved"
    assert result.rel_path == "技术/docker/常用命令.md"
    assert len(pending.list_open()) == 0
    doc = repo.read_doc("技术/docker/常用命令.md")
    assert "docker logs" in doc.body


def test_ingest_records_changelog(tmp_path):
    decision = json.dumps({"action": "new", "rel_path": "a.md", "title": "A",
                           "category": "", "tags": [], "ambiguous": False, "reason": "r"})
    org, repo, pending = _make(tmp_path, ["摘要", decision])
    org.ingest_text("内容")
    changelog = (repo.root / ".kb" / "changelog.md").read_text(encoding="utf-8")
    assert "a.md" in changelog


def test_resolve_agent_choices_returns_continue(tmp_path):
    decision = json.dumps(
        {
            "action": "new",
            "rel_path": "projects/lorechat/start.md",
            "title": "lorechat 启动",
            "category": "projects/lorechat",
            "tags": ["lorechat"],
            "ambiguous": False,
            "reason": "项目记录",
        }
    )
    org, repo, pending = _make(tmp_path, ["摘要", decision])
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


def test_resolve_pending_merge(tmp_path):
    decision = json.dumps({"action": "merge", "rel_path": "技术/docker/常用命令.md",
                           "title": "常用命令", "category": "技术/docker",
                           "tags": ["docker"], "ambiguous": True, "reason": "重叠"})
    merged_body = "docker ps\n\ndocker logs\n"
    org, repo, pending = _make(tmp_path, ["摘要", decision, merged_body])
    # 先建一个已有文档以便 merge 整理
    repo.write_doc("技术/docker/常用命令.md", {"title": "常用命令"}, "docker ps\n", commit_msg="seed")
    result = org.ingest_text("docker logs 看日志")
    qid = result.question_id
    org.resolve_pending(qid, "merge")
    doc = repo.read_doc("技术/docker/常用命令.md")
    assert "docker logs" in doc.body
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


def test_ingest_hint_path_merges_into_active_doc(tmp_path):
    decision = json.dumps(
        {
            "action": "new",
            "rel_path": "projects/mini-app/version-todo.md",
            "title": "小程序版本",
            "category": "projects",
            "tags": ["待办"],
            "ambiguous": False,
            "reason": "新待办",
        }
    )
    merged_body = "# 待办\n\n- 小程序版本\n"
    org, repo, pending = _make(tmp_path, ["摘要", decision, merged_body])
    repo.write_doc(
        "projects/anti-cheat/todo.md",
        {"title": "反外挂待办"},
        "# 反外挂待办\n\n1. 已有项\n",
        commit_msg="seed",
    )
    result = org.ingest_text(
        "增加待办：小程序版本",
        hint_path="projects/anti-cheat/todo.md",
    )
    assert result.status == "saved"
    assert result.rel_path == "projects/anti-cheat/todo.md"
    doc = repo.read_doc("projects/anti-cheat/todo.md")
    assert "小程序版本" in doc.body
