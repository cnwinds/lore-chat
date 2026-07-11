import pytest

from app.engine.agent.prompts import build_system_prompt
from app.engine.agent.system_layer import SystemLayer
from app.engine.retriever import Retriever
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def _repo(tmp_path):
    return KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))


def test_seeds_precepts_and_soul(tmp_path):
    repo = _repo(tmp_path)
    layer = SystemLayer(repo)
    assert "戒律" in repo.read_doc("系统/戒律.md").body
    assert "心法" in repo.read_doc("系统/心法.md").body
    # 出现在文档树中（可见），但归于系统目录
    assert "系统/戒律.md" in repo.list_tree()
    assert layer.prefix == "系统/"


def test_compose_includes_both_files(tmp_path):
    layer = SystemLayer(_repo(tmp_path))
    text = layer.compose()
    assert "心法" in text and "戒律" in text
    # 心法（处世哲学）在前，戒律在后
    assert text.index("心法") < text.index("戒律")


def test_compose_reflects_edits_via_mtime(tmp_path):
    repo = _repo(tmp_path)
    layer = SystemLayer(repo)
    repo.write_doc("系统/戒律.md", {"title": "戒律"}, "# 新规约\n只答英文。\n", commit_msg="edit")
    assert "只答英文" in layer.compose()


def test_build_system_prompt_injects_layer():
    prompt = build_system_prompt("default", "【系统控制层内容XYZ】")
    assert "【系统控制层内容XYZ】" in prompt
    assert prompt.index("【系统控制层内容XYZ】") < prompt.index("lorechat")


def test_retriever_excludes_system_prefix(tmp_path):
    llm = FakeLLMClient(embed_dim=8)
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm, excluded_prefixes=("系统/",))
    idx.reindex_doc("系统/戒律.md", "默认不落库，渐进式披露读取资料")
    idx.reindex_doc("技术/note.md", "默认不落库，渐进式披露读取资料")
    hits = retr.search("渐进式披露", k=5)
    sources = {h.source for h in hits}
    assert "系统/戒律.md" not in sources


def test_system_dir_protected_from_delete(tmp_path):
    repo = _repo(tmp_path)
    SystemLayer(repo)
    with pytest.raises(ValueError):
        repo.delete_path("系统/戒律.md", commit_msg="try delete")
    with pytest.raises(ValueError):
        repo.delete_path("系统/", commit_msg="try delete dir")
