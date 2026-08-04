import pytest

from app.storage.kb_paths import KbPathError, join_kb_path


def test_join_kb_path():
    assert join_kb_path("技术/llm", "对比.md") == "技术/llm/对比.md"
    assert join_kb_path("", "root.md") == "root.md"


def test_join_kb_path_rejects_conv_prefix():
    with pytest.raises(KbPathError):
        join_kb_path("conv:abc", "note.md")
    with pytest.raises(KbPathError):
        join_kb_path("技术", "conv:abc.md")
