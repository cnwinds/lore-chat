"""Phase 2 gap fixes: clear_tombstone, import tombstone, sensitive recall, doc sync order."""

from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.memory.normalize import value_hash, normalize_slot_key
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def _service(tmp_path, repo=None):
    repo = repo or KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    return MemoryService(store, repo, knowledge_writer=make_writer(repo, tmp_path))


def test_clear_tombstone_allows_remember_after_forget(tmp_path):
    svc = _service(tmp_path)
    f = svc.remember("记住我喜欢简洁回答")["fact"]
    svc.forget(fact_id=f["id"])
    blocked = svc.remember("记住我喜欢简洁回答")
    assert blocked["ok"] is False
    assert blocked["error"] == "tombstoned"
    cleared = svc.remember(
        "记住我喜欢简洁回答",
        origin="explicit_remember",
        clear_tombstone=True,
    )
    assert cleared["ok"] is True
    assert svc.store.list_confirmed()


def test_import_manual_upsert_blocked_by_tombstone(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    svc = _service(tmp_path, repo)
    f = svc.remember("记住我用 uv")["fact"]
    svc.forget(fact_id=f["id"])
    svc.render_to_file()
    doc = repo.read_doc("系统/记忆.md")
    new_body = doc.body + "\n- 记住我用 uv\n"
    out = svc.import_manual_document(doc.meta, new_body)
    assert out["ok"] is False
    assert out["error"] == "tombstoned"
    assert svc.store.list_confirmed() == []


def test_sensitive_fact_omits_quote_in_recall_sources(tmp_path):
    svc = _service(tmp_path)
    stmt = "我住在北京市朝阳区某某路100号"
    out = svc.remember(stmt, origin="explicit_remember")
    assert out["ok"] is True
    assert out["fact"]["sensitivity"] == "sensitive"
    cid = "c1"
    mid = "m1"
    svc.store.add_evidence(
        fact_id=out["fact"]["id"],
        conversation_id=cid,
        message_id=mid,
        start_char=0,
        end_char=len(stmt),
        quote_hash="dummy",
    )
    recalled = svc.recall("朝阳", include_sources=True)
    sources = recalled["facts"][0]["sources"]
    assert sources
    assert sources[0]["quote"] is None


def test_import_manual_dry_run_validates_without_persisting(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    svc = _service(tmp_path, repo)
    svc.render_to_file()
    doc = repo.read_doc("系统/记忆.md")
    invalid = doc.body + "\n```code block```\n"
    out = svc.import_manual_document(doc.meta, invalid, dry_run=True)
    assert out["ok"] is False
    before = repo.read_doc("系统/记忆.md").body
    assert before == doc.body


def test_validate_manual_import_checks_tombstone(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    svc = _service(tmp_path, repo)
    f = svc.remember("记住我用 uv")["fact"]
    svc.forget(fact_id=f["id"])
    svc.render_to_file()
    doc = repo.read_doc("系统/记忆.md")
    new_body = doc.body + "\n- 记住我用 uv\n"
    out = svc.import_manual_document(doc.meta, new_body, dry_run=True)
    assert out["ok"] is False
    assert out["error"] == "tombstoned"
