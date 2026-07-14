# 第二大脑 · 阶段 4 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按类别配置记忆衰减（默认 90/180 天），每日 maintenance job 将长期无新证据的事实降级为 `stale`/`candidate`/`rejected`；产生 `memory_decayed` 系统事件与恢复路径；`manual`/`explicit_remember`/稳定身份永不自动衰减；只改状态不静默删除。

**Architecture:** `memory/decay.py` 定义 per-category 阈值与豁免规则；`MemoryMaintenanceJob` 扫描 `memory_facts` 按 `last_seen_at`/evidence 时间应用降级；状态变更写 `conversation_system_events`（最近关联会话或全局 workspace 事件）；新 evidence 在 `MemoryObserver` 可将 `stale` 恢复为 `confirmed`；`main.py` lifespan 每日触发一次 maintenance（测试直接调用）。

**Tech Stack:** Python 3.12 / SQLite / pytest。

**Spec:** [2026-07-13-memory-layer-design.md](../specs/2026-07-13-memory-layer-design.md) §8.4、§16 阶段 4。

**前置：** 阶段 3 已合并。

---

## 文件结构（4）

| 文件 | 职责 |
|------|------|
| `backend/app/engine/memory/decay.py` | 类别阈值、豁免判定、目标状态计算 |
| `backend/app/engine/memory_maintenance.py` | 每日 job：扫描、降级、发事件 |
| `backend/app/engine/memory/store.py` | `list_decay_candidates`、`set_status` |
| `backend/app/engine/memory/observer.py` | stale 恢复逻辑 |
| `backend/app/config.py` | `memory_decay_*_days` 配置项 |
| `backend/app/main.py` | 每日 maintenance 调度 |
| `backend/tests/test_memory_phase4_*.py` | 对应测试 |

---

## 决策记录（4 冻结）

| 项 | 决策 |
|----|------|
| goal/project | 90 天无新 evidence → `stale` |
| preference/workflow (inferred) | 180 天无 evidence → `candidate` |
| candidate | 180 天无 evidence → `rejected` |
| 豁免 origin | `manual`、`explicit_remember` 不衰减 |
| 豁免 category | `identity` 不自动衰减 |
| 操作 | 仅 `UPDATE status`；不 `DELETE` |
| 通知 | `memory_decayed` system_event，含 `fact_id`/`old_status`/`new_status` |
| 恢复 | 新 evidence 命中 `stale` fact → 恢复 `confirmed` |
| 调度 | lifespan 每 24h 一次；`MemoryMaintenanceJob.run()` 可单测 |

---

## Task 1: decay 规则与 store 查询

**Files:**
- Create: `backend/app/engine/memory/decay.py`
- Modify: `backend/app/engine/memory/store.py`
- Test: `backend/tests/test_memory_phase4_decay.py`

- [ ] **Step 1: 写失败测试**

```python
def test_manual_origin_never_decays(store):
    ...

def test_identity_never_decays(store):
    ...

def test_goal_becomes_stale_after_90_days(store, maintenance):
    ...
```

- [ ] **Step 2–4: 实现 `decay_target_status`、`is_decay_exempt`**

```bash
git commit -m "feat: per-category memory decay rules"
```

---

## Task 2: MemoryMaintenanceJob

**Files:**
- Create: `backend/app/engine/memory_maintenance.py`
- Test: `backend/tests/test_memory_phase4_maintenance.py`

- [ ] **Step 1: 写失败测试**

```python
def test_maintenance_emits_decay_event(conversations, maintenance):
    ...

def test_maintenance_never_deletes_rows(store, maintenance):
    ...
```

- [ ] **Step 2–4: 扫描 + 批量状态更新 + 事件**

```bash
git commit -m "feat: daily memory maintenance job with decay events"
```

---

## Task 3: stale 恢复与调度接线

**Files:**
- Modify: `backend/app/engine/memory/observer.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/deps.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_memory_phase4_recovery.py`

- [ ] **Step 1: 写失败测试**

```python
def test_stale_recovers_on_new_evidence(observer, store):
    ...
```

- [ ] **Step 2–4: observer 恢复；maintenance 注入 deps**

```bash
git commit -m "feat: stale memory recovery and maintenance scheduling"
```

---

## 验收清单

1. manual/explicit_remember/identity 不自动衰减。
2. goal/project 90 天 → stale；inferred preference 180 天 → candidate。
3. candidate 180 天 → rejected。
4. 无静默删除；审计行保留。
5. decay 产生 `memory_decayed` 事件。
6. 新 evidence 可恢复 stale。
7. 全量 `pytest` 绿。

---

**Plan complete.**
