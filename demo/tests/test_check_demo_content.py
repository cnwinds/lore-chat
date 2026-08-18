import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_demo_content import find_dangling_kb_refs, find_forbidden


def test_clean_tree_passes(tmp_path):
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "a.md").write_text("# A", encoding="utf-8")
    (tmp_path / "memory.json").write_text("{}", encoding="utf-8")
    assert find_forbidden(tmp_path) == []


def test_settings_json_is_rejected(tmp_path):
    (tmp_path / ".kb").mkdir()
    (tmp_path / ".kb" / "settings.json").write_text("{}", encoding="utf-8")
    assert find_forbidden(tmp_path)


def test_auth_json_is_rejected(tmp_path):
    (tmp_path / ".kb").mkdir()
    (tmp_path / ".kb" / "auth.json").write_text("{}", encoding="utf-8")
    assert find_forbidden(tmp_path)


def test_sqlite_is_rejected(tmp_path):
    (tmp_path / "conversations.db").write_bytes(b"SQLite")
    assert find_forbidden(tmp_path)


def test_wal_and_shm_are_rejected(tmp_path):
    (tmp_path / "x.db-wal").write_bytes(b"")
    (tmp_path / "y.db-shm").write_bytes(b"")
    assert len(find_forbidden(tmp_path)) == 2


def test_index_dir_is_rejected(tmp_path):
    (tmp_path / ".kb" / "index").mkdir(parents=True)
    (tmp_path / ".kb" / "index" / "fts.db").write_bytes(b"")
    assert find_forbidden(tmp_path)


def test_cooldown_json_is_rejected(tmp_path):
    (tmp_path / "model_cooldown.json").write_text("{}", encoding="utf-8")
    assert find_forbidden(tmp_path)


def test_conversation_path_must_exist_in_knowledge(tmp_path):
    (tmp_path / "knowledge" / "技术").mkdir(parents=True)
    (tmp_path / "knowledge" / "技术" / "现名.md").write_text("# ok", encoding="utf-8")
    (tmp_path / "conversations").mkdir()
    (tmp_path / "conversations" / "c1.json").write_text(
        '{"messages":[{"text":"已存入 `技术/旧名.md`","sources_json":"[{\\"path\\":\\"技术/旧名.md\\"}]"}]}',
        encoding="utf-8",
    )
    assert find_dangling_kb_refs(tmp_path)


def test_matching_conversation_path_passes(tmp_path):
    (tmp_path / "knowledge" / "技术").mkdir(parents=True)
    (tmp_path / "knowledge" / "技术" / "现名.md").write_text("# ok", encoding="utf-8")
    (tmp_path / "conversations").mkdir()
    (tmp_path / "conversations" / "c1.json").write_text(
        '{"messages":[{"text":"已存入 `技术/现名.md`","sources_json":"[{\\"path\\":\\"技术/现名.md\\"}]"}]}',
        encoding="utf-8",
    )
    assert find_dangling_kb_refs(tmp_path) == []


def test_dangling_svg_ref_is_caught(tmp_path):
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "conversations").mkdir()
    (tmp_path / "conversations" / "c1.json").write_text(
        '{"messages":[{"sources_json":"[{\\"path\\":\\"媒体/生成/2026-08/旧图.svg\\"}]"}]}',
        encoding="utf-8",
    )
    assert find_dangling_kb_refs(tmp_path)


def test_matching_svg_ref_passes(tmp_path):
    dest = tmp_path / "knowledge" / "媒体" / "生成" / "2026-08"
    dest.mkdir(parents=True)
    (dest / "数据流.svg").write_text("<svg></svg>", encoding="utf-8")
    (tmp_path / "conversations").mkdir()
    (tmp_path / "conversations" / "c1.json").write_text(
        '{"messages":[{"sources_json":"[{\\"path\\":\\"媒体/生成/2026-08/数据流.svg\\"}]"}]}',
        encoding="utf-8",
    )
    assert find_dangling_kb_refs(tmp_path) == []
