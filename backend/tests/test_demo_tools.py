from app.engine.agent.prompts import MODE_DEFAULT
from app.engine.agent.tool_catalog import select_tools
from app.engine.agent.tool_impl.demo_preview import (
    DEMO_BLOCKED_TOOLS,
    DEMO_PREVIEW_TOOLS,
)


def _names(tools):
    return {t["function"]["name"] for t in tools}


def test_demo_catalog_drops_blocked_tools():
    names = _names(
        select_tools(MODE_DEFAULT, web_enabled=True, sandbox_enabled=True, demo=True)
    )
    assert names & DEMO_BLOCKED_TOOLS == set()


def test_demo_catalog_keeps_preview_tools_with_same_names():
    """同名同 schema：提示词与已沉淀的 Skill 方法不必为 demo 改写。"""
    names = _names(select_tools(MODE_DEFAULT, web_enabled=True, demo=True))
    assert DEMO_PREVIEW_TOOLS <= names | {"summarize_conversation"}
    assert "write_doc" in names
    assert "edit_doc" in names
    assert "manage_memory" in names


def test_demo_catalog_keeps_read_tools_and_web_search():
    names = _names(select_tools(MODE_DEFAULT, web_enabled=True, demo=True))
    assert {"search_kb", "read_doc", "list_kb_structure", "recall_memory"} <= names
    assert "web_search" in names


def test_demo_catalog_drops_fetch_url():
    """让匿名访客指定任意 URL 由服务器抓取是 SSRF 面。"""
    assert "fetch_url" not in _names(
        select_tools(MODE_DEFAULT, web_enabled=True, demo=True)
    )


def test_non_demo_catalog_is_unchanged():
    names = _names(select_tools(MODE_DEFAULT, web_enabled=True))
    assert "fetch_url" in names
    assert "write_kb_file" in names
