from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.storage.repo import KnowledgeRepo


def _service(tmp_path, repo=None):
    repo = repo or KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    return MemoryService(store, repo)


def test_remember_rejects_secret_statement(tmp_path):
    svc = _service(tmp_path)
    out = svc.remember("我的 key=sk-abcdefghijklmnopqrstuvwxyz0123456789")
    assert out["ok"] is False
    assert out["error"] == "secret_rejected"
    assert svc.store.list_confirmed() == []


def test_forget_creates_tombstone_and_blocks_same_value(tmp_path):
    svc = _service(tmp_path)
    f = svc.remember("记住我喜欢简洁回答")["fact"]
    svc.forget(fact_id=f["id"])
    again = svc.remember("记住我喜欢简洁回答")
    assert again["ok"] is False
    assert again["error"] == "tombstoned"
