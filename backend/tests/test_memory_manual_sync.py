from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.storage.repo import KnowledgeRepo


from tests.helpers import make_writer


def _service(tmp_path, repo=None):
    repo = repo or KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    return MemoryService(store, repo, knowledge_writer=make_writer(repo, tmp_path))


def test_import_detects_deleted_marker_as_forgotten(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    svc = _service(tmp_path, repo)
    f = svc.remember("记住我用 uv")["fact"]
    svc.render_to_file()
    doc = repo.read_doc("系统/记忆.md")
    marker = f"<!-- memory:{f['id']} -->"
    new_body = doc.body.replace(f"- 记住我用 uv\n{marker}", "")
    out = svc.import_manual_document(doc.meta, new_body)
    assert out["ok"] is True
    assert svc.store.get_fact(f["id"])["status"] == "forgotten"
    assert svc.store.has_tombstone(
        slot_key=f["slot_key"], normalized_value_hash=f["normalized_value_hash"]
    )


def test_import_new_bullet_without_id_becomes_manual(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    svc = _service(tmp_path, repo)
    svc.render_to_file()
    doc = repo.read_doc("系统/记忆.md")
    new_body = doc.body + "\n- 新增强约束：周五不发版\n"
    svc.import_manual_document(doc.meta, new_body)
    confirmed = svc.store.list_confirmed()
    assert any("周五不发版" in f["statement"] for f in confirmed)
