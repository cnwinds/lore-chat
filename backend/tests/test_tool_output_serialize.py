"""tool 结果序列化：provenance_groups 不得因 Hit 导致整轮中断。"""

import json

from app.engine.agent.tool_loop import AgentToolLoop
from app.engine.provenance import group_provenance
from app.index.types import Hit


def test_serialize_search_kb_with_provenance_groups():
    kb = Hit("d1", "摘要段", 1.0, "技术/glm.md")
    msg = Hit(
        "c1",
        "原文片段",
        0.9,
        "conv:cid1",
        message_id="m1",
        start_char=0,
        end_char=4,
        role="user",
        ts="2026-08-14T16:00:00+08:00",
        conversation_title="glm",
    )
    groups = group_provenance(
        [kb, msg], doc_conversation_ids={"技术/glm.md": ["cid1"]}
    )
    assert groups
    out = {
        "summary": "找到 2 条相关内容",
        "sources": [{"type": "kb", "path": "技术/glm.md", "excerpt": "摘要段"}],
        "hits": [kb, msg],  # 运行时字段，应被剥离
        "has_more": False,
        "index_revision": "1",
        "provenance_groups": groups,
    }
    text = AgentToolLoop._serialize_tool_output(out)
    payload = json.loads(text)
    assert "hits" not in payload
    assert "provenance_groups" in payload
    assert payload["provenance_groups"][0]["hits"][0]["doc_id"] == "d1"


def test_serialize_fallback_raw_hit_in_nested_payload():
    """防御：即便上游漏转 dict，default 也应兜住。"""
    h = Hit("d", "c", 1.0, "a.md")
    out = {"summary": "x", "sources": [], "oops": h}
    text = AgentToolLoop._serialize_tool_output(out)
    assert json.loads(text)["oops"]["doc_id"] == "d"
