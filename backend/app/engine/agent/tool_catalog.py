from __future__ import annotations

import copy

from app.engine.disclosure import DisclosureWindows
from app.engine.knowledge_writer import KnowledgeWriter

resolve_kb_location = KnowledgeWriter.resolve_location

READ_ONLY_TOOLS = frozenset({
    "search_kb", "read_doc", "read_doc_meta", "list_kb_structure", "read_conversation_context",
    "fetch_url", "web_search",
    "recall_memory",
    "list_roles",
    "list_role_schedules",
    "sandbox_list_dir", "sandbox_read_file", "sandbox_job_status",
})
WRITE_TOOLS = frozenset({
    "write_doc", "write_kb_file", "delete_kb", "ask_user", "summarize_conversation",
    "edit_doc", "update_doc_meta",
    "manage_memory", "move_entry",
    "generate_image",
    "create_role",
    "update_role",
    "send_message",
    "create_role_schedule",
    "update_role_schedule",
    "delete_role_schedule",
    "finalize_role_onboarding",
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
    "list_roles": "列出角色",
    "create_role": "创建角色",
    "update_role": "更新角色",
    "list_role_schedules": "列出例行任务",
    "send_message": "发送给其他角色",
    "create_role_schedule": "创建例行任务",
    "update_role_schedule": "更新例行任务",
    "delete_role_schedule": "删除例行任务",
    "finalize_role_onboarding": "完成角色引导",
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
    "sandbox_stop",
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


_SCHEDULE_TIMING_PROP = {
    "type": "object",
    "description": (
        "定时规格（北京时间）。kind=interval 每隔 N 小时；"
        "hourly 每小时第 minute 分；daily 每天 HH:MM；"
        "weekdays 每个工作日；weekly 每周指定星期（0=周一…6=周日）；"
        "monthly 每月 day_of_month；cron 五段表达式（分 时 日 月 周，周 0/7=周日）。"
        "优先用 timing；仅间隔时可改传 interval_hours。"
    ),
    "properties": {
        "kind": {
            "type": "string",
            "enum": [
                "interval",
                "hourly",
                "daily",
                "weekdays",
                "weekly",
                "monthly",
                "cron",
            ],
        },
        "interval_hours": {
            "type": "number",
            "minimum": 0.5,
            "description": "kind=interval 时的间隔小时",
        },
        "hour": {"type": "integer", "minimum": 0, "maximum": 23},
        "minute": {"type": "integer", "minimum": 0, "maximum": 59},
        "weekdays": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 6},
            "description": "weekly：0=周一 … 6=周日",
        },
        "day_of_month": {"type": "integer", "minimum": 1, "maximum": 31},
        "cron": {"type": "string", "description": "五段 cron，按北京时间"},
    },
    "required": ["kind"],
}


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
                    "query": {
                        "type": "string",
                        "description": "检索问题或关键词；连续英文词按词 AND/OR（不要求彼此紧挨）；url/http 等格式词会忽略",
                    },
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
                    "role_id": {
                        "type": "string",
                        "description": "限定本角色的历史会话（默认取当前会话所属角色）；仅影响会话命中，不影响知识库",
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
                "列出知识库当前目录结构与各目录下的 Markdown / 文本代码文件名（只读；"
                "图片等二进制不在此列出，单目录文件名可能截断）。"
                "规划新路径（新建 write_doc / write_kb_file / summarize_conversation / "
                "publish_from_sandbox / generate_image 指定 kb 路径）或 move_entry 之前必须先调用本工具；"
                "并入已知文档、沿用已确认路径时不必为选路径再调。"
                "禁止凭记忆编造路径。"
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
            "description": "联网搜索，获取网页摘要。本轮已下发即表示可用，直接查询。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "k": {
                        "type": "integer",
                        "description": "返回条数；未指定时使用设置中的默认值",
                        "minimum": 1,
                        "maximum": 20,
                    },
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
                "默认 destination=chat_attachment，写入 媒体/生成/{年月}/；"
                "若需写入指定知识库路径供文档引用，用 destination=kb 并提供 directory 与 filename（均必填）。"
                "两种 destination 成功后都会在工具结果 attachments 中给出路径，信息流工具卡可内联预览。"
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
                            "可选弱覆盖：优先尝试该提供商 id 或类型（openai/zhipu/bailian/agnes/openrouter）；"
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
                "规划新路径时先 list_kb_structure；并入已知文档沿用已确认路径时不必再为选路径调用。"
                "可选 meta（title/tags/source）；"
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
                "规划新路径时应先 list_kb_structure；覆盖已确认路径时不必再为选路径调用。"
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
                "归档前应先 list_kb_structure 规划 directory 与 filename（归档是新路径）；必须指定二者。"
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
                "移动前须先 list_kb_structure；目标路径不得已存在。"
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
            "name": "list_roles",
            "description": (
                "列出当前实例中的角色目录，或按 id / 名称查看某一个角色的完整资料"
                "（名称、人设、头像、是否默认、引导状态、例行任务数量、是否忙碌）。"
                "问「有哪些角色 / 叫什么 / 某人设或资料」时必须先调用本工具，"
                "禁止凭印象编造角色名单或人设。"
                "创建新角色或 send_message 委托前，若不确定是否已有同名或同职责角色，先列出再决定。"
                "省略参数则返回全部角色；传入 role_id 或 name 则只返回匹配项。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "role_id": {
                        "type": "string",
                        "description": "角色 ID（可选；提供则只返回该角色的完整资料）",
                    },
                    "name": {
                        "type": "string",
                        "description": "角色显示名称（可选；提供则按名称查找，先精确再忽略大小写）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_role",
            "description": (
                "创建一个新的对话角色（工作台）。用于用户明确要求「新建角色 / 开一个某某助手」时；"
                "新角色共享知识库与主人记忆，拥有独立提示词与对话上下文。"
                "创建前若不确定是否已有同名或同职责角色，先调用 list_roles。"
                "创建后告知用户可在侧栏切换；不要替用户擅自大量建角色。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "角色显示名称，例如「股票研究员」",
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "该角色的叠加人设/职责提示词（可选）",
                        "default": "",
                    },
                    "avatar": {
                        "type": "string",
                        "description": (
                            "头像（可选）：知识库相对路径（与 generate_image 返回的 rel_path 相同）"
                            "或 http(s)/data URL。权威身份是路径或 URL 本身，不要改写成页面相对地址。"
                        ),
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_role",
            "description": (
                "更新角色的名称、头像或人设提示词。默认更新当前会话的角色；"
                "也可通过 role_id 指定其它角色。默认角色也可以改名称/头像/人设。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "role_id": {
                        "type": "string",
                        "description": "角色 ID（可选，默认为当前会话角色）",
                    },
                    "name": {
                        "type": "string",
                        "description": "新的角色名称（可选）",
                    },
                    "avatar": {
                        "type": "string",
                        "description": (
                            "新的头像（可选）：知识库相对路径（generate_image 的 rel_path）"
                            "或 http(s)/data URL。生图后应把 rel_path 传给本参数，不要只把图留在对话里。"
                        ),
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "新的人设/职责提示词（可选）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": (
                "向另一角色投递消息。对方会在协作房间收到入站消息并自动开回合工作；"
                "做完后对方应再 send_message 回执。"
                "这是投递，不是你变成对方。必须指定 to_role_id 或 to_role_name。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to_role_id": {
                        "type": "string",
                        "description": "目标角色 id（优先）",
                    },
                    "to_role_name": {
                        "type": "string",
                        "description": "目标角色显示名（与 id 二选一）",
                    },
                    "text": {
                        "type": "string",
                        "description": "要送达的完整委托或回执正文",
                    },
                    "expect_reply": {
                        "type": "boolean",
                        "description": "是否期待对方回执，默认 true",
                        "default": True,
                    },
                    "room_id": {
                        "type": "string",
                        "description": "已有协作房间 id；省略则按双方自动复用/创建",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_role_schedules",
            "description": "列出角色的定时任务。默认查询当前会话的角色。",
            "parameters": {
                "type": "object",
                "properties": {
                    "role_id": {
                        "type": "string",
                        "description": "角色 ID（可选，默认为当前会话角色）",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_role_schedule",
            "description": (
                "为角色创建例行任务：按 timing 在该角色活跃时间线插入提示词。"
                "支持每天/工作日/每周/每月指定时刻（北京时间），或间隔小时、cron。"
                "默认对当前会话角色操作。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "role_id": {
                        "type": "string",
                        "description": "角色 ID（可选，默认为当前会话角色）",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "定时触发的提示词内容",
                    },
                    "timing": _SCHEDULE_TIMING_PROP,
                    "interval_hours": {
                        "type": "number",
                        "description": "兼容：仅间隔触发时可用（小时，最小 0.5）",
                        "minimum": 0.5,
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": "是否启用（默认 true）",
                        "default": True,
                    },
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_role_schedule",
            "description": "更新现有例行任务的提示词、定时规格或启用状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {
                        "type": "string",
                        "description": "定时任务 ID",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "新的提示词（可选）",
                    },
                    "timing": _SCHEDULE_TIMING_PROP,
                    "interval_hours": {
                        "type": "number",
                        "description": "兼容：改为间隔小时（可选）",
                        "minimum": 0.5,
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": "启用/禁用（可选）",
                    },
                },
                "required": ["schedule_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_role_schedule",
            "description": "删除角色的例行任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {
                        "type": "string",
                        "description": "定时任务 ID",
                    },
                },
                "required": ["schedule_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_role_onboarding",
            "description": (
                "完成角色引导流程：写入最终的人设提示词，可选地创建例行任务，"
                "并将 onboarding_status 标记为 completed。"
                "仅在引导对话中、用户确认人设草稿后调用。默认对当前会话角色操作。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "role_id": {
                        "type": "string",
                        "description": "角色 ID（可选，默认为当前会话角色）",
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "最终确认的人设提示词（必填）",
                    },
                    "schedules": {
                        "type": "array",
                        "description": "可选的例行任务列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "prompt": {"type": "string"},
                                "timing": _SCHEDULE_TIMING_PROP,
                                "interval_hours": {"type": "number", "minimum": 0.5},
                                "enabled": {"type": "boolean", "default": True},
                            },
                            "required": ["prompt"],
                        },
                    },
                },
                "required": ["system_prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_run",
            "description": (
                "在该角色固定绑定的执行沙箱中跑 shell 命令"
                "（默认 cwd 为 /workspace/conversations/{当前会话}；"
                "定时任务为 /workspace/schedules/{schedule_id}；"
                "显式 cwd 须仍在 /workspace 下）。"
                "统一后台 job + 流式 poll；默认每 wait_sec 秒（60）检查点交还控制权。"
                "if_exceeded=return 时到期返回 checkpoint；wait_until_done 等到完成；"
                "stop 到期则 sandbox_stop 等价中断。"
                "续接已有任务传 execution_id（勿重复 command）。仅在实例启用执行能力时可用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令（新任务必填；续接时省略）",
                    },
                    "execution_id": {
                        "type": "string",
                        "description": "续接此前 sandbox_run 返回的后台任务 id",
                    },
                    "cwd": {
                        "type": "string",
                        "description": (
                            "工作目录，须在 /workspace 下。"
                            "省略时：交互回合用 /workspace/conversations/{conversation_id}，"
                            "定时任务用 /workspace/schedules/{schedule_id}"
                        ),
                    },
                    "wait_sec": {
                        "type": "number",
                        "description": "本段等待预算秒数，默认 60；到期按 if_exceeded 处理",
                        "default": 60,
                    },
                    "if_exceeded": {
                        "type": "string",
                        "enum": ["return", "wait_until_done", "stop"],
                        "description": (
                            "wait 预算用尽时：return=检查点交还 Agent；"
                            "wait_until_done=一直等到完成；stop=中断命令"
                        ),
                        "default": "return",
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
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sandbox_stop",
            "description": (
                "强制停止 sandbox_run 返回 execution_id 对应的后台命令，"
                "并流式刷出剩余日志。"
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
            "description": (
                "列出沙箱内目录内容（默认 /workspace）。"
                "路径以返回的 entries[].path 为准（每项一条）；"
                "summary 仅含条数，不要从 summary 拼路径。"
            ),
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
_MODE_API = "api"
_API_EXCLUDED_TOOLS = frozenset(
    {
        "write_doc",
        "edit_doc",
        "write_kb_file",
        "update_doc_meta",
        "summarize_conversation",
        "move_entry",
        "delete_kb",
        "publish_from_sandbox",
        "manage_memory",
        "generate_image",
        "create_role",
        "update_role",
        "create_role_schedule",
        "update_role_schedule",
        "delete_role_schedule",
        "finalize_role_onboarding",
        "send_message",
    }
)


def select_tools(
    mode: str,
    web_enabled: bool,
    *,
    search_configured: bool = True,
    imagegen_configured: bool = True,
    sandbox_enabled: bool = False,
    disclosure_windows: DisclosureWindows | None = None,
    role_messaging: bool = False,
) -> list[dict]:
    """按 mode / 联网 / 沙箱能力硬门过滤下发给模型的工具集。

    - web_enabled=False 或未配置搜索 provider：移除 web_search（保留 fetch_url）。
    - 未配置生图 provider：移除 generate_image。
    - mode=no_write：移除 write_doc / write_kb_file / update_doc_meta / manage_memory / publish_from_sandbox / generate_image（保留 stage_to_sandbox）。
    - mode=force_write：保留 write_doc（/api/ingest 依赖 prompt 强制调用）。
    - sandbox_enabled=False：移除全部沙箱工具。
    - disclosure_windows：注入 read_doc / fetch_url 的实际窗口字数（与 Settings 一致）。

    /api/chat 使用 mode=default。ingest/ask 为测试与脚本同步 API。
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
    if mode == _MODE_API:
        excluded |= _API_EXCLUDED_TOOLS
    if not sandbox_enabled:
        excluded |= SANDBOX_TOOLS
    if not role_messaging:
        excluded.add("send_message")
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
