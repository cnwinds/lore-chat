"""记忆抽取 prompt 共用片段——单一来源，避免会话级/按条双份漂移。"""

from __future__ import annotations

import json
import re

# 「关于主人」门槛（AGENTS.md §0 / §2）；两边抽取器必须引用，禁止各写一份黑名单式补丁。
OWNER_MEMORY_GATE = """核心门槛（关于主人）：
- 只记主人自身的身份、偏好、跨会话仍成立的长期方向、工作方式、约束，或主人主动纳入画像的家庭/环境关系。
- 制度、常识、规格、考试规则、新闻、文档摘要等与主人无关的信息一律不记——即使对话里出现了数字或专有名词。
- 判定：删掉该句后主人画像是否变少？不变则不要输出。
- 禁止把常识改写成第一人称伪自述。"""

# 非耐久噪声（与「关于主人」正交：有主人指称也不该进长期画像的瞬时内容）
NON_DURABLE_IGNORE = """还必须忽略（非耐久 / 任务上下文）：
- 提问、命令、一次性任务、代码块、链接摘要
- 当前会话的任务拆解与交付要求；针对具体仓库/依赖/文件/接口的阶段性改动计划
- 仅在某课程/活动/项目阶段内成立的时间与精力安排；对助手方案的一次性改期或改范围指令
- 提示词/模板/填空示例（含占位符、填空说明）
- 无关第三方或虚构人物画像
- 不确定的猜测（除非 origin=inferred 且仍在描述主人）
- 耐久性判定：删掉该句后，跨会话仍成立的「主人是谁 / 怎么协作 / 长期方向」是否变少？若只影响本会话交付或某短期活动阶段，则不要输出。"""

# 语境保全（与归属、耐久性正交：禁止把情境事实剥成通项）
SCOPE_FIDELITY_GATE = """语境保全：
- 若事实的真值依赖特定活动、课程、项目、时段或对话中的具体方案，禁止写成无限定的通项。
- 判定：删掉限定语境后，这句话是否变成对主人的过度概括？若是，不得以通项形式输出。
- 若补全限定后事实仍只绑定短期活动阶段，按非耐久整条不记，而不是记一条带活动名的临时约束。
- 可借助手轮次消歧指代与限定，但画像 statement 只能来自主人立场，不得把助手陈述写成主人自述。"""

# 主人指称：须有第一人称/「我家」归属。裸「孩子/父母」不放行（常识句可夹带）。
# 语义判断（耐久性、语境保全、短指令是否属画像）交给抽取 prompt / LLM；
# 此处只做确定性表面过滤，避免无归属伪自述落入写入路径。
_OWNER_DEIXIS_RE = re.compile(r"(我|咱|本人|吾|俺|我家|我的|我们家)")


def passes_owner_surface_gate(statement: str) -> bool:
    """语句是否具备「关于主人」的表面归属（第一人称/家庭指称）。

    种子别名 / 抽象槽名不参与放行——不能证明语句关于主人。
    """
    text = (statement or "").strip()
    if not text:
        return False
    return bool(_OWNER_DEIXIS_RE.search(text))


class MemoryExtractParseError(ValueError):
    """LLM 抽取响应无法解析为约定 JSON（应保留 dirty 待重试）。"""


def parse_llm_json_list(raw: str, *, key: str) -> list[dict]:
    """解析抽取器 JSON 对象中的列表字段（items / candidates）。

    合法空数组 ``{"items":[]}`` 返回 ``[]``；缺对象/坏 JSON/缺列表字段则抛错。
    """
    text = (raw or "").strip()
    if not text:
        raise MemoryExtractParseError("empty LLM response")
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise MemoryExtractParseError("no JSON object in LLM response")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise MemoryExtractParseError("invalid JSON in LLM response") from exc
    if not isinstance(data, dict):
        raise MemoryExtractParseError("LLM JSON root must be an object")
    items = data.get(key)
    if not isinstance(items, list):
        raise MemoryExtractParseError(f"missing list field {key!r}")
    return [x for x in items if isinstance(x, dict)]
