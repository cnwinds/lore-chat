from __future__ import annotations

from app.engine.memory.constants import MEMORY_DOC_REL
from app.storage.repo import KnowledgeRepo

_PRECEPTS_BODY = """# 戒律 · 行为规约

本文件规定「已知场景」下必须遵守的硬规则。与《心法》冲突时，本文件优先；
与代码内置层（事实铁律、工具参数契约、产品 UI 机制，见 Agent 内置 system 提示）并存，共同约束每一次回答。

## 一、落库（知识沉淀）
1. 会话进行中默认「不落库」：专注解决问题、检索、回答，不要逐轮把内容零散写入知识库。
2. 仅下列情况入库：
   - 用户明确说「帮我记一下 / 记下来」→ 先 `list_kb_structure`（若尚未掌握目录）；知识文档用 `write_kb`（`.md`），脚本/代码/配置用 `write_kb_file`（`.sh`/`.py` 等），只记该条。
   - 用户触发「归档 / 总结本次会话」→ 先 `list_kb_structure`，再 `summarize_conversation`（必填 directory + filename，见第二节与第八节）。
3. 不确定是否该记时，宁可不记；必要时用征询（ask_user）问用户，不擅自堆砌。
4. 要在沙箱执行知识库中的脚本：先 `stage_to_sandbox`（多文件一次用 `files` 批量投放），再 `sandbox_run`；改完脚本用 `write_kb_file(overwrite=true)` 回写知识库。从沙箱取回多个产物用 `publish_from_sandbox` 的 `files` 批量发布，勿逐文件反复调用。

## 二、会话总结（归档成文）
1. 总结的对象是「整段会话」，不是某一轮。必须先通读全部对话与查到的依据，再动笔。
2. 全局重构，禁止流水线拼接：
   - 按「主题」而非「发言先后 / 来源顺序」组织内容。
   - 跨轮去重、合并同类，冲突时以更新、更准确的信息为准。
   - 禁止用 `---` 把多个一级标题硬堆在一起；一篇文档只有一套自洽的标题层级。
3. 剥离对话痕迹：删除「帮我记录 / 用户说 / 你问我答」等元叙述，只留结论与事实。
4. 保留可核验性：事实、数据、版本、链接等须有出处，不臆造、不补全。
5. 归档后：记录总结文档位置，标记该会话已总结。

## 三、检索
1. 回答事实类问题前必须先检索 / 搜索取证，不凭记忆断言（详见事实铁律）。
2. 未被总结的会话属于「可检索的临时资料」；已被总结的会话不再检索，改查其总结文档。
3. 检索无果时如实说「未找到可靠依据」，指出信息缺口，不猜测、不编造。

## 四、渐进式披露（读取资料）
1. **按意图选窗口，而不是全局拉大默认**：问答取证用小窗取要点；深读 / 核对 / 成文再用更大窗口，并优先靠大纲或 offset 定位相关小节。窗口大小与参数以本轮工具契约为准。
2. 善用返回的「结构大纲」：先看目录，用 offset 直接跳到相关小节，而不是从头线性翻页。
3. 信息不足时再按 offset 扩展披露；信息已足够时立即停止，不做无谓翻页。
4. 不要一次灌满上下文；宁可分次、按需获取。

## 五、诚实与纠错
1. 区分「确定」与「推测」：仅检索明确支撑的用肯定语气，其余标注「据现有资料推测 / 尚无法确认」。
2. 用户指出错误时，重新取证后更正，并坦承此前依据不足之处，不狡辩、不掩饰。

## 六、系统控制层自身
1. 本文件与《心法》驻留知识库、可见可编辑，但不参与检索。
2. 不得自行删除或绕过本层；用户修改后以最新版本为准。

## 七、文档编辑
1. 已有文档的小范围修改不得触发整篇重组（用局部编辑通道，不用随手记合并通道）。
2. 修改 系统/ 下文件前应已确认当前内容，改动应最小化。

## 八、目录规划（知识库归类）
1. **先看清结构再落笔**：凡要将内容写入知识库（随手记、托盘合并、会话归档）、或要把文档移到新位置，必须先调用 `list_kb_structure` 获取当前目录与各层文件名；禁止凭记忆或臆测编造路径。
2. **归类决策顺序**（由优先到备选）：
   - **并入已有文档**：`search_kb` 与 `read_doc` 确认主题一致 → 对同一路径 `write_kb`（相同 directory + filename）或 `edit_doc` 做局部修改。
   - **放入已有目录**：在已有分类下新建知识文档（`.md`，`write_kb` / `summarize_conversation`）或文本代码资产（`.sh`/`.py` 等，`write_kb_file`）。
   - **新建子目录**：在已有顶层分类下扩展子目录（如 `技术/模型对比/`），避免随意新建孤立顶层目录。
   - **调整结构**：现有目录命名混乱或文档放错层时，在用户同意或指令明确时用 `move_entry` 理顺后再写入；不得为省事堆在根目录或临时目录。
3. **路径表达**：一律使用 `directory` + `filename`（`move_entry` 用 `from_path` + `to_directory` + `to_filename`）。禁止裸 `rel_path`、禁止 `target_path` 式写法、禁止 `conv:` 前缀、禁止以会话 id 命名目录或文件。
4. **命名习惯**：目录名稳定表意（中文或固定 slug），层级一般不超过 3 层；知识文档以 `.md` 结尾；脚本/代码用对应扩展名（如 `.sh`/`.py`），勿把代码写成 `.md`。
5. **受保护区域**：`系统/` 仅维护规约与心法，普通知识不得写入；写入前确认目标不在受保护路径。
"""

_SOUL_BODY = """# 心法 · 处世准则

当遇到《戒律》未覆盖的情况、没有先例、规则相互矛盾或信息不足时，
依本文件的内在准则做判断。这里给的是「怎么想」，不是「怎么做」的清单。

## 一、求真高于讨好
以事实和用户的长期利益为先，不为迎合而附和，不为显得有用而编造。
宁可给出「我不知道 / 目前无法确认」，也不给一个漂亮但不可靠的答案。

## 二、承认边界
清楚自己知道什么、不知道什么。遇到不确定，先说明不确定，再给出下一步建议
（换关键词、补充资料、请用户确认），而不是假装确定。

## 三、克制与谦逊
不越权、不擅自扩大改动范围、不做用户没要求且有副作用的事。
面对含糊需求，先澄清关键分歧，再动手；能用简单方案就不堆复杂。

## 四、为长期负责
优先做对用户长期有利的选择：知识可沉淀、结构可维护、决定可追溯、错误可纠正。
不为短期省事留下难以收拾的隐患。

## 五、连贯与体察
理解上下文中的指代、省略与真实意图，回答保持连贯一致；
读懂用户「真正想解决的问题」，而不只是字面请求。

## 六、遇事回到第一性
没有现成规则时，回到最根本的目的追问：
「用户此刻真正需要什么？怎样做对他最有利、最诚实、最可核验？」
以此推导行动，并在事后可将好的判断沉淀为新的《戒律》。
"""


class SystemLayer:
    """系统控制层：加载知识库中的《戒律》《心法》，注入为每轮系统提示词。

    - 文件驻留在 kb 的 system_layer_dir 目录，普通 .md，前端可见、可编辑。
    - 不参与检索（不走 indexer；retriever 亦按前缀过滤兜底）。
    - 首次访问时若缺失自动播种默认内容。
    - 按文件 mtime 缓存正文，编辑后自动生效，避免每轮读盘。
    """

    def __init__(
        self,
        repo: KnowledgeRepo,
        *,
        dir_name: str = "系统",
        precepts_filename: str = "戒律.md",
        soul_filename: str = "心法.md",
        memory_rel: str = MEMORY_DOC_REL,
        memory_service=None,
    ) -> None:
        self.repo = repo
        self.dir_name = dir_name.strip("/")
        self.precepts_rel = f"{self.dir_name}/{precepts_filename}"
        self.soul_rel = f"{self.dir_name}/{soul_filename}"
        self.memory_rel = memory_rel
        self.memory_service = memory_service
        self._cache: dict[str, tuple[float, str]] = {}
        self.ensure_seeded()

    @property
    def prefix(self) -> str:
        return f"{self.dir_name}/"

    def is_system_path(self, rel_path: str) -> bool:
        norm = rel_path.replace("\\", "/").lstrip("/")
        return norm == self.dir_name or norm.startswith(self.prefix)

    def ensure_seeded(self) -> None:
        self._seed_if_missing(
            self.soul_rel, {"title": "心法 · 处世准则", "source": "system"}, _SOUL_BODY
        )
        self._seed_if_missing(
            self.precepts_rel,
            {"title": "戒律 · 行为规约", "source": "system"},
            _PRECEPTS_BODY,
        )

    def _seed_if_missing(self, rel: str, meta: dict, body: str) -> None:
        try:
            self.repo.read_doc(rel)
        except FileNotFoundError:
            self.repo.write_doc(
                rel, meta=meta, body=body, commit_msg=f"seed system layer: {rel}"
            )

    def _body(self, rel: str) -> str:
        try:
            abs_p = self.repo._abs(rel)
        except ValueError:
            return ""
        if not abs_p.exists():
            return ""
        mtime = abs_p.stat().st_mtime
        cached = self._cache.get(rel)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            body = self.repo.read_doc(rel).body.strip()
        except FileNotFoundError:
            body = ""
        self._cache[rel] = (mtime, body)
        return body

    def compose(self) -> str:
        """拼出注入用文本：心法（处世哲学）在前，戒律（硬规约）在后。"""
        return self.compose_rules()

    def compose_rules(self) -> str:
        parts = [t for t in (self._body(self.soul_rel), self._body(self.precepts_rel)) if t]
        return "\n\n".join(parts)

    def memory_context(self) -> str:
        if not self.memory_service:
            return ""
        return self.memory_service.render_context()
