# 第二大脑 · 阶段 3 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `observe_memory` outbox 上实现可恢复的异步自动学习：MemoryExtractor 从用户消息提取候选、policy 晋升/冲突/敏感规则、`memory_updated` 时间线反馈；`observation_allowed` 按 turn 门控；候选永不注入或经 `recall_memory` 返回。

**Architecture:** `begin_turn` 同事务入队 `observe_memory`（`blocked`）；`finalize_turn` 按 `observation_allowed` 将任务转为 `pending` 或 `cancelled`；`MemoryWorker`（或扩展 `DerivationWorker`）claim 已 finalize 的观察任务 → `MemoryExtractor` → `policy.apply_observation` → `MemoryStore` upsert/evidence；confirmed 变更触发 `render_to_file` + `system_event`；`GET /api/conversations/{cid}/events` 供前端续取。

**Tech Stack:** Python 3.12 / FastAPI / SQLite / pytest；现有 `ConversationStore`、`MemoryService`、`scan_secrets`、`policy.py`。

**Spec:** [2026-07-13-memory-layer-design.md](../specs/2026-07-13-memory-layer-design.md) §7.4、§8.1–8.3、§10.4、§11.1、§16 阶段 3。

**前置：** 阶段 2 已合并（含 tombstone clear、sensitive recall、doc sync 校验）。

**后续（本文件不实现）：** 阶段 4 按类别衰减与每日 maintenance。

---

## 文件结构（3）

| 文件 | 职责 |
|------|------|
| `backend/app/engine/memory/models.py` | `MemoryCandidate`、提取结果结构化类型 |
| `backend/app/engine/memory/extractor.py` | `MemoryExtractor`：规则/LLM 结构化提取 + 证据 range 校验 |
| `backend/app/engine/memory/policy.py` | 晋升、冲突、敏感、直接自述判定 |
| `backend/app/engine/memory/observer.py` | `observe_message` 编排：scanner → extract → policy → store |
| `backend/app/engine/memory_worker.py` | 消费 `observe_memory` outbox |
| `backend/app/engine/conversations.py` | 入队 blocked observe；finalize 激活/取消；`system_events` 表 |
| `backend/app/engine/memory/store.py` | candidate CRUD、supersede、跨会话 evidence 计数 |
| `backend/app/engine/memory/service.py` | `observe_message`、渲染与事件发射 |
| `backend/app/api/routes.py` | `ChatBody.observation_allowed`；`GET .../events` |
| `backend/app/deps.py` / `main.py` | 装配 MemoryWorker；lifespan drain |
| `backend/tests/test_memory_phase3_*.py` | 对应测试 |

---

## 决策记录（3 冻结）

| 项 | 决策 |
|----|------|
| outbox kind | `observe_memory`；`begin_turn` 创建 `blocked`；finalize 后 `pending`/`cancelled` |
| claim 条件 | 仅 `turn.finalized_at` 非空且 `observation_allowed=1` 的 blocked/pending 可 claim |
| 提取器 | 测试用 `RuleBasedMemoryExtractor`；生产 `LLMMemoryExtractor` 包装 `small_model` |
| 直接自述 | `policy.is_direct_self_statement` + 精确 evidence range → 立即 `confirmed`（`origin=direct`） |
| 推断晋升 | 同 slot 至少 2 个不同 `conversation_id`、≥2 条 evidence、confidence≥0.80；**同会话重复不晋升** |
| 敏感 | extractor 检出敏感且无 `explicit_remember`/`manual` 授权 → 丢弃，不写 candidate |
| secret | `scan_secrets` 先于 extractor；永不进入 memory.db |
| 冲突 | 新 direct/manual 覆盖旧 inferred；`superseded` 保留审计；双 inferred 矛盾均不晋升 |
| 候选隔离 | `list_confirmed`/`recall`/`memory_context` 仅 `status=confirmed`；renderer 同 |
| memory_updated | `conversation_system_events` 表；payload `type=memory_updated`；不进 FTS/Vector/llm_history |
| 历史回填 | CLI `python -m app.engine.memory_backfill` 可选；默认不自动补历史 observe |
| observation_allowed | `ChatBody` 默认 `true`；路由透传 `begin_turn` |

---

## Task 1: observe_memory outbox 入队与 finalize 门控

**Files:**
- Modify: `backend/app/engine/conversations.py`
- Test: `backend/tests/test_memory_phase3_outbox.py`

- [ ] **Step 1: 写失败测试**

```python
def test_begin_turn_enqueues_blocked_observe_memory(store):
    cid = store.create()
    turn = store.begin_turn(cid, "我喜欢简洁", "c1", observation_allowed=True)
    jobs = store.list_outbox(kind="observe_memory", message_id=turn["user_message"]["id"])
    assert len(jobs) == 1
    assert jobs[0]["status"] == "blocked"


def test_finalize_cancels_observe_when_not_allowed(store):
    cid = store.create()
    turn = store.begin_turn(cid, "hi", "c1", observation_allowed=False)
    store.finalize_turn(cid, turn["turn_id"], assistant={"text": "ok", "timeline": [], "sources": []})
    jobs = store.list_outbox(kind="observe_memory")
    assert jobs[0]["status"] == "cancelled"


def test_finalize_activates_observe_when_allowed(store):
    cid = store.create()
    turn = store.begin_turn(cid, "我喜欢茶", "c1", observation_allowed=True)
    store.finalize_turn(cid, turn["turn_id"], assistant={"text": "好", "timeline": [], "sources": []})
    jobs = store.list_outbox(kind="observe_memory")
    assert jobs[0]["status"] == "pending"
```

- [ ] **Step 2–4: `_enqueue_observe_memory`、`_activate_observe_jobs(turn_id)`、`claim_outbox` 跳过未 finalize turn**

```bash
git commit -m "feat: enqueue gated observe_memory outbox on begin_turn"
```

---

## Task 2: MemoryExtractor 与证据校验

**Files:**
- Create: `backend/app/engine/memory/models.py`
- Create: `backend/app/engine/memory/extractor.py`
- Test: `backend/tests/test_memory_extractor.py`

- [ ] **Step 1: 写失败测试**

```python
def test_extractor_rejects_invalid_evidence_range():
    ext = RuleBasedMemoryExtractor()
    text = "我偏好简洁回答"
    out = ext.extract(text, context_messages=[])
    assert out.candidates
    bad = out.candidates[0]._replace(start_char=99, end_char=100)
    assert policy.validate_evidence(text, bad) is False


def test_extractor_skips_secrets():
    ext = RuleBasedMemoryExtractor()
    out = ext.extract("key=sk-abcdefghijklmnopqrstuvwxyz0123456789", [])
    assert out.candidates == []
```

- [ ] **Step 2–4: 结构化候选；range 必须 `text[start:end]` 与 statement 一致；secret 前置跳过**

```bash
git commit -m "feat: add MemoryExtractor with evidence range validation"
```

---

## Task 3: Policy 晋升与冲突

**Files:**
- Modify: `backend/app/engine/memory/policy.py`
- Modify: `backend/app/engine/memory/store.py`
- Test: `backend/tests/test_memory_phase3_policy.py`

- [ ] **Step 1: 写失败测试**

```python
def test_direct_self_statement_confirms_immediately(store, observer):
    # 用户说「我偏好简洁」→ confirmed, origin=direct
    ...


def test_inferred_same_session_stays_candidate(store, observer):
    # 同一会话两次相同推断 → 仍 candidate
    ...


def test_inferred_promotes_after_two_sessions(store, observer):
    # 两个 conversation_id + confidence → confirmed
    ...


def test_conflict_supersedes_inferred(store, observer):
    # slot 新 direct 值覆盖旧 inferred → old superseded
    ...


def test_sensitive_without_auth_not_saved(store, observer):
    # 健康/住址类无 explicit_remember → 无 fact
    ...
```

- [ ] **Step 2–4: `apply_observation`、`resolve_slot_conflict`、`count_distinct_conversations`**

```bash
git commit -m "feat: memory promotion, conflict, and sensitive policy"
```

---

## Task 4: MemoryWorker 与 observe_message 编排

**Files:**
- Create: `backend/app/engine/memory/observer.py`
- Create: `backend/app/engine/memory_worker.py`
- Modify: `backend/app/engine/memory/service.py`
- Test: `backend/tests/test_memory_phase3_worker.py`

- [ ] **Step 1: 写失败测试**

```python
def test_worker_processes_observe_job_and_confirms_direct(container):
    # begin_turn + finalize + drain memory worker → confirmed fact
    ...


def test_candidate_never_in_recall(container):
    # 推断仅 candidate → recall count 0
    ...
```

- [ ] **Step 2–4: `MemoryWorker.process_observe_job`；confirmed 时 `render_to_file`**

```bash
git commit -m "feat: MemoryWorker consumes observe_memory outbox"
```

---

## Task 5: memory_updated 事件与 API

**Files:**
- Modify: `backend/app/engine/conversations.py`
- Modify: `backend/app/api/routes.py`
- Test: `backend/tests/test_memory_phase3_events.py`

- [ ] **Step 1: 写失败测试**

```python
def test_memory_updated_event_after_confirm(client):
    # worker 晋升后 GET /api/conversations/{cid}/events 含 memory_updated
    ...


def test_events_cursor_after_event_id(client):
    # after_event_id 过滤
    ...
```

- [ ] **Step 2–4: `append_system_event`；`GET /conversations/{cid}/events?after_event_id=`**

```bash
git commit -m "feat: memory_updated system events API"
```

---

## Task 6: 路由 observation_allowed 与 deps 接线

**Files:**
- Modify: `backend/app/api/routes.py`（`ChatBody.observation_allowed`）
- Modify: `backend/app/deps.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_memory_phase3_integration.py`

- [ ] **Step 1: 写失败测试**

```python
def test_chat_passes_observation_allowed(client):
    # observation_allowed=false → 无 pending observe 或 cancelled
    ...
```

- [ ] **Step 2–4: lifespan 合并 drain memory worker；`build_container` 注入 `memory_worker`**

```bash
git commit -m "feat: wire observation_allowed and memory worker into API"
```

---

## Task 7: 可选历史记忆回填命令

**Files:**
- Create: `backend/app/engine/memory_backfill.py`
- Test: `backend/tests/test_memory_backfill.py`

- [ ] **Step 1: 写失败测试**

```python
def test_backfill_enqueues_observe_for_retained_messages(store):
    # 显式命令仅为 retained user 消息创建 observe_memory
    ...
```

- [ ] **Step 2–4: CLI entry；不自动运行；尊重 deletion ledger**

```bash
git commit -m "feat: optional historical memory observation backfill command"
```

---

## 验收清单

1. `observe_memory` blocked → finalize 门控 → worker 可恢复处理。
2. 直接普通自述 + 有效 evidence → 立即 `confirmed`。
3. 推断同会话不晋升；跨 2+ 会话 + 门槛 → `confirmed`。
4. 冲突/替代：`superseded` 退出画像；tombstone 仍阻止复活。
5. secret 永不提取；敏感无授权不保存。
6. `recall_memory` / `<user_memory>` 不含 candidate。
7. `memory_updated` 事件可续取；不进索引与 llm_history。
8. 全量 `pytest` 绿。

## 风险与偏差记录

| 风险 | 缓解 |
|------|------|
| LLM 提取不稳定 | 测试用 RuleBased；生产 JSON schema + 校验失败整批拒绝 |
| worker 与 derivation 争用 | 独立 `MemoryWorker.drain`；同线程顺序消费或独立线程 |
| 事件风暴 | 每轮合并为单条 `memory_updated` count |

---

**Plan complete.** 执行顺序：Task 1 → 7；每 Task 先红后绿再提交。
