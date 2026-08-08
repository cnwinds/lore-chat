"""记忆.md 文件投影已取消：相关写入须被拒绝。"""

from app.engine.memory.constants import MEMORY_DOC_REL
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def _service(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    return MemoryService(store, repo, knowledge_writer=make_writer(repo, tmp_path)), repo


def test_purge_removes_legacy_projection_file(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    repo.write_doc(
        MEMORY_DOC_REL,
        {"title": "记忆 · 关于用户", "source": "system"},
        "# 记忆 · 关于用户\n\n## 偏好与沟通方式\n\n- 旧投影\n",
        commit_msg="seed legacy",
    )
    assert repo.abs_path(MEMORY_DOC_REL).exists()
    _svc, _ = _service(tmp_path)
    assert not repo.abs_path(MEMORY_DOC_REL).exists()
    # 删除已纳入 git，工作区不应残留未提交的 D
    assert MEMORY_DOC_REL not in [i.path for i in repo.repo.index.diff(None)]
    assert MEMORY_DOC_REL not in repo.repo.untracked_files


def test_render_context_from_db_without_file(tmp_path):
    svc, repo = _service(tmp_path)
    svc.remember("记住我用 uv")
    ctx = svc.render_context()
    assert "uv" in ctx
    assert not repo.abs_path(MEMORY_DOC_REL).exists()


def test_is_memory_projection_path_normalizes_dots():
    from app.engine.memory.constants import is_memory_projection_path

    assert is_memory_projection_path("系统/记忆.md")
    assert is_memory_projection_path("/系统/./记忆.md")
    assert is_memory_projection_path("系统//记忆.md")
    assert not is_memory_projection_path("系统/戒律.md")


def test_persist_document_rejects_memory_projection(tmp_path):
    from app.engine.knowledge_writer import KnowledgeWriter

    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    writer = KnowledgeWriter(repo, indexer=None)
    try:
        writer.persist_document(
            MEMORY_DOC_REL,
            {"title": "x"},
            "# hi\n",
            commit_msg="should fail",
            changelog_line="should fail",
        )
        raise AssertionError("expected reject")
    except ValueError as e:
        assert "数据库" in str(e)


def test_ingest_and_summarize_reject_memory_projection_path(tmp_path):
    from app.engine.organizer import Organizer
    from app.engine.pending import PendingStore
    from app.engine.retriever import Retriever
    from app.index.fulltext import FullTextIndex
    from app.index.vector import VectorIndex
    from app.models.llm import FakeLLMClient

    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    llm = FakeLLMClient(chat_responses=[], embed_dim=8)
    org = Organizer(
        repo=repo,
        retriever=Retriever(VectorIndex(tmp_path / "vec"), FullTextIndex(tmp_path / "fts.db"), llm),
        pending=PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json"),
        llm=llm,
        knowledge_writer=make_writer(repo, tmp_path),
    )
    out = org.ingest_text("hello", forced_rel_path=MEMORY_DOC_REL)
    assert out.status == "rejected"
    assert "数据库" in out.message
    out2 = org.summarize_conversation(
        "用户: hi\n助手: ok",
        forced_rel_path=MEMORY_DOC_REL,
    )
    assert out2.status == "rejected"
    assert not repo.abs_path(MEMORY_DOC_REL).exists()
