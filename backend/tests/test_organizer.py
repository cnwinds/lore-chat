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


def test_ingest_ambiguous_creates_question(tmp_path):
    decision = json.dumps({"action": "merge", "rel_path": "技术/docker/常用命令.md",
                           "title": "常用命令", "category": "技术/docker",
                           "tags": ["docker"], "ambiguous": True, "reason": "可能与已有重叠"})
    org, repo, pending = _make(tmp_path, ["摘要", decision])
    result = org.ingest_text("docker logs 看日志")
    assert result.status == "question"
    assert result.question_id is not None
    assert len(pending.list_open()) == 1


def test_ingest_records_changelog(tmp_path):
    decision = json.dumps({"action": "new", "rel_path": "a.md", "title": "A",
                           "category": "", "tags": [], "ambiguous": False, "reason": "r"})
    org, repo, pending = _make(tmp_path, ["摘要", decision])
    org.ingest_text("内容")
    changelog = (repo.root / ".kb" / "changelog.md").read_text(encoding="utf-8")
    assert "a.md" in changelog


def test_resolve_pending_merge(tmp_path):
    decision = json.dumps({"action": "merge", "rel_path": "技术/docker/常用命令.md",
                           "title": "常用命令", "category": "技术/docker",
                           "tags": ["docker"], "ambiguous": True, "reason": "重叠"})
    org, repo, pending = _make(tmp_path, ["摘要", decision])
    # 先建一个已有文档以便 merge 追加
    repo.write_doc("技术/docker/常用命令.md", {"title": "常用命令"}, "docker ps\n", commit_msg="seed")
    result = org.ingest_text("docker logs 看日志")
    qid = result.question_id
    org.resolve_pending(qid, "merge")
    doc = repo.read_doc("技术/docker/常用命令.md")
    assert "docker logs" in doc.body
    assert pending.get(qid)["status"] == "resolved"
