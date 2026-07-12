# Agent 局部文档编辑（edit_doc）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Agent 新增 `edit_doc` 工具（search/replace 局部修改），并同期实现向量增量重索引，避免大文档小改时全量 embed。

**Architecture:** `engine/patch.py`（含 `affected_start/end`）→ `edit_doc` + read guard → `indexer.reindex_doc_after_edit`（向量 tail 重嵌 + FTS 全量）。不经 Organizer。Phase 1 = `edits` + 增量重索引；`insert` 留 Phase 2。

**设计文档:** [2026-07-12-partial-doc-edit-design.md](../specs/2026-07-12-partial-doc-edit-design.md)（复审修订版）

**前置:** architecture-fixes 已实施（结构化 tool result、KB_MUTATING_TOOLS、logging 等）。

---

## 关键契约（跨任务共享，命名必须一致）

```python
# app/engine/patch.py
@dataclass
class PatchResult:
    ok: bool
    body: str | None
    applied: int
    message: str
    error: PatchError | None = None
    preview: str | None = None
    affected_start: int | None = None   # 原文坐标，供增量重索引
    affected_end: int | None = None

# app/index/indexer.py
def reindex_doc_after_edit(
    self, doc_id: str, old_body: str, new_body: str,
    affected_start: int | None, affected_end: int | None,
) -> str: ...  # 返回 "partial" | "full"

# app/config.py
edit_doc_max_edits: int = 10
edit_doc_max_patch_chars: int = 8192
edit_doc_require_read: bool = True
reindex_full_threshold: int = 4000

# edit_doc tool result（结构化，禁止从 summary 解析）
# 成功: status="saved", applied, preview, reindex_mode
# 失败: status="failed", error="NOT_READ"|"AMBIGUOUS"|...
```

---

## 复审增补（2026-07-12，相对原计划的变化）

1. **§9.2 《戒律》** 只加 2 条策略（§七），API 细节放 Tool + SYSTEM_PROMPT。
2. **SYSTEM_PROMPT §7** 小改 → `edit_doc`；语义融合 → `write_kb`+`target_path`。
3. **新增 Task 3.5** 增量重索引（`chunk_starts`、`vector.delete_ids`、`reindex_doc_after_edit`）。
4. **前端** 仅在 `KB_MUTATING_TOOLS` 加 `"edit_doc"`（F1 已集中常量，不必改 Chat if 链）。
5. **patch** 必须跟踪并返回 `affected_start/end`。

---

## 文件结构

```
backend/app/
  config.py                         # 修改：edit_doc_* 配置
  deps.py                           # 修改：ToolRegistry 传入 settings
  engine/
    patch.py                        # 新建：匹配与应用引擎
    agent/
      tools.py                      # 修改：edit_doc + read guard
      prompts.py                    # 修改：工具说明与分工
      system_layer.py               # 修改：戒律新增「文档编辑策略」
backend/tests/
  test_patch.py                     # 新建
  test_agent_tools.py               # 修改：edit_doc 集成测试
  test_config.py                    # 修改：默认值冒烟
frontend/src/
  components/Chat.tsx               # 修改：edit_doc 触发 onKbChanged
```

---

## Task 1: 配置项

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: 在 Settings 末尾添加**

```python
    # edit_doc 局部编辑
    edit_doc_max_edits: int = 10
    edit_doc_max_patch_chars: int = 8192
    edit_doc_require_read: bool = True
    reindex_full_threshold: int = 4000
```

- [ ] **Step 2: 更新 `.env.example`**

```env
# edit_doc 局部编辑
EDIT_DOC_MAX_EDITS=10
EDIT_DOC_MAX_PATCH_CHARS=8192
EDIT_DOC_REQUIRE_READ=true
REINDEX_FULL_THRESHOLD=4000
```

- [ ] **Step 3: 扩展 `test_config.py`**

在 `test_settings_defaults` 末尾追加：

```python
    assert s.edit_doc_max_edits == 10
    assert s.edit_doc_max_patch_chars == 8192
    assert s.edit_doc_require_read is True
    assert s.reindex_full_threshold == 4000
```

- [ ] **Step 4: 运行测试**

```bash
cd backend && python -m pytest tests/test_config.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/.env.example backend/tests/test_config.py
git commit -m "feat: add edit_doc configuration settings"
```

---

## Task 2: patch 引擎 — 精确替换

**Files:**
- Create: `backend/app/engine/patch.py`
- Test: `backend/tests/test_patch.py`

- [ ] **Step 1: 写失败测试（精确替换 + NOT_FOUND + AMBIGUOUS）**

创建 `backend/tests/test_patch.py`：

```python
import pytest

from app.engine.patch import Edit, PatchError, apply_edits


def test_apply_edits_single_replace():
    body = "alpha\nbeta\ngamma\n"
    result = apply_edits(body, [Edit(old_string="beta\n", new_string="BETA\n")], max_patch_chars=8192)
    assert result.ok is True
    assert result.body == "alpha\nBETA\ngamma\n"
    assert result.applied == 1


def test_apply_edits_not_found():
    result = apply_edits("hello\n", [Edit(old_string="missing", new_string="x")], max_patch_chars=8192)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "NOT_FOUND"


def test_apply_edits_ambiguous():
    body = "foo bar\nfoo bar\n"
    result = apply_edits(
        body,
        [Edit(old_string="foo", new_string="baz")],
        max_patch_chars=8192,
    )
    assert result.ok is False
    assert result.error.code == "AMBIGUOUS"
    assert len(result.error.occurrences or []) == 2


def test_apply_edits_replace_all():
    body = "foo bar\nfoo bar\n"
    result = apply_edits(
        body,
        [Edit(old_string="foo", new_string="baz", replace_all=True)],
        max_patch_chars=8192,
    )
    assert result.ok is True
    assert result.body == "baz bar\nbaz bar\n"
    assert result.applied == 1


def test_apply_edits_delete_with_empty_new_string():
    body = "keep\nremove me\nkeep\n"
    result = apply_edits(
        body,
        [Edit(old_string="remove me\n", new_string="")],
        max_patch_chars=8192,
    )
    assert result.ok is True
    assert result.body == "keep\nkeep\n"


def test_apply_edits_too_large():
    big = "x" * 9000
    result = apply_edits("ok\n", [Edit(old_string="ok", new_string=big)], max_patch_chars=8192)
    assert result.ok is False
    assert result.error.code == "TOO_LARGE"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_patch.py -v
```

Expected: FAIL `ModuleNotFoundError: app.engine.patch`

- [ ] **Step 3: 实现 `patch.py`（Pass 1 精确匹配）**

创建 `backend/app/engine/patch.py`：

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Edit:
    old_string: str
    new_string: str
    replace_all: bool = False


@dataclass
class PatchError:
    code: str
    message: str
    hint: str | None = None
    occurrences: list[dict] | None = None
    suggestion: str | None = None


@dataclass
class PatchResult:
    ok: bool
    body: str | None
    applied: int
    message: str
    error: PatchError | None = None
    preview: str | None = None


def _context_snippet(body: str, start: int, length: int, *, radius: int = 50) -> str:
    lo = max(0, start - radius)
    hi = min(len(body), start + length + radius)
    return body[lo:hi]


def _find_exact(body: str, needle: str) -> list[int]:
    if not needle:
        return []
    out: list[int] = []
    i = 0
    while True:
        j = body.find(needle, i)
        if j < 0:
            break
        out.append(j)
        i = j + 1
    return out


def _fail_not_found(body: str, needle: str) -> PatchResult:
    return PatchResult(
        ok=False,
        body=None,
        applied=0,
        message="old_string 在文档中未找到",
        error=PatchError(
            code="NOT_FOUND",
            message="old_string 在文档中未找到",
            hint=_context_snippet(body, 0, min(len(needle), len(body))),
            suggestion="请用 read_doc 重新读取后复制精确文本",
        ),
    )


def _fail_ambiguous(body: str, needle: str, positions: list[int]) -> PatchResult:
    return PatchResult(
        ok=False,
        body=None,
        applied=0,
        message=f"old_string 在文档中出现 {len(positions)} 次",
        error=PatchError(
            code="AMBIGUOUS",
            message=f"old_string 在文档中出现 {len(positions)} 次",
            occurrences=[
                {
                    "offset": pos,
                    "context": _context_snippet(body, pos, len(needle)),
                }
                for pos in positions
            ],
            suggestion="请扩大 old_string 范围，包含更多唯一上下文",
        ),
    )


def _make_preview(body: str, start: int, old_len: int, new_len: int) -> str:
    return _context_snippet(body, start, max(old_len, new_len), radius=80)


def apply_edits(body: str, edits: list[Edit], *, max_patch_chars: int) -> PatchResult:
    if not edits:
        return PatchResult(
            ok=False,
            body=None,
            applied=0,
            message="edits 不能为空",
            error=PatchError(code="INVALID", message="edits 不能为空"),
        )

    current = body
    applied = 0
    last_preview: str | None = None

    for edit in edits:
        if len(edit.old_string) > max_patch_chars or len(edit.new_string) > max_patch_chars:
            return PatchResult(
                ok=False,
                body=None,
                applied=applied,
                message="单段 old_string 或 new_string 超出长度限制",
                error=PatchError(
                    code="TOO_LARGE",
                    message="单段 old_string 或 new_string 超出长度限制",
                ),
            )

        positions = _find_exact(current, edit.old_string)
        if not positions:
            return _fail_not_found(current, edit.old_string)

        if len(positions) > 1 and not edit.replace_all:
            return _fail_ambiguous(current, edit.old_string, positions)

        if edit.replace_all:
            current = current.replace(edit.old_string, edit.new_string)
            last_preview = _make_preview(
                current, 0, len(edit.old_string), len(edit.new_string)
            )
        else:
            pos = positions[0]
            current = current[:pos] + edit.new_string + current[pos + len(edit.old_string) :]
            last_preview = _make_preview(
                current, pos, len(edit.old_string), len(edit.new_string)
            )
        applied += 1

    delta = len(current) - len(body)
    sign = f"+{delta}" if delta >= 0 else str(delta)
    return PatchResult(
        ok=True,
        body=current,
        applied=applied,
        message=f"已应用 {applied} 处修改（{sign} 字）",
        preview=last_preview,
    )
```

- [ ] **Step 4: 运行测试**

```bash
cd backend && python -m pytest tests/test_patch.py -v
```

Expected: PASS（6 tests）

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/patch.py backend/tests/test_patch.py
git commit -m "feat: add patch engine with exact-match edits"
```

---

## Task 3: patch 引擎 — 换行归一化与多 edits

**Files:**
- Modify: `backend/app/engine/patch.py`
- Modify: `backend/tests/test_patch.py`

- [ ] **Step 1: 追加失败测试**

在 `test_patch.py` 末尾添加：

```python
def test_apply_edits_newline_normalized():
    body = "line1\r\nline2\r\n"
    result = apply_edits(
        body,
        [Edit(old_string="line1\nline2\n", new_string="LINE1\nLINE2\n")],
        max_patch_chars=8192,
    )
    assert result.ok is True
    assert "LINE1" in result.body
    assert "LINE2" in result.body


def test_apply_edits_sequential_multiple():
    body = "aaa\nbbb\nccc\n"
    result = apply_edits(
        body,
        [
            Edit(old_string="aaa\n", new_string="AAA\n"),
            Edit(old_string="ccc\n", new_string="CCC\n"),
        ],
        max_patch_chars=8192,
    )
    assert result.ok is True
    assert result.body == "AAA\nbbb\nCCC\n"
    assert result.applied == 2
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_patch.py::test_apply_edits_newline_normalized -v
```

Expected: FAIL（NOT_FOUND）

- [ ] **Step 3: 在 `patch.py` 添加归一化匹配**

在 `_find_exact` 之后添加：

```python
def _normalize_newlines(s: str) -> str:
    return s.replace("\r\n", "\n").replace("\r", "\n")


def _build_norm_index_map(body: str) -> tuple[str, list[int]]:
    """归一化换行并记录 norm 下标 → 原文起始下标。"""
    norm_chars: list[str] = []
    norm_to_orig: list[int] = []
    i = 0
    while i < len(body):
        if body.startswith("\r\n", i):
            norm_chars.append("\n")
            norm_to_orig.append(i)
            i += 2
        elif body[i] == "\r":
            norm_chars.append("\n")
            norm_to_orig.append(i)
            i += 1
        else:
            norm_chars.append(body[i])
            norm_to_orig.append(i)
            i += 1
    return "".join(norm_chars), norm_to_orig


def _orig_span_for_norm_match(
    body: str, norm_body: str, norm_to_orig: list[int], norm_start: int, norm_needle: str
) -> tuple[int, int] | None:
  """将归一化匹配映射回原文 [start, end) 跨度。"""
    norm_end = norm_start + len(norm_needle)
    if norm_end > len(norm_body):
        return None
    orig_start = norm_to_orig[norm_start]
    # 从 orig_start 向后扩展，直到归一化后与 norm 片段一致
    for orig_end in range(orig_start + 1, len(body) + 1):
        if _normalize_newlines(body[orig_start:orig_end]) == norm_needle:
            return orig_start, orig_end
    return None


def _find_with_fallback(body: str, needle: str) -> list[tuple[int, int]]:
    """返回原文中的 (start, end) 跨度列表。"""
    exact = _find_exact(body, needle)
    if exact:
        n = len(needle)
        return [(pos, pos + n) for pos in exact]

    norm_body, norm_to_orig = _build_norm_index_map(body)
    norm_needle = _normalize_newlines(needle)
    if not norm_needle:
        return []

    spans: list[tuple[int, int]] = []
    i = 0
    while True:
        j = norm_body.find(norm_needle, i)
        if j < 0:
            break
        mapped = _orig_span_for_norm_match(body, norm_body, norm_to_orig, j, norm_needle)
        if mapped:
            spans.append(mapped)
        i = j + 1
    return spans
```

将 `apply_edits` 内 `positions = _find_exact(...)` 替换为：

```python
        spans = _find_with_fallback(current, edit.old_string)
        if not spans:
            return _fail_not_found(current, edit.old_string)

        if len(spans) > 1 and not edit.replace_all:
            positions = [s[0] for s in spans]
            return _fail_ambiguous(current, edit.old_string, positions)

        if edit.replace_all:
            # 从后往前替换，避免偏移错乱
            for start, end in reversed(spans):
                current = current[:start] + edit.new_string + current[end:]
            last_preview = _make_preview(
                current, spans[0][0], spans[0][1] - spans[0][0], len(edit.new_string)
            )
        else:
            start, end = spans[0]
            current = current[:start] + edit.new_string + current[end:]
            last_preview = _make_preview(
                current, start, end - start, len(edit.new_string)
            )
```

- [ ] **Step 4: 运行全部 patch 测试**

```bash
cd backend && python -m pytest tests/test_patch.py -v
```

Expected: PASS（8 tests）

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/patch.py backend/tests/test_patch.py
git commit -m "feat: patch engine newline fallback and multi-edit support"
```

---

## Task 3.5: 增量重索引（向量 tail + FTS 全量）

**Files:**
- Modify: `backend/app/index/chunk.py`
- Modify: `backend/app/index/vector.py`
- Modify: `backend/app/index/indexer.py`
- Modify: `backend/app/deps.py`（Indexer 传入 `reindex_full_threshold`）
- Test: `backend/tests/test_indexer.py`

- [ ] **Step 1: `chunk.py` 新增 `chunk_starts`**

与 `chunk_text(size=800, overlap=100)` 使用相同步长逻辑，返回每个 chunk 在原文中的起始偏移列表。

- [ ] **Step 2: `vector.py` 新增 `delete_ids(ids: list[str])`**

按 id 列表删除（Chroma collection.delete(ids=...)），空列表 no-op。

- [ ] **Step 3: `indexer.py` 实现 `reindex_doc_after_edit`**

按设计文档 §6.5.1：
- 回退条件 → `reindex_doc` 返回 `"full"`
- 否则计算 `first_idx`，`delete_ids` tail，`embed` tail chunks，FTS 全量重建
- 返回 `"partial"`

构造函数增加 `reindex_full_threshold: int = 4000`。

- [ ] **Step 4: 写测试 `test_indexer.py`**

- 大文档中间小编辑 → embed 调用次数 < 全量 chunk 数（用 FakeLLMClient 计数）
- 小文档 → `"full"` 路径
- 编辑后 search 能命中新内容

- [ ] **Step 5: pytest tests/test_indexer.py -q**

- [ ] **Step 6: Commit**

```bash
git add backend/app/index/chunk.py backend/app/index/vector.py backend/app/index/indexer.py backend/app/deps.py backend/tests/test_indexer.py
git commit -m "feat: partial vector reindex after doc edit"
```

**Task 2–3 补充：** `apply_edits` 成功时必须设置 `affected_start`/`affected_end`（合并所有 edit 在原文中的最小覆盖区间；每步 apply 前在 current 上定位，映射回初始 body 坐标或在一开始 body 上预先找齐所有 spans 再顺序替换）。

---

## Task 4: ToolRegistry — edit_doc 与 read guard

**Files:**
- Modify: `backend/app/engine/agent/tools.py`
- Modify: `backend/app/deps.py`
- Test: `backend/tests/test_agent_tools.py`

- [ ] **Step 1: 写失败集成测试**

在 `test_agent_tools.py` 中：

1. 更新 `test_can_parallelize_read_only`：

```python
    assert can_parallelize(["search_kb", "edit_doc"]) is False
```

2. 更新 `_make_registry` 签名，传入 settings：

```python
def _make_registry(tmp_path, chat_responses=None, **settings_kw):
    ...
    settings = Settings(kb_path=tmp_path / "knowledge", **settings_kw)
    ...
    registry = ToolRegistry(
        retr, repo, org, fetcher, web_search, pending,
        indexer=idx,
        edit_doc_max_edits=settings.edit_doc_max_edits,
        edit_doc_max_patch_chars=settings.edit_doc_max_patch_chars,
        edit_doc_require_read=settings.edit_doc_require_read,
    )
```

3. 追加测试：

```python
@pytest.mark.asyncio
async def test_edit_doc_requires_read_first(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    repo.write_doc("技术/foo.md", {"title": "Foo"}, "hello world\n", commit_msg="seed")
    cid = "conv-1"
    result = await registry.execute(
        "edit_doc",
        {"path": "技术/foo.md", "edits": [{"old_string": "world", "new_string": "earth"}]},
        conversation_id=cid,
    )
    assert result.get("error") == "NOT_READ"
    assert "read_doc" in (result.get("suggestion") or "")


@pytest.mark.asyncio
async def test_edit_doc_after_read(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    path = "技术/foo.md"
    repo.write_doc(path, {"title": "Foo"}, "hello world\n", commit_msg="seed")
    idx.reindex_doc(path, "hello world\n")
    cid = "conv-2"
    await registry.execute("read_doc", {"path": path}, conversation_id=cid)
    result = await registry.execute(
        "edit_doc",
        {"path": path, "edits": [{"old_string": "world", "new_string": "earth"}]},
        conversation_id=cid,
    )
    assert "已" in result["summary"]
    assert result.get("error") is None
    assert repo.read_doc(path).body == "hello earth\n"
    # 索引已更新（reindex 后 search 可命中新内容，此处只验文件）


@pytest.mark.asyncio
async def test_edit_doc_protected_path(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    cid = "conv-3"
    # .kb 内部路径不可写
    result = await registry.execute(
        "edit_doc",
        {"path": ".kb/pending.json", "edits": [{"old_string": "x", "new_string": "y"}]},
        conversation_id=cid,
    )
    assert result.get("error") == "PROTECTED"


@pytest.mark.asyncio
async def test_edit_doc_system_precepts_allowed(tmp_path):
    registry, repo, idx = _make_registry(
        tmp_path,
        system_layer_dir="系统",
    )
    from app.engine.agent.system_layer import SystemLayer

    sl = SystemLayer(repo, dir_name="系统")
    sl.ensure_seeded()
    path = "系统/戒律.md"
    cid = "conv-4"
    await registry.execute("read_doc", {"path": path}, conversation_id=cid)
    original = repo.read_doc(path).body
    marker = "## 一、落库"
    result = await registry.execute(
        "edit_doc",
        {
            "path": path,
            "edits": [
                {
                    "old_string": marker,
                    "new_string": marker,  # no-op 替换，验证允许编辑
                }
            ],
        },
        conversation_id=cid,
    )
    assert result.get("error") is None
    assert repo.read_doc(path).body == original


@pytest.mark.asyncio
async def test_edit_doc_edits_and_insert_mutually_exclusive(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    path = "技术/foo.md"
    repo.write_doc(path, {"title": "Foo"}, "body\n", commit_msg="seed")
    cid = "conv-5"
    await registry.execute("read_doc", {"path": path}, conversation_id=cid)
    result = await registry.execute(
        "edit_doc",
        {
            "path": path,
            "edits": [{"old_string": "body", "new_string": "BODY"}],
            "insert": {"content": "extra\n"},
        },
        conversation_id=cid,
    )
    assert result.get("error") == "INVALID"
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_agent_tools.py::test_edit_doc_requires_read_first -v
```

Expected: FAIL（unknown tool 或缺少方法）

- [ ] **Step 3: 修改 `tools.py`**

1. 更新 imports 与常量：

```python
from app.engine.patch import Edit, apply_edits

WRITE_TOOLS = frozenset({
    "write_kb", "delete_kb", "ask_user", "summarize_conversation", "edit_doc",
})

TOOL_LABELS = {
    # ...existing keys...
    "edit_doc": "局部编辑文档",
}
```

2. 在 `TOOL_DEFINITIONS` 中 `write_kb` 之后插入 `edit_doc` 定义（完整 schema 见设计文档 §5.1；Phase 1 保留 `insert` 字段但在执行层返回 INVALID）。

3. 扩展 `ToolRegistry.__init__`：

```python
    def __init__(
        self,
        ...
        edit_doc_max_edits: int = 10,
        edit_doc_max_patch_chars: int = 8192,
        edit_doc_require_read: bool = True,
    ):
        ...
        self.edit_doc_max_edits = edit_doc_max_edits
        self.edit_doc_max_patch_chars = edit_doc_max_patch_chars
        self.edit_doc_require_read = edit_doc_require_read
        self._read_guard: dict[str, set[str]] = {}
```

4. 添加辅助方法：

```python
    def _mark_read(self, conversation_id: str | None, path: str) -> None:
        if not conversation_id:
            return
        self._read_guard.setdefault(conversation_id, set()).add(path)

    def _is_read(self, conversation_id: str | None, path: str) -> bool:
        if not self.edit_doc_require_read:
            return True
        if not conversation_id:
            return False
        return path in self._read_guard.get(conversation_id, set())

    def _edit_doc_error(self, code: str, message: str, **extra) -> dict:
        out = {"summary": message, "sources": [], "error": code, **extra}
        if code == "NOT_READ":
            out["suggestion"] = "请先调用 read_doc 读取该文档后再 edit_doc"
        return out
```

5. 在 `_read_doc` 成功返回前调用 `self._mark_read(conversation_id, path)`——需在 `execute` 把 `conversation_id` 传入 `_read_doc`，或改 `_read_doc` 签名加 `conversation_id` 参数。

6. 在 `execute` 添加分支：

```python
        if name == "edit_doc":
            return await asyncio.to_thread(
                self._edit_doc, args, conversation_id=conversation_id
            )
```

7. 实现 `_edit_doc`：

```python
    def _edit_doc(self, args: dict, *, conversation_id: str | None = None) -> dict:
        path = args["path"]
        edits_raw = args.get("edits")
        insert_raw = args.get("insert")

        if edits_raw and insert_raw:
            return self._edit_doc_error("INVALID", "edits 与 insert 不能同时使用")
        if insert_raw:
            return self._edit_doc_error(
                "INVALID",
                "insert 模式尚未实现（Phase 2）",
                suggestion="请使用 edits 做局部替换，或用 old_string 含段末换行后 new_string 追加内容",
            )
        if not edits_raw:
            return self._edit_doc_error("INVALID", "必须提供 edits")

        if len(edits_raw) > self.edit_doc_max_edits:
            return self._edit_doc_error(
                "TOO_LARGE",
                f"单次最多 {self.edit_doc_max_edits} 处 edits",
            )

        if not self.repo.is_writable(path):
            return self._edit_doc_error("PROTECTED", f"路径不可写：{path}")

        if not self._is_read(conversation_id, path):
            return self._edit_doc_error("NOT_READ", f"请先 read_doc 再编辑：{path}")

        try:
            doc = self.repo.read_doc(path)
        except FileNotFoundError:
            return self._edit_doc_error("NOT_FOUND", f"文档不存在：{path}")

        edits = [
            Edit(
                old_string=e["old_string"],
                new_string=e["new_string"],
                replace_all=bool(e.get("replace_all", False)),
            )
            for e in edits_raw
        ]
        result = apply_edits(
            doc.body, edits, max_patch_chars=self.edit_doc_max_patch_chars
        )
        if not result.ok:
            err = result.error
            out = self._edit_doc_error(err.code, result.message)
            if err.hint:
                out["hint"] = err.hint
            if err.occurrences:
                out["occurrences"] = err.occurrences
            if err.suggestion:
                out["suggestion"] = err.suggestion
            return out

        self.repo.write_doc(
            path, doc.meta, result.body, commit_msg=f"edit: {path}"
        )
        if self.indexer is not None:
            self.indexer.reindex_doc(path, result.body)
        self.repo.log_change(f"Agent 局部编辑 {path}", commit_msg=f"chore: changelog edit {path}")
        self._mark_read(conversation_id, path)

        return {
            "summary": f"已在 {path} {result.message}",
            "sources": [{"type": "kb", "path": path}],
            "applied": result.applied,
            "preview": result.preview,
        }
```

8. 修改 `execute` 中 `read_doc` 调用，传入 `conversation_id`：

```python
        if name == "read_doc":
            return await asyncio.to_thread(
                self._read_doc, args, conversation_id=conversation_id
            )
```

9. `_read_doc` 签名改为 `def _read_doc(self, args: dict, *, conversation_id: str | None = None)`，在成功 `return out` 前：

```python
        self._mark_read(conversation_id, path)
```

- [ ] **Step 4: 修改 `deps.py` 传入配置**

```python
    tool_registry = ToolRegistry(
        ...
        edit_doc_max_edits=settings.edit_doc_max_edits,
        edit_doc_max_patch_chars=settings.edit_doc_max_patch_chars,
        edit_doc_require_read=settings.edit_doc_require_read,
    )
```

- [ ] **Step 5: 运行 Agent 工具测试**

```bash
cd backend && python -m pytest tests/test_agent_tools.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/engine/agent/tools.py backend/app/deps.py backend/tests/test_agent_tools.py
git commit -m "feat: add edit_doc tool with read guard"
```

---

## Task 5: Prompt 与《戒律》更新

**Files:**
- Modify: `backend/app/engine/agent/prompts.py`
- Modify: `backend/app/engine/agent/system_layer.py`
- Test: `backend/tests/test_system_layer.py`（可选断言新章节存在）

- [ ] **Step 1: 更新 `prompts.py`**

在 `SYSTEM_PROMPT` 的「工具使用」列表中加入：

```markdown
- edit_doc：对已有文档做局部修改（替换）。修改前必须先 read_doc；old_string 须从 read_doc 返回值精确复制。小范围修改优先于 write_kb
```

在「核心原则」**替换原 §7**（不再一律 write_kb+target_path）：

```markdown
7. **当前查看的文档**：用户正在查看某文档时，改字/改段/删段 → edit_doc（path 用该文档）；需与全文语义融合的新段落 → write_kb + target_path；全新随手记 → write_kb。
```

（原第 8 条序号顺延。）

- [ ] **Step 2: 在 `system_layer.py` 的 `_PRECEPTS_BODY` 末尾仅追加 2 条策略**

```markdown

## 七、文档编辑
1. 已有文档的小范围修改不得触发整篇重组（用局部编辑通道，不用随手记合并通道）。
2. 修改 系统/ 下文件前应已确认当前内容，改动应最小化。
```

**不要**在《戒律》中写 old_string、edits 等 API 细节。

- [ ] **Step 3: 运行相关测试**

```bash
cd backend && python -m pytest tests/test_system_layer.py tests/test_agent_orchestrator.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/engine/agent/prompts.py backend/app/engine/agent/system_layer.py
git commit -m "docs: prompt and precepts for edit_doc surgical edits"
```

---

## Task 6: 前端 — `KB_MUTATING_TOOLS` 加入 edit_doc

**Files:**
- Modify: `frontend/src/api.ts`

architecture-fixes F1 已集中 `KB_MUTATING_TOOLS` 与 `Chat.tsx` 集合判定，**只需**在 `KB_MUTATING_TOOLS` 数组中加入 `"edit_doc"`。

- [ ] **Step 1: 修改 `api.ts`**

```typescript
export const KB_MUTATING_TOOLS = [
  "write_kb",
  "delete_kb",
  "summarize_conversation",
  "edit_doc",
] as const;
```

- [ ] **Step 2: `cd frontend && npm run build`**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat: refresh sidebar after edit_doc tool result"
```

**Task 4 补充：** `_edit_doc` 成功写入后调用 `indexer.reindex_doc_after_edit(...)` 而非 `reindex_doc`；tool result 含 `status`、`reindex_mode`（partial/full）。

---

## Task 7: 全量回归

**Files:** 无新文件

- [ ] **Step 1: 运行后端全量测试**

```bash
cd backend && python -m pytest -v
```

Expected: 全部 PASS

- [ ] **Step 2: 更新设计文档状态**

将 `docs/superpowers/specs/2026-07-12-partial-doc-edit-design.md` 首行状态改为：

```markdown
状态：Phase 1 实现中（计划已编写）
```

- [ ] **Step 3: Commit（仅 spec 状态，若本任务有改动）**

```bash
git add docs/superpowers/specs/2026-07-12-partial-doc-edit-design.md
git commit -m "docs: mark partial-doc-edit spec as planned"
```

---

## Phase 2（后续，不在本计划执行范围）

以下留作独立 follow-up：

| 项 | 说明 |
|----|------|
| `insert` 模式 | `apply_insert` + after_heading / at_offset / 文末默认 |
| NOT_FOUND hint | 最接近子串搜索（difflib） |
| 行尾空白 Pass 3 | `_find_with_fallback` 第三层匹配 |
| 前端 diff 预览 | 时间线展示 `preview` + git diff |
| Orchestrator 测试 | FakeLLM 模拟 read→edit 工具链 |

---

## Spec 覆盖自检

| Spec 章节 | 对应 Task |
|-----------|-----------|
| §5 edit_doc schema | Task 4 |
| §6.2 匹配 Pass 1–2 | Task 2–3 |
| §6.3 唯一性 / replace_all | Task 2 |
| §6.4 read guard | Task 4 |
| §6.5.1 增量重索引 | Task 3.5 |
| §6.5 写入流程 | Task 4 + 3.5 |
| §6.6 系统目录可编辑 | Task 4 测试 |
| §7 WRITE_TOOLS | Task 4 |
| §8 错误反馈 | Task 2–4 |
| §9 Prompt / 戒律 | Task 5 |
| §10 配置项 | Task 1 |
| §11 前端 Phase 1 | Task 6 |
| §15 Phase 2 insert | Phase 2 表 |
