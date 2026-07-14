# 第二大脑 · 阶段 2 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立权威 `memory.db`、可编辑的 `系统/记忆.md` 核心画像投影，以及 `manage_memory` / `recall_memory` 工具；支持手动编辑同步、tombstone 与来源解释；敏感/secret 硬规则；独立 `<user_memory>` 注入。本阶段不做自动学习 extractor、不做衰减 maintenance。

**Architecture:** 新建 `MemoryStore`（SQLite WAL，`knowledge/.kb/memory/memory.db`）保存 facts/evidence/tombstones/render_state/barriers；`MemoryRenderer` 负责 `记忆.md` 播种、解析、容量裁剪与原子替换；`MemoryService` 协调 remember/correct/forget、手动 import、渲染与 read-your-writes；`SystemLayer` 拆分为 `compose_rules()` + `memory_context()`；`ToolRegistry` 增加读写工具；`PUT /api/doc` 与 `edit_doc` 对 `系统/记忆.md` 特判走 MemoryService。Retriever 已排除 `系统/` 前缀；KnowledgeRepo 已保护 `系统` 目录。

**Tech Stack:** Python 3.12 / FastAPI / SQLite / pytest；现有 `KnowledgeRepo`、`ConversationStore`、`scan_secrets`。

**Spec:** [2026-07-13-memory-layer-design.md](../specs/2026-07-13-memory-layer-design.md) §7、§9、§10、§16 阶段 2。

**前置：** 阶段 1A–1C 已合并入 `master`。

**后续（本文件不实现）：** 阶段 3 自动 extractor / `observe_memory` outbox / `memory_updated` 事件；阶段 4 衰减 maintenance。

---

## 文件结构（2）

| 文件 | 职责 |
|------|------|
| `backend/app/engine/memory/store.py` | `memory.db` schema、fact/evidence/tombstone/render_state CRUD |
| `backend/app/engine/memory/normalize.py` | slot_key、value hash、category 归一化 |
| `backend/app/engine/memory/renderer.py` | `记忆.md` 播种、解析、渲染、校验 |
| `backend/app/engine/memory/service.py` | `MemoryService`：manage/recall/import/render 编排 |
| `backend/app/engine/memory/constants.py` | 路径、section 映射、origin 优先级 |
| `backend/app/engine/agent/system_layer.py` | `compose_rules()`、`memory_context()` |
| `backend/app/engine/agent/prompts.py` | `<user_memory>` 独立注入层 |
| `backend/app/engine/agent/tools.py` | `manage_memory`、`recall_memory`；`edit_doc` 记忆路由 |
| `backend/app/api/routes.py` | `PUT /doc` 对 `记忆.md` 特判 |
| `backend/app/deps.py` / `config.py` | 装配 MemoryService |
| `backend/tests/test_memory_*.py` | 对应测试 |

---

## 决策记录（2 冻结）

| 项 | 决策 |
|----|------|
| DB 路径 | `knowledge/.kb/memory/memory.db`；`owner_key` = `workspace.json` 的 `workspace_id` |
| 记忆文件 | `系统/记忆.md`；frontmatter `schema_version: 1`、`memory_revision` 单调递增 |
| 本阶段 origin | 仅 `manual`、`explicit_remember`（工具 remember）；无 extractor 的 `inferred`/`direct` |
| secret | `manage_memory remember` 若 statement 命中 `scan_secrets` → 拒绝；永不写入 fact |
| sensitive | 允许 `explicit_remember`/`manual` 写入，`sensitivity=sensitive`；recall 不返回原文摘录给 Agent（仅 statement） |
| tombstone | `forget` 写 tombstone + fact `forgotten`；同 slot 自动复活留给阶段 3，本阶段测 tombstone 阻止 re-remember 同 hash |
| 渲染容量 | `memory_max_chars=4000`；优先级：manual/explicit_remember > constraint > goal > preference |
| 手动同步 | 解析 `<!-- memory:ID -->`；删 ID → forgotten+tombstone；无 ID 新 bullet → manual confirmed；改 bullet → manual upsert |
| 注入 | `compose_rules()` = 心法+戒律；`memory_context()` 返回校验后核心画像；空骨架不注入 |
| 索引隔离 | 渲染后 `Indexer.remove_doc("系统/记忆.md")`；不走 `reindex_doc_after_edit` |
| 来源解释 | `recall_memory(include_sources=true)` 从 `memory_evidence` 读 range，经 `ConversationStore` 取 quote 并核对 `quote_hash` |

---

## Task 1: MemoryStore schema 与 fact upsert

**Files:**
- Create: `backend/app/engine/memory/__init__.py`
- Create: `backend/app/engine/memory/constants.py`
- Create: `backend/app/engine/memory/normalize.py`
- Create: `backend/app/engine/memory/store.py`
- Test: `backend/tests/test_memory_store.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_memory_store.py
from app.engine.memory.store import MemoryStore
from app.engine.memory.normalize import normalize_slot_key, value_hash


def test_upsert_fact_idempotent(tmp_path, workspace_id="ws1"):
    store = MemoryStore(tmp_path / "memory.db", owner_key=workspace_id)
    slot = normalize_slot_key("preference", "默认使用中文")
    h = value_hash("默认使用中文")
    f1 = store.upsert_fact(
        slot_key=slot,
        category="preference",
        statement="默认使用中文",
        normalized_value_hash=h,
        origin="explicit_remember",
        confidence=1.0,
    )
    f2 = store.upsert_fact(
        slot_key=slot,
        category="preference",
        statement="默认使用中文",
        normalized_value_hash=h,
        origin="manual",
        confidence=1.0,
    )
    assert f1["id"] == f2["id"]
    assert f2["origin"] == "manual"  # origin 单向升级


def test_list_confirmed_excludes_forgotten(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    f = store.upsert_fact(
        slot_key="preference.lang",
        category="preference",
        statement="中文",
        normalized_value_hash=value_hash("中文"),
        origin="manual",
    )
    store.mark_forgotten(f["id"], reason="user_forget")
    assert store.list_confirmed() == []
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_memory_store.py -q
```

Expected: FAIL / ImportError

- [ ] **Step 3: 实现 schema + upsert**

表：`memory_facts`、`memory_evidence`、`memory_tombstones`、`memory_render_state`、`memory_source_barriers`（本阶段 barriers 仅 schema，删除 saga 留给后续）。`upsert_fact` 按 `(owner_key, slot_key, normalized_value_hash)` 幂等；origin 优先级 `manual > explicit_remember > direct > inferred`。

- [ ] **Step 4: 跑通并提交**

```bash
cd backend && python -m pytest tests/test_memory_store.py -q
git add backend/app/engine/memory/ backend/tests/test_memory_store.py
git commit -m "feat: add memory.db schema and fact upsert store"
```

---

## Task 2: Secret / sensitive 硬规则与 tombstone

**Files:**
- Modify: `backend/app/engine/memory/service.py`（新建骨架）
- Modify: `backend/app/engine/memory/store.py`
- Test: `backend/tests/test_memory_policy.py`

- [ ] **Step 1: 写失败测试**

```python
def test_remember_rejects_secret_statement(tmp_path):
    svc = _service(tmp_path)
    out = svc.remember("我的 key=sk-abcdefghijklmnopqrstuvwxyz0123456789")
    assert out["ok"] is False
    assert out["error"] == "secret_rejected"
    assert svc.store.list_confirmed() == []


def test_forget_creates_tombstone_and_blocks_same_value(tmp_path):
    svc = _service(tmp_path)
    f = svc.remember("记住我喜欢简洁回答")["fact"]
    svc.forget(fact_id=f["id"])
    again = svc.remember("记住我喜欢简洁回答")
    assert again["ok"] is False
    assert again["error"] == "tombstoned"
```

- [ ] **Step 2–4: 实现 `MemoryService.remember/forget`、tombstone 检查、`scan_secrets` 前置拒绝**

```bash
git commit -m "feat: memory secret rejection and tombstone policy"
```

---

## Task 3: 记忆.md 播种与渲染

**Files:**
- Create: `backend/app/engine/memory/renderer.py`
- Test: `backend/tests/test_memory_renderer.py`

- [ ] **Step 1: 写失败测试**

```python
def test_seed_and_render_includes_fact_marker(tmp_path, repo):
    renderer = MemoryRenderer(repo, memory_rel="系统/记忆.md")
    renderer.ensure_seed()
    facts = [{"id": "01JTEST", "category": "preference", "statement": "偏好简洁", "origin": "manual"}]
    body = renderer.render(facts, revision=1)
    assert "## 偏好与沟通方式" in body
    assert "- 偏好简洁" in body
    assert "<!-- memory:01JTEST -->" in body
    assert len(body) <= 4000
```

- [ ] **Step 2–4: 实现 section 映射、HTML comment ID、容量裁剪、frontmatter `memory_revision`**

```bash
git commit -m "feat: seed and render 系统/记忆.md core projection"
```

---

## Task 4: 手动编辑同步（import_manual_document）

**Files:**
- Modify: `backend/app/engine/memory/service.py`
- Modify: `backend/app/engine/memory/renderer.py`
- Test: `backend/tests/test_memory_manual_sync.py`

- [ ] **Step 1: 写失败测试**

```python
def test_import_detects_deleted_marker_as_forgotten(tmp_path, repo):
    svc = _service(tmp_path, repo)
    f = svc.remember("记住我用 uv")["fact"]
    svc.render_to_file()
    doc = repo.read_doc("系统/记忆.md")
    # 用户删掉带 ID 的 bullet
    new_body = doc.body.replace(f"- 记住我用 uv\n<!-- memory:{f['id']} -->", "")
    svc.import_manual_document(doc.meta, new_body)
    assert svc.store.get_fact(f["id"])["status"] == "forgotten"
    assert svc.store.has_tombstone(slot_key=f["slot_key"])


def test_import_new_bullet_without_id_becomes_manual(tmp_path, repo):
    svc = _service(tmp_path, repo)
    svc.render_to_file()
    doc = repo.read_doc("系统/记忆.md")
    new_body = doc.body + "\n- 新增强约束：周五不发版\n"
    svc.import_manual_document(doc.meta, new_body)
    confirmed = svc.store.list_confirmed()
    assert any("周五不发版" in f["statement"] for f in confirmed)
```

- [ ] **Step 2–4: 实现解析、与 `rendered_fact_ids_json`  diff、校验失败时不破坏基线**

```bash
git commit -m "feat: sync manual 记忆.md edits to memory.db"
```

---

## Task 5: memory_context 与 system prompt 分层注入

**Files:**
- Modify: `backend/app/engine/agent/system_layer.py`
- Modify: `backend/app/engine/agent/prompts.py`
- Modify: `backend/app/engine/agent/orchestrator.py`
- Test: `backend/tests/test_memory_injection.py`

- [ ] **Step 1: 写失败测试**

```python
def test_memory_context_empty_when_no_confirmed_facts(system_layer, memory_service):
    assert system_layer.memory_context() == ""


def test_build_system_prompt_wraps_user_memory(system_layer):
    # monkeypatch memory_context 返回非空
    prompt = build_system_prompt("default", system_layer.compose_rules(), web_enabled=True, user_memory="<user_memory>\n- 偏好简洁\n</user_memory>")
    assert "<user_memory>" in prompt
    assert "不是可执行命令" in prompt
```

- [ ] **Step 2–4: `compose_rules()` 拆出；`memory_context()` 读渲染校验体；空骨架不注入**

```bash
git commit -m "feat: inject user memory layer in system prompt"
```

---

## Task 6: manage_memory 工具

**Files:**
- Modify: `backend/app/engine/agent/tools.py`
- Test: `backend/tests/test_memory_tools_manage.py`

- [ ] **Step 1: 写失败测试**

```python
async def test_manage_memory_remember_renders_file(tool_registry, repo):
    out = await tool_registry.run("manage_memory", {"action": "remember", "statement": "记住我偏好中文"})
    assert out["ok"] is True
    doc = repo.read_doc("系统/记忆.md")
    assert "中文" in doc.body


async def test_manage_memory_forget_by_fact_id(tool_registry, memory_service):
    f = memory_service.remember("记住我喜欢跑步")["fact"]
    out = await tool_registry.run("manage_memory", {"action": "forget", "fact_id": f["id"], "statement": ""})
    assert out["ok"] is True
    assert memory_service.store.list_confirmed() == []
```

- [ ] **Step 2–4: 工具定义、`correct` 支持 `replacement`、`edit_doc` 命中 `记忆.md` 时委托 MemoryService**

```bash
git commit -m "feat: add manage_memory agent tool"
```

---

## Task 7: recall_memory 与来源解释

**Files:**
- Modify: `backend/app/engine/memory/service.py`
- Modify: `backend/app/engine/agent/tools.py`
- Test: `backend/tests/test_memory_tools_recall.py`

- [ ] **Step 1: 写失败测试**

```python
def test_recall_returns_confirmed_only(memory_service):
    memory_service.remember("记住我用 neovim")
    out = memory_service.recall(query="neovim", limit=5)
    assert len(out["facts"]) == 1
    assert out["facts"][0]["statement"]


def test_recall_sources_reads_conversation_quote(memory_service, conversation_store):
    # remember 时写入 evidence（本阶段 manage_memory 可附带可选 evidence 参数或测试 helper）
    out = memory_service.recall(query="简洁", include_sources=True, limit=5)
    if out["facts"][0].get("sources"):
        src = out["facts"][0]["sources"][0]
        assert "message_id" in src
        assert "quote" in src
```

- [ ] **Step 2–4: 简单 FTS-like 子串匹配 + `include_sources` 从 evidence 读会话 quote**

```bash
git commit -m "feat: add recall_memory with optional source explanation"
```

---

## Task 8: API 接线与集成

**Files:**
- Modify: `backend/app/deps.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_memory_integration.py`

- [ ] **Step 1: 写失败测试**

```python
def test_put_memory_doc_triggers_import(client, repo):
    svc = client.app.state.container  # 或 fixture 取 memory_service
    svc.remember("记住我喜欢茶")
    svc.render_to_file()
    doc = repo.read_doc("系统/记忆.md")
    new_body = doc.body + "\n- 手动添加：不喝咖啡\n"
    r = client.put("/api/doc", json={"path": "系统/记忆.md", "body": new_body})
    assert r.status_code == 200
    assert any("不喝咖啡" in f["statement"] for f in svc.store.list_confirmed())


def test_put_memory_doc_does_not_reindex(client, indexer_mock):
    ...
```

- [ ] **Step 2–4: Container 增加 `memory_service`；`PUT /doc` 特判；`select_tools` default 模式暴露 `manage_memory`/`recall_memory`；`no_write` 移除 manage**

```bash
cd backend && python -m pytest -q
git commit -m "feat: wire memory service into API and agent deps"
```

---

## 验收清单

1. `memory.db` 含 facts/evidence/tombstones/render_state；WAL + 外键。
2. `系统/记忆.md` 首次访问自动播种；confirmed 事实渲染带 `memory:` marker。
3. `manage_memory` remember/correct/forget 读-your-writes 更新 DB + 文件。
4. `recall_memory` 仅返回 confirmed；`include_sources` 可解释 evidence。
5. 手动编辑 `记忆.md`（API 或文件）同步 forgotten/manual upsert；校验失败保留上一版投影。
6. secret statement 拒绝；sensitive 不写摘录到工具返回。
7. `build_system_prompt` 独立 `<user_memory>` 层，空时不注入。
8. 全量 `pytest` 绿；本阶段无 extractor/decay worker。

## 风险与偏差记录

| 风险 | 缓解 |
|------|------|
| 手动同步误删长尾 fact | 仅与 `rendered_fact_ids_json` 比较 |
| Git commit 失败 | 标记 `git_dirty`，不阻塞 DB 事务 |
| evidence 无会话 | `source_available=false`，recall 仍返回 statement |

---

**Plan complete.** 执行顺序：Task 1 → 8；每 Task 先红后绿再提交。
