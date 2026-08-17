"""ConversationTranscript：本轮产出路径投影进 llm_history。"""

from __future__ import annotations

from app.engine.conversation.transcript import ConversationTranscript


def test_llm_history_appends_turn_output_paths_from_attachments():
    conv = {
        "messages": [
            {"role": "user", "text": "画一个图标"},
            {
                "role": "assistant",
                "text": "已生成。",
                "attachments": ["媒体/生成/2026-08/icon.svg"],
            },
            {"role": "user", "text": "把颜色改成蓝"},
        ]
    }
    history = ConversationTranscript.llm_history(conv)
    assert history[0] == {"role": "user", "content": "画一个图标"}
    assert history[1]["role"] == "assistant"
    assert "已生成。" in history[1]["content"]
    assert "【本轮产出】" in history[1]["content"]
    assert "- 媒体/生成/2026-08/icon.svg" in history[1]["content"]
    assert history[2] == {"role": "user", "content": "把颜色改成蓝"}


def test_llm_history_collects_write_tool_sources_not_search():
    conv = {
        "messages": [
            {"role": "user", "text": "写文档"},
            {
                "role": "assistant",
                "timeline": [
                    {
                        "type": "tool",
                        "tool": "search_kb",
                        "status": "done",
                        "sources": [{"type": "kb", "path": "笔记/旧.md"}],
                    },
                    {
                        "type": "tool",
                        "tool": "write_doc",
                        "status": "done",
                        "sources": [{"type": "kb", "path": "笔记/新.md"}],
                    },
                    {"type": "text", "content": "写好了"},
                ],
            },
        ]
    }
    history = ConversationTranscript.llm_history(conv)
    content = history[1]["content"]
    assert "笔记/新.md" in content
    assert "笔记/旧.md" not in content


def test_llm_history_attachments_only_still_projects():
    conv = {
        "messages": [
            {"role": "user", "text": "生图"},
            {
                "role": "assistant",
                "timeline": [
                    {
                        "type": "tool",
                        "tool": "generate_image",
                        "status": "done",
                        "attachments": ["媒体/生成/2026-08/a.png"],
                    }
                ],
            },
        ]
    }
    history = ConversationTranscript.llm_history(conv)
    assert len(history) == 2
    assert history[1]["content"].startswith("【本轮产出】")
    assert "媒体/生成/2026-08/a.png" in history[1]["content"]


def test_indexable_text_does_not_include_turn_output_footer():
    conv = {
        "messages": [
            {"role": "user", "text": "画"},
            {
                "role": "assistant",
                "text": "好了",
                "attachments": ["媒体/生成/2026-08/x.png"],
            },
        ]
    }
    indexed = ConversationTranscript.indexable_text(conv)
    assert indexed == "画\n\n好了"
    assert "本轮产出" not in indexed


def test_llm_history_ignores_non_write_tool_attachments():
    conv = {
        "messages": [
            {"role": "user", "text": "搜一下"},
            {
                "role": "assistant",
                "text": "找到了",
                "timeline": [
                    {
                        "type": "tool",
                        "tool": "search_kb",
                        "status": "done",
                        "attachments": ["笔记/误挂.md"],
                        "sources": [{"type": "kb", "path": "笔记/命中.md"}],
                    }
                ],
            },
        ]
    }
    history = ConversationTranscript.llm_history(conv)
    assert history[1]["content"] == "找到了"
    assert "本轮产出" not in history[1]["content"]


def test_context_excerpt_omits_turn_output_footer():
    conv = {
        "messages": [
            {"role": "user", "text": "画"},
            {
                "role": "assistant",
                "text": "好了",
                "attachments": ["媒体/生成/2026-08/x.png"],
            },
        ]
    }
    excerpt = ConversationTranscript.context_excerpt(conv)
    assert "产出" not in excerpt
    assert "媒体/生成" not in excerpt
