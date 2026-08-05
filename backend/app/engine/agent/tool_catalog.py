from __future__ import annotations

from app.engine.knowledge_writer import KnowledgeWriter

resolve_kb_location = KnowledgeWriter.resolve_location

READ_ONLY_TOOLS = frozenset({
    "search_kb", "read_doc", "list_kb_structure", "read_conversation_context",
    "fetch_url", "web_search",
    "recall_memory",
})
WRITE_TOOLS = frozenset({
    "write_kb", "delete_kb", "ask_user", "summarize_conversation", "edit_doc",
    "manage_memory", "move_entry",
})

_DEFAULT_DISCLOSURE_CHARS = 3000


def can_parallelize(tool_names: list[str]) -> bool:
    return all(n in READ_ONLY_TOOLS for n in tool_names)


TOOL_LABELS = {
    "search_kb": "检索本地知识库",
    "read_doc": "读取文档",
    "list_kb_structure": "查看知识库目录结构",
    "read_conversation_context": "读取会话邻近消息",
    "fetch_url": "打开链接",
    "web_search": "搜索网页",
    "write_kb": "写入知识库文档",
    "summarize_conversation": "归档整段会话",
    "delete_kb": "删除知识库内容",
    "ask_user": "征询用户",
    "edit_doc": "局部编辑文档",
    "move_entry": "移动或重命名路径",
    "manage_memory": "管理长期用户记忆",
    "recall_memory": "回忆已确认的用户画像",
}

_KB_DIRECTORY_DESC = (
    "相对知识库根的目录，不含首尾斜杠；根目录下文档传空字符串。"
    "示例：技术/llm、projects/mini-app"
)
_KB_FILENAME_DESC = "Markdown 文件名，必须以 .md 结尾。示例：DeepSeek对比.md、常用命令.md"


def _path_fields(*, directory_required: bool = True, filename_required: bool = True) -> dict:
    props = {
        "directory": {"type": "string", "description": _KB_DIRECTORY_DESC},
        "filename": {"type": "string", "description": _KB_FILENAME_DESC},
    }
    required = []
    if directory_required:
        required.append("directory")
    if filename_required:
        required.append("filename")
    return props, required




TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_kb",
            "description": "检索本地知识库，查找与用户问题相关的文档片段",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或问题"},
                    "k": {"type": "integer", "description": "返回条数，默认 5", "default": 5},
                    "scope": {
                        "type": "string",
                        "enum": ["all", "knowledge", "conversations"],
                        "description": "检索范围：全部 / 仅知识库 / 仅会话",
                    },
                    "conversation_id": {
                        "type": "string",
                        "description": "限定在某个会话内检索（scope=conversations 时有效）；显式传入时覆盖默认的「排除当前会话」",
                    },
                    "cursor": {
                        "type": "string",
                        "description": "分页游标，用于续取上一页未返回的结果",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_doc",
            "description": (
                "按渐进式披露读取知识库文档：默认返回前 3000 字，并附结构大纲（各标题及字符位置）。"
                "内容不足时，用 offset 跳到相关小节或翻页继续读取，不要盲目全量读取。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文档相对路径，如 技术/docker/常用命令.md"},
                    "offset": {"type": "integer", "description": "从第几个字符开始读取，默认 0；可用返回的 next_offset 或大纲中的 @位置", "default": 0},
                    "limit": {"type": "integer", "description": "本次最多读取字符数，默认 3000", "default": 3000},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_kb_structure",
            "description": (
                "列出知识库当前目录结构与各目录下的文档文件名（只读）。"
                "在 write_kb、summarize_conversation、move_entry 之前必须先调用本工具，"
                "据此决定放入已有目录、新建子目录或 move_entry 调整结构；禁止凭记忆编造路径。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_conversation_context",
            "description": "读取某条会话消息及其前后若干条邻近消息（用于核验检索命中、展开上下文）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "message_id": {"type": "string"},
                    "before_messages": {"type": "integer", "minimum": 0, "maximum": 10, "default": 2},
                    "after_messages": {"type": "integer", "minimum": 0, "maximum": 10, "default": 2},
                },
                "required": ["conversation_id", "message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "抓取并解析网页为 Markdown，按渐进式披露返回：默认前 3000 字。"
                "同一链接会缓存，需要更多时用 offset 继续，不会重复抓取。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要抓取的 HTTP/HTTPS 链接"},
                    "offset": {"type": "integer", "description": "从第几个字符开始，默认 0；用返回的 next_offset 继续", "default": 0},
                    "limit": {"type": "integer", "description": "本次最多返回字符数，默认 3000", "default": 3000},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索，获取网页摘要（需已配置搜索 API）",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "k": {"type": "integer", "description": "返回条数，默认 5", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_kb",
            "description": (
                "将内容写入知识库。必须指定 directory 与 filename（目录 + 文件名）。"
                "写入前应先 list_kb_structure 规划路径。"
                "目标文件已存在时合并重组；不存在时在指定路径新建。"
                "禁止 conv: 等内部前缀、禁止会话 id 当目录名。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要写入的正文内容"},
                    "context": {
                        "type": "string",
                        "description": "可选上下文（如来源说明），会拼接到正文前",
                    },
                    **_path_fields()[0],
                },
                "required": ["text", "directory", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_doc",
            "description": (
                "对已有知识库文档做局部修改（替换或插入）。"
                "修改前必须先 read_doc 读取目标区域；old_string 必须从 read_doc 返回内容中精确复制。"
                "小范围修改优先于 write_kb。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文档相对路径，如 技术/docker/常用命令.md",
                    },
                    "edits": {
                        "type": "array",
                        "description": "按顺序应用的多处替换（同一文件原子提交）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "old_string": {
                                    "type": "string",
                                    "description": "要被替换的原文（精确匹配，含换行）",
                                },
                                "new_string": {
                                    "type": "string",
                                    "description": "替换后的内容；删除内容时传空字符串",
                                },
                                "replace_all": {
                                    "type": "boolean",
                                    "description": "为 true 时替换所有匹配项，默认 false",
                                    "default": False,
                                },
                            },
                            "required": ["old_string", "new_string"],
                        },
                        "minItems": 1,
                    },
                    "insert": {
                        "type": "object",
                        "description": "在指定位置插入内容（不删除原文）。与 edits 互斥。",
                        "properties": {
                            "after_heading": {
                                "type": "string",
                                "description": "在此 Markdown 标题行之后插入，如 '## 部署步骤'",
                            },
                            "at_offset": {
                                "type": "integer",
                                "description": "或在此字符偏移处插入（来自 read_doc 大纲 @位置）",
                            },
                            "content": {
                                "type": "string",
                                "description": "要插入的 Markdown 正文",
                            },
                        },
                        "required": ["content"],
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_conversation",
            "description": (
                "把当前整段会话通读后全局重构、去重、成文，归档为一篇知识库文档。"
                "用户要求「总结/归档本次会话/整理成文档/生成会话纪要」时调用。"
                "归档前应先 list_kb_structure 规划 directory 与 filename；必须指定二者。"
            ),
            "parameters": {
                "type": "object",
                "properties": _path_fields()[0],
                "required": ["directory", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_entry",
            "description": (
                "移动知识库中的 Markdown 文件、附件，或整个目录（如 Skill 包目录）。"
                "与侧栏拖放移动行为一致：目录移动时 to_filename 为新文件夹名（省略则用原目录名）；"
                "单文件移动时 to_filename 为目标 .md 文件名（省略则用原文件名）。"
                "移动前建议 list_kb_structure；目标路径不得已存在。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_path": {
                        "type": "string",
                        "description": (
                            "当前相对路径：.md 文件、attachments 下文件，或目录（如 skill/张雪峰）"
                        ),
                    },
                    "to_directory": {
                        "type": "string",
                        "description": _KB_DIRECTORY_DESC,
                    },
                    "to_filename": {
                        "type": "string",
                        "description": (
                            "目标文件名（.md 或附件名）或新目录名；省略时保留 from_path 最后一段名称"
                        ),
                    },
                },
                "required": ["from_path", "to_directory"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_kb",
            "description": "删除知识库中的文档或目录（含目录下所有文件）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的相对路径，如 projects/mini-app/version-todo.md 或 projects/mini-app/",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_memory",
            "description": "记住、更正或遗忘关于用户自身的长期画像事实（不是话题知识）",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["remember", "correct", "forget"],
                    },
                    "statement": {"type": "string", "description": "要记住/定位的事实描述"},
                    "fact_id": {"type": "string", "description": "correct/forget 时优先使用"},
                    "replacement": {"type": "string", "description": "correct 时的新内容"},
                    "clear_tombstone": {
                        "type": "boolean",
                        "description": "重新记住已遗忘事实时设为 true",
                        "default": False,
                    },
                },
                "required": ["action", "statement"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "查询已确认的用户长期记忆画像，可选返回来源解释",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或自然语言问题"},
                    "include_sources": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "向用户提出选择题，等待用户确认后再继续",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "向用户展示的问题"},
                    "options": {
                        "type": "array",
                        "description": "选项列表，每项含 id 和 label",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                            },
                            "required": ["id", "label"],
                        },
                    },
                    "multi_select": {
                        "type": "boolean",
                        "description": "是否允许多选，默认 false",
                        "default": False,
                    },
                    "context": {
                        "type": "string",
                        "description": "可选背景信息，帮助用户理解选项",
                    },
                },
                "required": ["question", "options"],
            },
        },
    },
]

_MODE_NO_WRITE = "no_write"


def select_tools(
    mode: str,
    web_enabled: bool,
    *,
    search_configured: bool = True,
) -> list[dict]:
    """按 mode 与联网能力硬门过滤下发给模型的工具集。

    - web_enabled=False 或未配置搜索 provider：移除 web_search（保留 fetch_url）。
    - mode=no_write：移除 write_kb（/api/ask；此前仅靠 prompt 约束，此处收紧为硬门）。
    - mode=force_write：保留 write_kb（/api/ingest 依赖 prompt 强制调用）。

    /api/chat 使用 mode=default。ingest/ask 为测试与脚本同步 API，见
    docs/superpowers/specs/2026-07-12-ingest-ask-api-design.md
    """
    excluded: set[str] = set()
    if not web_enabled or not search_configured:
        excluded.add("web_search")
    if mode == _MODE_NO_WRITE:
        excluded.add("write_kb")
        excluded.add("manage_memory")
    return [d for d in TOOL_DEFINITIONS if d["function"]["name"] not in excluded]
