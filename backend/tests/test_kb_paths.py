import pytest

from app.storage.kb_paths import KbPathError, join_kb_path


def test_join_kb_path():
    assert join_kb_path("技术/llm", "对比.md") == "技术/llm/对比.md"
    assert join_kb_path("", "root.md") == "root.md"


def test_join_kb_path_rejects_bad_filename():
    with pytest.raises(KbPathError):
        join_kb_path("技术", "note.txt")
    with pytest.raises(KbPathError):
        join_kb_path("技术", "../escape.md")
