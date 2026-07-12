# 联网搜索开关实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:executing-plans 或 superpowers:subagent-driven-development 逐任务实现。步骤用 `- [ ]` 跟踪。所有代码步骤遵循 TDD：先写失败测试 → 跑失败 → 实现 → 跑通过 → 提交。

**Goal:** 把"是否主动联网搜索"从 Agent 隐式决策变为用户显式开关；以硬门（过滤工具列表）实现，并顺带把 `mode` 也改为硬门过滤，消除 `no_write` 只靠 prompt 的既有隐患。不改 `/ingest`、`/ask` 端点去留。

**Spec:** [2026-07-12-web-search-toggle-design.md](../specs/2026-07-12-web-search-toggle-design.md)

**Tech Stack:** Python 3.11 / FastAPI / pytest；React + TypeScript + Vite。

**Architecture:** 后端先行（工具过滤为核心），前端后接（开关 UI + 透传）。后端内部按依赖顺序串行：`tools.select_tools` → orchestrator 透传 → prompts 语气 → routes 透传。

---

## 决策记录（实现前已定）

| 项 | 决策 |
|----|------|
| 开关粒度 | 布尔（开/关） |
| 开关语义 | 只控制 `web_search`；`fetch_url` 始终允许 |
| 文案 | 「联网搜索」 |
| 默认值 | 默认关 |
| 作用域 | 每次请求传参，前端 localStorage 记忆 |
| 融合 | 先本地，本地不足或需时效信息时再联网补充 |
| 工具过滤落点 | `tools.py` 新增 `select_tools(mode, web_enabled)` |
| `mode` 硬门 | 本计划一起做 |
| 抽象维度 | `web_enabled` 与 `mode` 正交 |

---

# 后端流

## Task B1: `tools.select_tools(mode, web_enabled)` 工具过滤

**问题:** orchestrator 每轮无条件下发全量 `TOOL_DEFINITIONS`；`mode` 与 `web_enabled` 均需硬门过滤。

**Files:**
- Modify: `backend/app/engine/agent/tools.py`
- Modify: `backend/app/engine/agent/prompts.py`（导入 mode 常量，避免循环依赖则用字符串）
- Test: `backend/tests/test_agent_tools.py`

- [ ] **Step 1: 写失败测试**

`test_agent_tools.py` 追加：

```python
from app.engine.agent.tools import select_tools
from app.engine.agent.prompts import MODE_DEFAULT, MODE_NO_WRITE, MODE_FORCE_WRITE


def _tool_names(defs):
    return {d["function"]["name"] for d in defs}


def test_select_tools_web_disabled_drops_web_search():
    names = _tool_names(select_tools(MODE_DEFAULT, web_enabled=False))
    assert "web_search" not in names
    assert "fetch_url" in names  # 贴链接始终允许


def test_select_tools_web_enabled_keeps_web_search():
    names = _tool_names(select_tools(MODE_DEFAULT, web_enabled=True))
    assert "web_search" in names


def test_select_tools_no_write_drops_write_kb():
    names = _tool_names(select_tools(MODE_NO_WRITE, web_enabled=True))
    assert "write_kb" not in names


def test_select_tools_force_write_keeps_write_kb():
    names = _tool_names(select_tools(MODE_FORCE_WRITE, web_enabled=True))
    assert "write_kb" in names
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_agent_tools.py -k select_tools -q
```

Expected: FAIL（ImportError: select_tools）

- [ ] **Step 3: 实现 `select_tools`（tools.py）**

在 `TOOL_DEFINITIONS` 之后追加。用字符串常量避免与 prompts 循环导入：

```python
_MODE_NO_WRITE = "no_write"


def select_tools(mode: str, web_enabled: bool) -> list[dict]:
    """按 mode 与 web_enabled 硬门过滤下发给模型的工具集。

    - web_enabled=False：移除 web_search（保留 fetch_url，贴链接=显式意图）。
    - mode=no_write：移除 write_kb（此前仅靠 prompt 约束，此处收紧为硬门）。
    """
    excluded: set[str] = set()
    if not web_enabled:
        excluded.add("web_search")
    if mode == _MODE_NO_WRITE:
        excluded.add("write_kb")
    return [d for d in TOOL_DEFINITIONS if d["function"]["name"] not in excluded]
```

- [ ] **Step 4: 跑通过**

```bash
cd backend && python -m pytest tests/test_agent_tools.py -k select_tools -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/agent/tools.py backend/tests/test_agent_tools.py
git commit -m "feat: select_tools hard-gates web_search and write_kb by mode/web_enabled"
```

---

## Task B2: orchestrator 透传 `web_enabled` 并用 `select_tools`

**Files:**
- Modify: `backend/app/engine/agent/orchestrator.py`
- Test: `backend/tests/test_agent_orchestrator.py`

- [ ] **Step 1: 写失败测试**

用 FakeLLM 断言下发工具集。参照 `test_agent_orchestrator.py` 现有夹具，捕获传入 `stream_chat_with_tools` 的 tool defs：

```python
@pytest.mark.asyncio
async def test_run_web_disabled_excludes_web_search(orchestrator_factory):
    orch, fake_llm = orchestrator_factory()  # 依现有夹具签名调整
    async for _ in orch.run("你好", web_enabled=False):
        pass
    names = {d["function"]["name"] for d in fake_llm.last_tools}
    assert "web_search" not in names
    assert "fetch_url" in names
```

若现有 FakeLLM 未记录 `last_tools`，在测试的 fake 内补一行 `self.last_tools = tools`。

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_agent_orchestrator.py -k web_disabled -q
```

Expected: FAIL（run() 无 web_enabled 参数 / 仍下发全量）

- [ ] **Step 3: 改 orchestrator**

`run()` 签名加 `web_enabled: bool = False`；工具下发改用 `select_tools`：

```python
    async def run(
        self,
        user_text: str,
        *,
        mode: str = MODE_DEFAULT,
        active_doc_path: str | None = None,
        history: list[dict] | None = None,
        conversation_id: str | None = None,
        web_enabled: bool = False,
    ) -> AsyncIterator[str]:
```

导入并计算一次工具集：

```python
from app.engine.agent.tools import select_tools  # 顶部已导入其他，追加

        tools_for_run = select_tools(mode, web_enabled)
```

替换下发处（orchestrator.py:119 附近）：

```python
            stream_iter = iter(
                self.llm.stream_chat_with_tools(
                    messages, tools_for_run, big=True
                )
            )
```

- [ ] **Step 4: 跑通过**

```bash
cd backend && python -m pytest tests/test_agent_orchestrator.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/agent/orchestrator.py backend/tests/test_agent_orchestrator.py
git commit -m "feat: orchestrator passes web_enabled and uses select_tools gating"
```

---

## Task B3: prompts 语气兜底（联网关时不得假装搜过）

**Files:**
- Modify: `backend/app/engine/agent/prompts.py`
- Test: `backend/tests/test_prompts.py`（若无则跳过测试，靠 B5 集成）

- [ ] **Step 1: `build_system_prompt` 增 `web_enabled` 影响的提示**

签名加 `web_enabled: bool = True`（注意：prompts 默认给 True 以免影响其他调用；实际关态由 orchestrator 传入）。在 suffix 组装处追加：

```python
def build_system_prompt(
    mode: str = MODE_DEFAULT,
    system_layer_text: str = "",
    web_enabled: bool = True,
) -> str:
    ...
    if not web_enabled:
        suffix += (
            "\n\n【联网】本轮未开启联网搜索，你没有 web_search 工具。"
            "可检索本地知识库、读取用户提供的链接（fetch_url）。"
            "若本地知识库无相关依据，如实说明「本地未找到，可开启联网搜索后重试」，"
            "禁止凭记忆补全或假装已联网。"
        )
```

- [ ] **Step 2: orchestrator 传 `web_enabled` 给 `build_system_prompt`**

orchestrator.py:99：

```python
            {"role": "system", "content": build_system_prompt(mode, system_layer_text, web_enabled)},
```

- [ ] **Step 3: 跑相关测试**

```bash
cd backend && python -m pytest tests/test_prompts.py tests/test_agent_orchestrator.py -q
```

Expected: PASS（无 test_prompts.py 则仅后者）

- [ ] **Step 4: Commit**

```bash
git add backend/app/engine/agent/prompts.py backend/app/engine/agent/orchestrator.py
git commit -m "feat: prompt reflects web_search availability, forbids faked web results"
```

---

## Task B4: `/chat` 端点透传 `web_enabled`

**Files:**
- Modify: `backend/app/api/routes.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: 写失败测试**

```python
def test_chat_web_disabled_by_default_no_web_search(client):
    # 默认关：即便问时效性问题，也不应出现 web_search 工具事件
    r = client.post("/api/chat", json={"text": "最新的 python 版本是多少"})
    assert r.status_code == 200
    events = _parse_sse_events(r.text)
    tools_called = [
        d.get("tool") for et, d in events if et == "tool_result"
    ]
    assert "web_search" not in tools_called
```

（依赖测试用 FakeLLM 的行为；若 FakeLLM 会主动请求 web_search，本测试正好验证硬门拦截。如 FakeLLM 从不调 web_search，此测试退化为"不回归"，仍保留。）

- [ ] **Step 2: 跑失败/基线**

```bash
cd backend && python -m pytest tests/test_api.py -k web_disabled -q
```

- [ ] **Step 3: `ChatBody` 加字段并透传**

```python
class ChatBody(BaseModel):
    text: str
    conversation_id: str | None = None
    active_doc_path: str | None = None
    web_enabled: bool = False
```

`/chat` 的 `c.agent.run(...)` 调用追加 `web_enabled=body.web_enabled`：

```python
            async for ev in c.agent.run(
                body.text,
                mode=MODE_DEFAULT,
                active_doc_path=body.active_doc_path,
                history=history,
                conversation_id=body.conversation_id,
                web_enabled=body.web_enabled,
            ):
```

- [ ] **Step 4: 跑通过**

```bash
cd backend && python -m pytest tests/test_api.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes.py backend/tests/test_api.py
git commit -m "feat: /chat accepts web_enabled flag (default off)"
```

---

## Task B5: 后端回归

- [ ] **Step 1:**

```bash
cd backend && python -m pytest -q
```

Expected: 全部 PASS。关注 `/ask`、`/ingest` 未受影响（它们不传 `web_enabled`，orchestrator 默认关；如 `_consume_agent_ask` 依赖 web_search 请评估——见下方风险）。

> **风险自检:** `_consume_agent_ask`（`/ask`）与 `_consume_agent_ingest`（`/ingest`）调用 `agent.run(...)` 未传 `web_enabled`，将默认关。若现有 `/ask` 测试期望联网补充，需在这两处显式传 `web_enabled=True` 以保持旧行为（端点重构前不改变对外语义）。实现时确认 `test_ingest_then_ask` 等仍通过；如失败，给 `/ask`、`/ingest` 的 `run()` 显式补 `web_enabled=True`。

---

# 前端流

## Task F1: `chatStream` 增加 `webEnabled` 参数

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: 扩展签名与请求体**

```typescript
export async function* chatStream(
  text: string,
  conversationId?: string | null,
  activeDocPath?: string | null,
  webEnabled = false,
): AsyncGenerator<ChatStreamEvent> {
  const r = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({
      text,
      conversation_id: conversationId ?? undefined,
      active_doc_path: activeDocPath ?? undefined,
      web_enabled: webEnabled,
    }),
  });
```

- [ ] **Step 2: 构建校验**

```bash
cd frontend && npm run build
```

Expected: 通过

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat: chatStream sends web_enabled flag"
```

---

## Task F2: Chat 界面「联网搜索」开关 + localStorage 记忆

**Files:**
- Modify: `frontend/src/components/Chat.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: 增加状态（默认关，读 localStorage）**

在其他 `useState` 附近：

```typescript
  const [webEnabled, setWebEnabled] = useState<boolean>(
    () => localStorage.getItem("lorechat.webSearch") === "1",
  );

  const toggleWebSearch = () => {
    setWebEnabled((prev) => {
      const next = !prev;
      localStorage.setItem("lorechat.webSearch", next ? "1" : "0");
      return next;
    });
  };
```

- [ ] **Step 2: 发送时传入**

`chatStream(apiText, cid, previewPath)` → 追加 `webEnabled`：

```typescript
      for await (const { event, data } of chatStream(apiText, cid, previewPath, webEnabled)) {
```

- [ ] **Step 3: 输入区加开关按钮**

在 `chat-input-actions` 内、发送按钮旁加一个可切换按钮（图标 🌐/闪电 + 高亮态）：

```tsx
          <button
            type="button"
            className={`chat-web-btn${webEnabled ? " chat-web-btn--on" : ""}`}
            onClick={toggleWebSearch}
            disabled={streaming}
            title={webEnabled ? "联网搜索：开（本地优先，联网补充）" : "联网搜索：关（仅本地知识库）"}
            aria-pressed={webEnabled}
          >
            🌐 联网
          </button>
```

- [ ] **Step 4: 样式（index.css）**

```css
.chat-web-btn {
  border: 1px solid var(--border, #d0d7de);
  background: transparent;
  color: var(--text-muted, #656d76);
  border-radius: 6px;
  padding: 0 10px;
  cursor: pointer;
}
.chat-web-btn--on {
  border-color: #1f883d;
  color: #1f883d;
  background: rgba(31, 136, 61, 0.08);
}
.chat-web-btn:disabled { opacity: 0.5; cursor: not-allowed; }
```

- [ ] **Step 5: 构建 + 手验**

```bash
cd frontend && npm run build
```

Expected: 通过；手动验证：默认关；点击切换高亮；刷新后保留；开态下问时效问题会触发 web_search，关态不触发。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Chat.tsx frontend/src/index.css
git commit -m "feat: web-search toggle in chat input with localStorage persistence"
```

---

## 验收自检

| Spec 验收项 | 对应 Task |
|------------|-----------|
| 默认关，`/chat` 无 web_search | B1/B4/F2 |
| 关时 fetch_url 仍可用 | B1 |
| 关时本地无依据如实告知、不编造 | B3 |
| 开时 web_search 可用、先本地后联网 | B1/B3/F2 |
| `no_write` 硬门去掉 write_kb | B1 |
| mode × web_enabled 正交 | B1/B2 |
| 前端默认关/切换生效/刷新保留 | F2 |
| `/chat`、`/ingest`、`/ask` 无回归 | B5 |
