from __future__ import annotations

import copy

from app.engine.disclosure import DisclosureWindows
from app.engine.knowledge_writer import KnowledgeWriter

resolve_kb_location = KnowledgeWriter.resolve_location

READ_ONLY_TOOLS = frozenset({
    "search_kb", "read_doc", "read_doc_meta", "list_kb_structure", "read_conversation_context",
    "fetch_url", "web_search",
    "recall_memory",
    "sandbox_list_dir", "sandbox_read_file", "sandbox_job_status",
})
WRITE_TOOLS = frozenset({
    "write_doc", "write_kb_file", "delete_kb", "ask_user", "summarize_conversation",
    "edit_doc", "update_doc_meta",
    "manage_memory", "move_entry",
    "generate_image",
    "sandbox_run", "publish_from_sandbox", "stage_to_sandbox",
})
# 可读工具 + 生图：落盘路径互不冲突（chat_attachment 自动唯一名），可同批并行。
# 其余写工具仍串行，避免文档竞态。
PARALLELIZABLE_TOOLS = READ_ONLY_TOOLS | frozenset({"generate_image"})

# 兼容旧导入（默认窗数值）
_DEFAULT_DISCLOSURE_CHARS = DisclosureWindows().spot
_DEEP_DISCLOSURE_CHARS = DisclosureWindows().deep
_MAX_DISCLOSURE_CHARS = DisclosureWindows().max_chars


def disclosure_intent_limit_props(windows: DisclosureWindows) -> dict:
    """intent / limit 参数 schema；字数来自传入窗口配置。"""
    return {
        "intent": {
            "type": "string",
            "enum": ["spot", "deep"],
            "description": (
                "读取意图：spot=问答取证（可先 search_kb，再小窗阅读；"
                f"默认约 {windows.spot} 字，limit 也不得超过该小窗）；"
                f"deep=深读/核对/成文（默认约 {windows.deep} 字，"
                f"limit 可放大至硬上限 {windows.max_chars}）。"
            ),
            "default": "spot",
        },
        "limit": {
            "type": "integer",
            "description": (
                f"本次最多字符数；省略则按 intent（spot≈{windows.spot}，"
                f"deep≈{windows.deep}）。spot 上限为小窗；"
                f"deep 硬上限 {windows.max_chars}。"
            ),
        },
    }


def _read_doc_description(windows: DisclosureWindows) -> str:
    return (
        "按渐进式披露读取知识库文档或文本资产："
        "Markdown 返回正文并附结构大纲；白名单文本文件（.sh/.py 等）按纯文本读取。"
        f"默认 intent=spot（约 {windows.spot} 字，可先 search_kb）；"
        f"深读/核对/成文用 intent=deep（默认约 {windows.deep} 字，硬上限 {windows.max_chars}）。"
        "内容不足时用 offset 续读，不要盲目全量读取。"
    )


def _fetch_url_description(windows: DisclosureWindows) -> str:
    return (
        "抓取并解析网页或 PDF 为 Markdown，按渐进式披露返回。"
        "支持微信公众号文章链接（内部自动处理）。"
        f"默认 intent=spot（约 {windows.spot} 字）；"
        f"深读/核对/成文用 intent=deep（默认约 {windows.deep} 字，硬上限 {windows.max_chars}）。"
        "同一链接会缓存，需要更多时用 offset 继续，不会重复抓取。"
    )


def apply_disclosure_windows(tool_def: dict, windows: DisclosureWindows) -> dict:
    """返回注入当前窗口配置后的工具定义副本。"""
    out = copy.deepcopy(tool_def)
    name = out["function"]["name"]
    props = out["function"]["parameters"]["properties"]
    props.update(disclosure_intent_limit_props(windows))
    if name == "read_doc":
        out["function"]["description"] = _read_doc_description(windows)
    elif name == "fetch_url":
        out["function"]["description"] = _fetch_url_description(windows)
    return out


def can_parallelize(tool_names: list[str]) -> bool:
    return all(n in PARALLELIZABLE_TOOLS for n in tool_names)


TOOL_LABELS = {
    "search_kb": "检索本地知识库",
    "read_doc": "读取文档",
    "read_doc_meta": "读取文档元数据",
    "list_kb_structure": "查看知识库目录结构",
    "read_conversation_context": "读取会话邻近消息",
    "fetch_url": "打开链接",
    "web_search": "搜索网页",
    "generate_image": "生成图片",
    "write_doc": "写入文档",
    "write_kb_file": "写入知识库代码/文本文件",
    "summarize_conversation": "归档整段会话",
    "delete_kb": "删除知识库内容",
    "ask_user": "征询用户",
    "edit_doc": "局部编辑文档",
    "update_doc_meta": "更新文档元数据",
    "move_entry": "移动或重命名路径",
    "manage_memory": "管理长期用户记忆",
    "recall_memory": "回忆已确认的用户画像",
    "sandbox_run": "在沙箱执行命令",
    "sandbox_list_dir": "列出沙箱目录",
    "sandbox_read_file": "读取沙箱文件",
    "publish_from_sandbox": "从沙箱批量发布到知识库",
    "stage_to_sandbox": "将知识库文件批量投放到沙箱",
    "sandbox_job_status": "查询沙箱后台任务",
}


def resolve_tool_label(name: str, arguments: dict | None = None) -> str:
    """时间线展示名：同工具按产物类型区分（SVG 是图像资产，不是代码/文本）。"""
    base = TOOL_LABELS.get(name, name)
    if name != "write_kb_file" or not isinstance(arguments, dict):
        return base
    fn = str(arguments.get("filename") or "").strip().lower()
    if fn.endswith(".svg"):
        return "写入知识库矢量图"
    return base


SANDBOX_TOOLS = frozenset({
    "sandbox_run",
    "sandbox_list_dir",
    "sandbox_read_file",
    "publish_from_sandbox",
    "stage_to_sandbox",
    "sandbox_job_status",
})

_KB_DIRECTORY_DESC = (
    "相对知识库根的目录，不含首尾斜杠；根目录下文档传空字符串。"
    "示例：技术/llm、projects/mini-app"
)
_KB_FILENAME_DESC = "Markdown 文件名，必须以 .md 结尾。示例：DeepSeek对比.md、常用命令.md"
_KB_FILE_FILENAME_DESC = (
    "非 Markdown 文件名：文本代码/配置（.sh/.py/.js/.yaml 等），"
    "或矢量图 .svg（按图片资产落盘并预览）；禁止 .md（文档请用 write_doc）。"
    "示例：gen_audio.sh、fetch.py、logo.svg"
)


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
            "description": _read_doc_description(DisclosureWindows()),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文档相对路径，如 技术/docker/常用命令.md"},
                    "offset": {"type": "integer", "description": "从第几个字符开始读取，默认 0；可用返回的 next_offset 或大纲中的 @位置", "default": 0},
                    **disclosure_intent_limit_props(DisclosureWindows()),
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
                "在 write_doc、write_kb_file、summarize_conversation、move_entry 之前必须先调用本工具，"
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
            "description": _fetch_url_description(DisclosureWindows()),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要抓取的 HTTP/HTTPS 链接（支持 HTML 与 PDF）",
                    },
                    "offset": {"type": "integer", "description": "从第几个字符开始，默认 0；用返回的 next_offset 继续", "default": 0},
                    **disclosure_intent_limit_props(DisclosureWindows()),
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
            "name": "generate_image",
            "description": (
                "根据文字描述生成一张图片并保存到知识库。"
                "默认 destination=chat_attachment，写入 媒体/生成/{年月}/，结果以附件形式出现在信息流；"
                "若需写入指定知识库路径供文档引用，用 destination=kb 并提供 directory 与 filename（均必填）。"
                "文档中请用相对路径 Markdown 插图：![说明](相对路径)。"
                "用户要多张图（多构思/多变体）时：在同一轮一次性发出多个 generate_image（不同 prompt），"
                "系统会并行生图；勿等一张完成再调下一张。"
                "需已配置生图提供商。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "图片内容描述（英文或中文）",
                    },
                    "aspect_ratio": {
                        "type": "string",
                        "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"],
                        "description": "宽高比，默认 1:1",
                        "default": "1:1",
                    },
                    "destination": {
                        "type": "string",
                        "enum": ["chat_attachment", "kb"],
                        "description": (
                            "chat_attachment=会话附件（默认，写入 媒体/生成/{年月}/）；"
                            "kb=指定知识库目录与文件名"
                        ),
                        "default": "chat_attachment",
                    },
                    "directory": {
                        "type": "string",
                        "description": "destination=kb 时的目标目录（相对知识库根）",
                    },
                    "filename": {
                        "type": "string",
                        "description": "destination=kb 时必填的文件名（可省略扩展名，默认 .png）",
                    },
                    "provider": {
                        "type": "string",
                        "description": (
                            "可选弱覆盖：优先尝试该提供商 id 或类型（openai/zhipu/bailian/agnes）；"
                            "失败后仍可切换链上其余提供商"
                        ),
                    },
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_doc",
            "description": (
                "将 Markdown 正文写入知识库。必须指定 directory 与 filename；"
                "写入前先 list_kb_structure。可选 meta（title/tags/source）；"
                "正文勿含元数据头。已存在则默认合并，不存在则新建。"
                "Skill 包放在「技能」目录下；Skill 的 name/description 触发头写在正文 --- YAML，勿放进 meta。"
                "禁止 conv: 前缀、禁止会话 id 当目录名。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "正文内容",
                    },
                    "context": {
                        "type": "string",
                        "description": "可选上下文（如来源说明），会拼接到正文前",
                    },
                    "meta": {
                        "type": "object",
                        "description": "可选元数据：title、tags、source",
                        "properties": {
                            "title": {"type": "string"},
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "source": {"type": "string"},
                        },
                    },
                    "write_mode": {
                        "type": "string",
                        "enum": ["auto", "merge", "replace"],
                        "description": (
                            "auto（默认，已存在则合并）；merge；replace（覆盖正文）"
                        ),
                        "default": "auto",
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
            "name": "read_doc_meta",
            "description": "读取文档结构化元数据；读正文用 read_doc。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文档相对路径，如 技术/docker/常用命令.md",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_doc_meta",
            "description": (
                "更新文档元数据（title/tags/source）；不改正文。"
                "默认与现有字段合并；created/updated 由系统维护。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文档相对路径",
                    },
                    "meta": {
                        "type": "object",
                        "description": "要写入的字段（title/tags/source）",
                        "properties": {
                            "title": {"type": "string"},
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "source": {"type": "string"},
                        },
                    },
                    "merge": {
                        "type": "boolean",
                        "description": "默认 true，与现有元数据合并",
                        "default": True,
                    },
                },
                "required": ["path", "meta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_kb_file",
            "description": (
                "将文本类代码/配置文件写入知识库（.sh/.py/.js/.yaml 等），"
                "也支持矢量图 .svg（与 PNG/JPG 同为图片资产，可在聊天中预览；"
                "**SVG 固定写入 媒体/生成/{年月}/**，directory 可传该路径或任意占位）。"
                "禁止 .md（文档请用 write_doc）。不做 LLM 合并；已存在时须 overwrite=true 整文件覆盖。"
                "写入前应先 list_kb_structure 规划路径。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "文件全文（UTF-8 文本）",
                    },
                    "directory": {
                        "type": "string",
                        "description": _KB_DIRECTORY_DESC,
                    },
                    "filename": {
                        "type": "string",
                        "description": _KB_FILE_FILENAME_DESC,
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "目标已存在时是否整文件覆盖，默认 false",
                        "default": False,
                    },
                },
                "required": ["content", "directory", "filename"],
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
                "小范围修改优先于 write_doc。"
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
                "移动知识库中的文件（Markdown 或其它文件如 .pdf/.sh）"
                "或整个目录（如 Skill 包目录）。"
                "与侧栏拖放移动行为一致：目录移动时 to_filename 为新文件夹名（省略则用原目录名）；"
                "单文件移动时 to_filename 为目标文件名（省略则用原文件名）；"
                "Markdown 须以 .md 结尾；目标为 to_directory/filename。"
                "移动前建议 list_kb_structure；目标路径不得已存在。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_path": {
                        "type": "string",
                        "description": (
                            "当前相对路径：任意知识库文件，或目录（如 技能/张雪峰）"
                        ),
                    },
                    "to_directory": {
                        "type": "string",
                        "description": _KB_DIRECTORY_DESC,
                    },
                    "to_filename": {
                        "type": "string",
                        "description": (
                            "目标文件名或新目录名；省略时保留 from_path 最后一段名称"
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
    {
        "type": "function",
        "function": {
            "name": "sandbox_run",
            "description": (
                "在服务器持久沙箱中执行 shell 命令（工作目录默认 /workspace）。"
                "短命令同步返回；background=true 或长耗时会轮询直至结束，并流式上报进度。"
                "仅在实例启用执行能力时可用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "工作目录，默认 /workspace",
                        "default": "/workspace",
                    },
                    "background": {
                        "type": "boolean",
                        "description": "是否按后台 job 轮询（适合长任务）",
                        "default": False,
                    },
                    "timeout_sec": {
                        "type": "number",
                        "description": "同步执行超时秒数，默认 120",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": (
                            "用户已在 UI 确认执行后由系统续跑时置 true；"
                            "模型勿自行设为 true 以绕过确认"
                        ),
                        "default": False,
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_job_status",
            "description": (
                "查询此前 sandbox_run 返回的后台 execution_id 状态与日志（跨回合续查）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "execution_id": {
                        "type": "string",
                        "description": "sandbox_run 返回的 execution_id",
                    },
                },
                "required": ["execution_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_list_dir",
            "description": "列出沙箱内目录内容（默认 /workspace）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "绝对路径，默认 /workspace",
                        "default": "/workspace",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_read_file",
            "description": "读取沙箱内文本文件内容（有长度上限）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "沙箱内绝对路径，如 /workspace/旁白.md",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "最多返回字符数，默认 50000",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "publish_from_sandbox",
            "description": (
                "将沙箱 /workspace 下的文件显式发布到知识库。"
                "支持 Markdown、文本代码/配置、图片（.png/.jpg/.svg 等；图片会挂聊天附件预览），"
                "以及其它二进制产物（如 .mp4/.mp3/.bin 等成片与中间件）。"
                "**SVG 固定发布到 媒体/生成/{年月}/**（与生图同目录）。"
                "重型调用：多文件务必一次用 files 批量发布，勿逐文件反复调用。"
                "中间产物不要自动入库；仅最终旁白/分镜/成片等需要归档时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "description": (
                            "推荐；要发布的文件列表。"
                            "每项：sandbox_path + directory + filename"
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "sandbox_path": {
                                    "type": "string",
                                    "description": "沙箱绝对路径，必须在 /workspace 下",
                                },
                                "directory": {
                                    "type": "string",
                                    "description": _KB_DIRECTORY_DESC,
                                },
                                "filename": {
                                    "type": "string",
                                    "description": (
                                        "目标文件名；Markdown 用 .md，"
                                        "其它文件落在 directory/filename"
                                    ),
                                },
                            },
                            "required": ["sandbox_path", "directory", "filename"],
                        },
                    },
                    "sandbox_path": {
                        "type": "string",
                        "description": (
                            "单文件兼容；沙箱绝对路径，必须在 /workspace 下。"
                            "多文件请用 files"
                        ),
                    },
                    "directory": {
                        "type": "string",
                        "description": _KB_DIRECTORY_DESC,
                    },
                    "filename": {
                        "type": "string",
                        "description": (
                            "单文件兼容；目标文件名。"
                            "Markdown 用 .md，其它文件落在 directory/filename"
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stage_to_sandbox",
            "description": (
                "将知识库中的文件显式投放到沙箱 /workspace，便于 sandbox_run 执行。"
                "重型调用：多文件务必一次用 files 批量投放，勿逐文件反复调用。"
                "默认映射 kb_path → /workspace/{kb_path}；沙箱侧已存在则覆盖。"
                "权威副本仍在知识库；改完脚本应 write_kb_file(overwrite=true) 回写。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "description": (
                            "推荐；要投放的文件列表。"
                            "每项：kb_path，可选 sandbox_path"
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "kb_path": {
                                    "type": "string",
                                    "description": (
                                        "知识库相对路径，如 "
                                        "技能/hn-video-report/scripts/fetch_hn.py"
                                    ),
                                },
                                "sandbox_path": {
                                    "type": "string",
                                    "description": (
                                        "可选；沙箱绝对路径，须在 /workspace 下。"
                                        "省略则使用 /workspace/{kb_path}"
                                    ),
                                },
                            },
                            "required": ["kb_path"],
                        },
                    },
                    "kb_path": {
                        "type": "string",
                        "description": (
                            "单文件兼容；知识库相对路径。"
                            "多文件请用 files"
                        ),
                    },
                    "sandbox_path": {
                        "type": "string",
                        "description": (
                            "单文件兼容；沙箱绝对路径，须在 /workspace 下。"
                            "省略则使用 /workspace/{kb_path}"
                        ),
                    },
                },
                "required": [],
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
    imagegen_configured: bool = True,
    sandbox_enabled: bool = False,
    disclosure_windows: DisclosureWindows | None = None,
) -> list[dict]:
    """按 mode / 联网 / 沙箱能力硬门过滤下发给模型的工具集。

    - web_enabled=False 或未配置搜索 provider：移除 web_search（保留 fetch_url）。
    - 未配置生图 provider：移除 generate_image。
    - mode=no_write：移除 write_doc / write_kb_file / update_doc_meta / manage_memory / publish_from_sandbox / generate_image（保留 stage_to_sandbox）。
    - mode=force_write：保留 write_doc（/api/ingest 依赖 prompt 强制调用）。
    - sandbox_enabled=False：移除全部沙箱工具。
    - disclosure_windows：注入 read_doc / fetch_url 的实际窗口字数（与 Settings 一致）。

    /api/chat 使用 mode=default。ingest/ask 为测试与脚本同步 API，见
    docs/superpowers/specs/2026-07-12-ingest-ask-api-design.md
    """
    excluded: set[str] = set()
    if not web_enabled or not search_configured:
        excluded.add("web_search")
    if not imagegen_configured:
        excluded.add("generate_image")
    if mode == _MODE_NO_WRITE:
        excluded.add("write_doc")
        excluded.add("write_kb_file")
        excluded.add("update_doc_meta")
        excluded.add("manage_memory")
        excluded.add("publish_from_sandbox")
        excluded.add("generate_image")
    if not sandbox_enabled:
        excluded |= SANDBOX_TOOLS
    windows = disclosure_windows or DisclosureWindows()
    selected: list[dict] = []
    for d in TOOL_DEFINITIONS:
        name = d["function"]["name"]
        if name in excluded:
            continue
        if name in ("read_doc", "fetch_url"):
            selected.append(apply_disclosure_windows(d, windows))
        else:
            selected.append(d)
    return selected
