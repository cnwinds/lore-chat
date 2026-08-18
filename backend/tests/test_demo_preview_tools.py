import pytest

from app.engine.agent.tool_impl.demo_preview import (
    blocked_result,
    demo_tool_result,
    preview_manage_memory,
    preview_write_doc,
)


def test_write_doc_preview_reports_target_and_content():
    out = preview_write_doc(
        {"directory": "技术/检索", "filename": "选型.md", "text": "正文"}
    )
    assert out["status"] == "preview_only"
    assert out["preview"]["kind"] == "doc"
    assert out["preview"]["path"] == "技术/检索/选型.md"
    assert out["preview"]["content"] == "正文"


def test_write_doc_preview_prepends_context():
    out = preview_write_doc(
        {"directory": "技术", "filename": "a.md", "text": "正文", "context": "背景"}
    )
    assert out["preview"]["content"] == "背景\n\n正文"


def test_write_doc_preview_summary_says_not_persisted():
    """工具返回值必须让模型无法宣称已保存。"""
    out = preview_write_doc({"directory": "技术", "filename": "a.md", "text": "x"})
    assert "未落盘" in out["summary"]


def test_write_doc_preview_propagates_path_error():
    out = preview_write_doc({"directory": "技术", "filename": "a.txt", "text": "x"})
    assert out.get("status") != "preview_only"


def test_manage_memory_preview():
    out = preview_manage_memory({"action": "remember", "content": "偏好结论先行"})
    assert out["status"] == "preview_only"
    assert out["preview"]["kind"] == "memory"
    assert out["preview"]["content"] == "偏好结论先行"


def test_blocked_result_shape():
    out = blocked_result("sandbox_run")
    assert out["error"] == "demo_tool_unavailable"
    assert out["status"] == "failed"


@pytest.mark.parametrize("name", ["sandbox_run", "generate_image", "fetch_url"])
def test_demo_tool_result_blocks(name):
    assert demo_tool_result(name, {})["error"] == "demo_tool_unavailable"


def test_demo_tool_result_passes_through_read_tools():
    assert demo_tool_result("search_kb", {"query": "x"}) is None


def test_registry_in_demo_never_writes(tmp_path):
    """兜底层：即使模型幻觉出写工具名，也不能落盘。"""
    import asyncio

    from app.config import Settings
    from app.deps import build_container
    from app.models.llm import FakeLLMClient

    settings = Settings(kb_path=tmp_path / "knowledge", demo_mode=True)
    container = build_container(settings, llm=FakeLLMClient(chat_responses=["x"], embed_dim=8))
    out = asyncio.run(
        container.agent.tools.execute(
            "write_kb_file", {"directory": "技术", "filename": "a.sh", "text": "echo"}
        )
    )
    assert out["error"] == "demo_tool_unavailable"
    assert not (tmp_path / "knowledge" / "技术" / "a.sh").exists()
