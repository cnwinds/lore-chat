from __future__ import annotations

from app.models.llm import LLMClient

# 仅当《戒律》缺失/读取失败时的兜底；正常以 system_rules（《戒律》二）为准。
DEFAULT_SUMMARY_RULES = (
    "1. 总结对象是整段会话，先通读全部对话与依据再动笔。\n"
    "2. 全局重构、禁止流水线拼接：按主题而非发言/来源顺序组织；跨轮去重合并；"
    "禁止用单独一行的 Markdown 分隔线 --- 把多个一级标题硬堆在一起，全篇只有一套自洽的标题层级。\n"
    "3. 剥离对话痕迹（如「帮我记录」「用户说」），只留结论与事实。\n"
    "4. 保留可核验性：事实、数据、版本、链接等须有出处，不臆造、不补全。"
)

# 成文输出契约：系统元数据与正文结构块分离（根因：勿把正文 --- YAML 当「应剥掉的 frontmatter」）
_BODY_OUTPUT_CONTRACT = (
    "只输出正文 Markdown；不要输出知识库文档元数据头（由系统单独维护）；"
    "不要用代码围栏包裹全文。"
    "已有正文中的结构块（含以 --- 定界的 YAML 等）须原样保留，禁止剥掉或改写成普通段落。"
)



class DocumentSynthesis:
    """会话归档 / 多文档合并 / 入库合并的 LLM 成文 module。"""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def archive_transcript(self, transcript: str, system_rules: str = "") -> str:
        rules = system_rules.strip() or DEFAULT_SUMMARY_RULES
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库编辑，负责把一整段会话归档成一篇结构清晰、可长期查阅的文档。\n"
                    "务必遵守下列规约（尤其是会话总结/归档部分）：\n\n"
                    + rules
                ),
            },
            {
                "role": "user",
                "content": (
                    "以下是完整会话记录。请严格按上述规约通读全文后产出归档文档正文；"
                    f"{_BODY_OUTPUT_CONTRACT}\n\n"
                    f"=== 会话记录 ===\n{transcript}"
                ),
            },
        ]
        return self._chat_body(messages)

    def archive_segment(
        self, segment_text: str, system_rules: str, seg: dict
    ) -> str:
        rules = system_rules.strip() or DEFAULT_SUMMARY_RULES
        first_id = seg.get("first_message_id", "")
        last_id = seg.get("last_message_id", "")
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库编辑，负责把会话片段归档成结构化摘要。\n"
                    "务必遵守下列规约：\n\n" + rules
                ),
            },
            {
                "role": "user",
                "content": (
                    f"以下是会话片段（消息 {first_id} 至 {last_id}）。"
                    f"请产出该片段的摘要 Markdown。{_BODY_OUTPUT_CONTRACT}\n\n"
                    f"=== 片段 ===\n{segment_text}"
                ),
            },
        ]
        return self._chat_body(messages)

    def merge_archive_segments(
        self, partials: list[str], system_rules: str = ""
    ) -> str:
        rules = system_rules.strip() or DEFAULT_SUMMARY_RULES
        merged_input = "\n\n".join(
            f"=== 段摘要 {i + 1} ===\n{p}" for i, p in enumerate(partials)
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库编辑，负责把多段会话摘要归并为一篇完整归档文档。\n"
                    "务必遵守下列规约：\n\n" + rules
                ),
            },
            {
                "role": "user",
                "content": (
                    "以下是按时间顺序的各段摘要。请全局重构、去重合并为终稿 Markdown。"
                    f"{_BODY_OUTPUT_CONTRACT}\n\n"
                    f"{merged_input}"
                ),
            },
        ]
        return self._chat_body(messages)

    def reorganize_existing(
        self, existing_body: str, new_content: str, title: str
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库文档编辑。将已有文档与新内容合并，输出一份完整、结构清晰的 Markdown 正文。\n"
                    "要求：\n"
                    "1. 通读已有文档与新内容，按主题去重合并，禁止简单拼接（与会话总结规约一致）\n"
                    "2. 形成完整文档：标题层级合理、章节有序、信息不遗漏\n"
                    "3. 删除对话痕迹（如「帮我记录」「用户希望记录」等元叙述），保留事实\n"
                    "4. 若新内容修正或补充旧内容，以新内容为准\n"
                    f"5. {_BODY_OUTPUT_CONTRACT}"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"文档标题参考：{title}\n\n"
                    f"=== 已有文档 ===\n{existing_body}\n\n"
                    f"=== 待合并的新内容 ===\n{new_content}"
                ),
            },
        ]
        return self._chat_body(messages)

    def merge_documents(
        self, sources: list[tuple[str, str]], instruction: str = ""
    ) -> str:
        source_text = "\n\n".join(
            f"=== 文档 {path} ===\n{body}" for path, body in sources
        )
        user_instruction = instruction.strip() or "在不遗漏关键信息的前提下去重合并。"
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库编辑，负责把多篇文档合并成一篇可长期维护的 Markdown 文档。\n"
                    "要求：\n"
                    "1. 按主题重组内容，去重并消除冲突，优先保留更新且更完整的信息\n"
                    f"2. {_BODY_OUTPUT_CONTRACT}\n"
                    "3. 避免对话化语言，直接给出结构化知识内容"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"合并要求：{user_instruction}\n\n"
                    "请将以下文档合并成一篇：\n\n"
                    f"{source_text}"
                ),
            },
        ]
        return self._chat_body(messages)

    def _chat_body(self, messages: list[dict]) -> str:
        body = self.llm.chat(messages, big=True).strip()
        if not body.endswith("\n"):
            body += "\n"
        return body
