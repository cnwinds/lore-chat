"""模型漏出的工具协议 XML 不得进入可见正文。"""

from app.engine.visible_text import VisibleTextStream, strip_protocol_markup


def test_strips_lone_old_function_results_tag():
    assert strip_protocol_markup("<old_function_results>") == ""
    assert strip_protocol_markup("<old_function_results>\n") == ""


def test_strips_complete_protocol_block():
    raw = "<old_function_results>\n{\"ok\": true}\n</old_function_results>\n你好"
    assert strip_protocol_markup(raw) == "你好"


def test_strips_same_class_tool_and_function_wrappers():
    for tag in (
        "function_results",
        "function_calls",
        "tool_call",
        "tool_result",
        "tool_response",
        "minimax:tool_call",
    ):
        assert strip_protocol_markup(f"<{tag}>payload</{tag}>\n结论") == "结论"


def test_keeps_ordinary_markup_and_prose():
    text = "用 <div> 包一层，再画 <svg> 图标。"
    assert strip_protocol_markup(text) == text


def test_preserves_protocol_tags_inside_fenced_code():
    raw = "示例：\n```\n<tool_call>search</tool_call>\n```\n"
    assert "<tool_call>search</tool_call>" in strip_protocol_markup(raw)


def test_strips_qwen_attribute_style_tags():
    raw = "<function=read><parameter=path>/tmp/a</parameter></function>\n好了"
    assert strip_protocol_markup(raw) == "好了"


def test_stream_holds_split_tag_then_drops_it():
    s = VisibleTextStream()
    assert s.push("<old_fun") == []
    assert s.push("ction_results>\n") == []
    assert s.flush() == []


def test_stream_emits_prose_after_lone_tag():
    s = VisibleTextStream()
    assert s.push("<old_function_results>\n") == []
    assert s.push("你好！接着上次") == ["你好！接着上次"]
    assert s.flush() == []


def test_stream_swallows_matched_block_payload():
    s = VisibleTextStream()
    assert s.push("<tool_call>\n") == []
    assert s.push('{"name": "search_kb"}\n') == []
    assert s.push("</tool_call>\n你好") == ["你好"]
    assert s.flush() == []


def test_stream_passes_ordinary_text_through():
    s = VisibleTextStream()
    assert s.push("你好") == ["你好"]
    assert s.push("，主人") == ["，主人"]
    assert s.flush() == []
