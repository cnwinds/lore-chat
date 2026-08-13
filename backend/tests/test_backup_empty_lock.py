import pytest

from app.backup.empty import is_kb_empty
from app.backup.lock import MaintenanceActiveError, MaintenanceLock
from app.engine.conversations import ConversationStore


def test_empty_fresh(tmp_path):
    assert is_kb_empty(tmp_path) is True


def test_non_empty_with_doc(tmp_path):
    p = tmp_path / "技术"
    p.mkdir()
    (p / "a.md").write_text("# a\n", encoding="utf-8")
    assert is_kb_empty(tmp_path) is False


def test_empty_with_system_layer_only(tmp_path):
    system = tmp_path / "系统"
    system.mkdir()
    (system / "戒律.md").write_text("# rules\n", encoding="utf-8")
    assert is_kb_empty(tmp_path) is True


def test_empty_with_skills_dir_gitkeep_only(tmp_path):
    skills = tmp_path / "技能"
    skills.mkdir()
    (skills / ".gitkeep").write_text("", encoding="utf-8")
    assert is_kb_empty(tmp_path) is True


def test_non_empty_with_conversation(tmp_path):
    store = ConversationStore(tmp_path / ".kb" / "conversations")
    store.create()
    assert is_kb_empty(tmp_path) is False


def test_non_empty_with_file(tmp_path):
    d = tmp_path / "技术" / "docker"
    d.mkdir(parents=True)
    (d / "plan.pdf").write_bytes(b"%PDF-1.4 fake")
    assert is_kb_empty(tmp_path) is False


def test_lock_blocks_second_acquire():
    lock = MaintenanceLock()
    lock.acquire("export")
    with pytest.raises(MaintenanceActiveError):
        lock.acquire("import")
    lock.release()
    lock.acquire("import")
    lock.release()


def test_lock_is_active_and_reason():
    lock = MaintenanceLock()
    assert lock.is_active() is False
    assert lock.reason() is None
    lock.acquire("export")
    assert lock.is_active() is True
    assert lock.reason() == "export"
    lock.release()
    assert lock.is_active() is False
    assert lock.reason() is None


def test_empty_ignores_kb_internal_md(tmp_path):
    internal = tmp_path / ".kb" / "changelog.md"
    internal.parent.mkdir(parents=True)
    internal.write_text("# log\n", encoding="utf-8")
    assert is_kb_empty(tmp_path) is True
