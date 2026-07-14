# 第二大脑 · 阶段 1C 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 message+range 来源全链路、邻近上下文工具、检索同源分组与前端消息跳转，并完善归档总结 provenance（`summaries[]`、stale 关系、`conversation_ids` frontmatter、长会话分段总结）。

**Architecture:** 抽取共享 `source_dedupe_key` 统一后端去重；新增 `read_conversation_context` 服务与 Agent 工具；`Retriever` 补全会话向量 `min_vector_score`、相邻 chunk 合并与 summary↔message 同源分组；`Organizer`/`ConversationStore` 暴露完整 `summaries[]` 与 `conversation_ids` 列表 frontmatter；前端为消息加 `data-message-id` 锚点，用 `Array.from` 做 `unicode-codepoint-v1` 区间高亮并实现跨会话跳转。本阶段不做 `记忆.md` / `memory.db` / 自动学习。

**Tech Stack:** Python 3.12 / FastAPI / SQLite / Chroma / pytest；React + TypeScript + Vitest。

**Spec:** [2026-07-13-memory-layer-design.md](../specs/2026-07-13-memory-layer-design.md) §6.3–6.4、§16 阶段 1C。

**前置：** 阶段 1A、1B 已合并入 `master`。

**后续（本文件不实现）：** 阶段 2 `记忆.md`；阶段 3 自动学习；阶段 4 衰减。

---

## 文件结构（1C）

| 文件 | 职责 |
|------|------|
| `backend/app/engine/source_key.py` | 来源去重键（message+range）共享函数 |
| `backend/app/engine/conversation_context.py` | 邻近消息上下文读取、脱敏、字符上限 |
| `backend/app/engine/retriever.py` | `min_vector_score`、相邻合并、同源分组 |
| `backend/app/engine/conversations.py` | `summaries[]` API 字段；`read_context` 查询 |
| `backend/app/engine/organizer.py` | `conversation_ids` frontmatter；长会话分段总结 |
| `backend/app/engine/agent/tools.py` | `read_conversation_context` 工具 |
| `backend/app/engine/agent/orchestrator.py` | 改用共享 `source_dedupe_key` |
| `backend/app/api/routes.py` | `_TimelineAccumulator` 去重对齐 |
| `backend/app/config.py` | `conversation_context_max_chars` 等 |
| `frontend/src/utils/unicodeHighlight.ts` | code point 区间高亮纯函数 |
| `frontend/src/hooks/chat/useConversationJump.ts` | 跳转意图 + 滚动/高亮 |
| `frontend/src/components/chat/ChatMessageRow.tsx` | `data-message-id` 锚点 |
| `frontend/src/components/chat/MessageRangeHighlight.tsx` | 消息内区间高亮 UI |
| `frontend/src/components/Chat.tsx` / `App.tsx` | 会话来源点击跳转 |
| `frontend/src/api.ts` | `ChatMessage.id`、`ConversationSummary` 扩展 |
| `backend/tests/test_*.py` / `frontend/src/**/*.test.ts` | 对应测试 |

---

## 决策记录（1C 冻结）

| 项 | 决策 |
|----|------|
| 来源去重键 | `conversation:{cid}:{message_id}:{start_char}:{end_char}`；`orchestrator`、`_TimelineAccumulator`、`dedupeSources` 三处一致 |
| `read_conversation_context` | `before_messages`/`after_messages` 各 0–10，默认 2；总字符硬上限 `conversation_context_max_chars=12000`；给 Agent 的 `text` 走 `mask_secrets` |
| 会话向量分数 | `_conv_vector_lane` 与 KB 向量 lane 同样应用 `min_vector_score`（1B 遗漏，1C 补齐） |
| 相邻 chunk 合并 | 同一 `message_id` 且 `prev.end_char == next.start_char` 的命中合并为一条（保留最高 RRF 分，拼接 excerpt） |
| 同源分组 | `provenance_group = conversation:{cid}`；KB 总结文档从 frontmatter `conversation_ids`（兼容旧 `conversation_id`）解析；分组内 `nav_preference=summary`，事实核验仍返回全部 hits |
| `summaries[]` | `GET /conversations/{cid}` 增加 `summaries` 数组；保留 `summary_path`/`summarized` 兼容字段 |
| stale 标记 | 新消息 `begin_turn` 已通过 `_mark_dirty_and_stale` 将 `current` 关系标 `stale`；本阶段补测试与 API 暴露 |
| frontmatter | 新文档写 `conversation_ids: [cid]` 列表；merge/append 时并集去重，不再单独写 `conversation_id` |
| 长会话总结 | `full_transcript` 超 `summarize_segment_chars`（默认 28000）时按消息边界切段 → 段摘要 → 全局归并；每段记录 `first_message_id`/`last_message_id` |
| 前端高亮 | **必须** `Array.from(text).slice(start, end)` 映射 DOM，禁止 UTF-16 下标 |
| 跳转行为 | 点击 conversation 来源：若 `cid !== 当前会话` 则 `setActiveConversationId` 并排队跳转；同会话直接 `scrollIntoView` + 高亮 3s |
| cursor | 1B revision 绑定已够用；本阶段仅补相邻合并后 `doc_id` 稳定性测试，不改 cursor 协议 |

---

## Task 1: 来源去重键全链路对齐

**Files:**
- Create: `backend/app/engine/source_key.py`
- Modify: `backend/app/engine/agent/orchestrator.py:64-83`
- Modify: `backend/app/api/routes.py:96-187`
- Test: `backend/tests/test_source_key.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_source_key.py
from app.engine.source_key import source_dedupe_key, extend_sources


def test_conversation_key_includes_message_and_range():
    a = {
        "type": "conversation",
        "cid": "c1",
        "message_id": "m1",
        "start_char": 0,
        "end_char": 4,
    }
    b = {**a, "start_char": 4, "end_char": 8}
    assert source_dedupe_key(a) != source_dedupe_key(b)
    assert source_dedupe_key(a) == source_dedupe_key(dict(a))


def test_extend_sources_dedupes_by_key():
    src = {"type": "conversation", "cid": "c1", "message_id": "m1", "start_char": 0, "end_char": 3}
    all_sources: list[dict] = [dict(src)]
    extend_sources(all_sources, [dict(src), {**src, "excerpt": "other"}])
    assert len(all_sources) == 1
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_source_key.py -q
```

Expected: FAIL / ImportError

- [ ] **Step 3: 实现共享模块并接线**

```python
# backend/app/engine/source_key.py
from __future__ import annotations


def source_dedupe_key(source: dict) -> str:
    st = source.get("type")
    if st == "kb":
        return f"kb:{source.get('path')}"
    if st == "conversation":
        return (
            f"conversation:{source.get('cid')}:{source.get('message_id')}:"
            f"{source.get('start_char')}:{source.get('end_char')}"
        )
    return f"{st}:{source.get('url')}"


def extend_sources(all_sources: list[dict], new_sources: list[dict]) -> None:
    seen = {source_dedupe_key(s) for s in all_sources}
    for s in new_sources:
        key = source_dedupe_key(s)
        if key not in seen:
            all_sources.append(s)
            seen.add(key)
```

`orchestrator.py`：删除本地 `_source_key`/`_extend_sources`，改为 `from app.engine.source_key import source_dedupe_key, extend_sources`（`_extend_sources` 改名为直接调 `extend_sources`）。

`routes.py` `_TimelineAccumulator`：

```python
from app.engine.source_key import extend_sources

# tool_result 分支末尾，替换 self.all_sources.extend(block["sources"])
extend_sources(self.all_sources, block.get("sources") or [])

# done 分支，替换 json.dumps 去重
extend_sources(self.all_sources, data.get("sources") or [])
```

- [ ] **Step 4: 跑通并提交**

```bash
cd backend && python -m pytest tests/test_source_key.py tests/test_agent_orchestrator.py -q
git add backend/app/engine/source_key.py backend/app/engine/agent/orchestrator.py backend/app/api/routes.py backend/tests/test_source_key.py
git commit -m "fix: unify conversation source dedupe key across orchestrator and timeline"
```

---

## Task 2: read_conversation_context 工具

**Files:**
- Create: `backend/app/engine/conversation_context.py`
- Modify: `backend/app/engine/conversations.py`（`get_message_window`）
- Modify: `backend/app/engine/agent/tools.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_conversation_context.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_conversation_context.py
from app.engine.conversation_context import read_conversation_context
from app.engine.conversations import ConversationStore
from app.engine.derivation_worker import DerivationWorker
from app.index.conversation_fts import ConversationFTS


def _store(tmp_path):
    return ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")


def test_read_context_before_after_and_mask(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid, "key=sk-abcdefghijklmnopqrstuvwxyz012345", client_message_id="c1", observation_allowed=False
    )
    store.finalize_turn(
        turn["turn_id"],
        assistant_text="收到，已记录",
        timeline=[],
        sources=[],
    )
    turn2 = store.begin_turn(cid, "第二条用户消息", client_message_id="c2", observation_allowed=False)
    store.finalize_turn(turn2["turn_id"], assistant_text="好的", timeline=[], sources=[])
    msgs = store.get(cid)["messages"]
    anchor_id = msgs[0]["id"]

    out = read_conversation_context(
        store,
        conversation_id=cid,
        message_id=anchor_id,
        before_messages=0,
        after_messages=1,
        max_chars=12000,
    )
    assert out["anchor"]["message_id"] == anchor_id
    assert len(out["messages"]) == 2
    masked = out["messages"][0]["text"]
    assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in masked
    assert "•" in masked
    assert out["messages"][0]["offset_version"] == "unicode-codepoint-v1"
    assert out["messages"][0]["source_available"] is True


def test_read_context_clamps_before_after(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(cid, "only", client_message_id="c1", observation_allowed=False)
    mid = turn["user_message"]["id"]
    out = read_conversation_context(
        store, cid, mid, before_messages=99, after_messages=99, max_chars=12000
    )
    assert len(out["messages"]) == 1


def test_read_context_truncates_at_char_cap(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    long_text = "甲" * 8000
    turn = store.begin_turn(cid, long_text, client_message_id="c1", observation_allowed=False)
    store.finalize_turn(turn["turn_id"], assistant_text="乙" * 8000, timeline=[], sources=[])
    turn2 = store.begin_turn(cid, "anchor", client_message_id="c2", observation_allowed=False)
    anchor = turn2["user_message"]["id"]
    out = read_conversation_context(store, cid, anchor, before_messages=10, after_messages=0, max_chars=12000)
    total = sum(len(m["text"]) for m in out["messages"])
    assert total <= 12000
    assert out["truncated"] is True
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_conversation_context.py -q
```

Expected: FAIL

- [ ] **Step 3: 实现**

```python
# backend/app/engine/conversation_context.py
from __future__ import annotations

from app.engine.secrets import mask_secrets


def read_conversation_context(
    store,
    *,
    conversation_id: str,
    message_id: str,
    before_messages: int = 2,
    after_messages: int = 2,
    max_chars: int = 12000,
) -> dict:
    before_messages = max(0, min(10, int(before_messages)))
    after_messages = max(0, min(10, int(after_messages)))
    window = store.get_message_window(
        conversation_id,
        message_id,
        before_messages=before_messages,
        after_messages=after_messages,
    )
    out_messages: list[dict] = []
    used = 0
    truncated = False
    for row in window:
        raw_text = row.get("text") or ""
        masked, _ = mask_secrets(raw_text)
        budget = max_chars - used
        if budget <= 0:
            truncated = True
            break
        if len(masked) > budget:
            masked = masked[:budget]
            truncated = True
        used += len(masked)
        out_messages.append({
            "message_id": row["id"],
            "role": row["role"],
            "ts": row.get("ts"),
            "text": masked,
            "offset_version": "unicode-codepoint-v1",
            "source_available": True,
        })
        if truncated:
            break
    return {
        "summary": f"{len(out_messages)} 条消息，约 {used} 字符",
        "messages": out_messages,
        "anchor": {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "offset_version": "unicode-codepoint-v1",
        },
        "truncated": truncated,
    }
```

`conversations.py` 新增：

```python
def get_message_window(
    self,
    cid: str,
    message_id: str,
    *,
    before_messages: int = 0,
    after_messages: int = 0,
) -> list[dict]:
    with self._lock:
        self._conversation_row(cid)
        anchor = self.conn.execute(
            "SELECT seq FROM messages WHERE id = ? AND conversation_id = ?",
            (message_id, cid),
        ).fetchone()
        if anchor is None:
            raise KeyError(message_id)
        seq = int(anchor["seq"])
        rows = self.conn.execute(
            """
            SELECT * FROM messages
            WHERE conversation_id = ?
              AND seq BETWEEN ? AND ?
              AND role IN ('user', 'assistant')
            ORDER BY seq ASC
            """,
            (cid, seq - before_messages, seq + after_messages),
        ).fetchall()
    return [self._message_row_to_dict(r) for r in rows]
```

`tools.py` 增加工具定义与 handler：

```python
# TOOL_DEFINITIONS 追加
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
}

def _read_conversation_context(self, args: dict) -> dict:
    try:
        return read_conversation_context(
            self.conversations,
            conversation_id=args["conversation_id"],
            message_id=args["message_id"],
            before_messages=args.get("before_messages", 2),
            after_messages=args.get("after_messages", 2),
            max_chars=self.settings.conversation_context_max_chars,
        )
    except KeyError:
        return {
            "summary": "消息或会话不存在",
            "messages": [],
            "anchor": {"message_id": args.get("message_id")},
            "truncated": False,
            "error": "not_found",
        }
```

`config.py`：`conversation_context_max_chars: int = 12000`

- [ ] **Step 4: 跑通并提交**

```bash
cd backend && python -m pytest tests/test_conversation_context.py tests/test_agent_tools.py -q
git add backend/app/engine/conversation_context.py backend/app/engine/conversations.py backend/app/engine/agent/tools.py backend/app/config.py backend/tests/test_conversation_context.py
git commit -m "feat: add read_conversation_context tool with secret mask and char cap"
```

---

## Task 3: Retriever 补强（min_vector_score + 相邻合并 + 同源分组）

**Files:**
- Create: `backend/app/engine/provenance.py`
- Modify: `backend/app/index/types.py`
- Modify: `backend/app/engine/retriever.py`
- Modify: `backend/app/deps.py`（向 Retriever 注入 `repo`）
- Test: `backend/tests/test_retriever_provenance.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_retriever_provenance.py
from app.engine.provenance import conversation_ids_from_meta, merge_adjacent_conversation_hits, group_provenance
from app.index.types import Hit


def test_conversation_ids_from_meta_list_and_legacy():
    assert conversation_ids_from_meta({"conversation_ids": ["a", "b"]}) == ["a", "b"]
    assert conversation_ids_from_meta({"conversation_id": "legacy"}) == ["legacy"]


def test_merge_adjacent_chunks_same_message():
    hits = [
        Hit("a", "hel", 1.0, "conv:c1", message_id="m1", start_char=0, end_char=3),
        Hit("b", "lo", 0.9, "conv:c1", message_id="m1", start_char=3, end_char=5),
        Hit("c", "x", 0.8, "conv:c2", message_id="m2", start_char=0, end_char=1),
    ]
    merged = merge_adjacent_conversation_hits(hits)
    assert len(merged) == 2
    assert merged[0].chunk == "hello"
    assert merged[0].end_char == 5


def test_group_provenance_links_summary_and_message():
    kb = Hit("d1", "摘要段", 1.0, "娱乐/盘点.md")
    msg = Hit("c1", "原文", 0.9, "conv:abc", message_id="m1", start_char=0, end_char=2)
    doc_ids = {"娱乐/盘点.md": ["abc"]}
    groups = group_provenance([kb, msg], doc_conversation_ids=doc_ids)
    assert len(groups) == 1
    assert groups[0]["group_key"] == "conversation:abc"
    assert groups[0]["nav_preference"] == "summary"
    assert len(groups[0]["hits"]) == 2
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_retriever_provenance.py -q
```

Expected: FAIL

- [ ] **Step 3: 实现**

```python
# backend/app/engine/provenance.py
from __future__ import annotations

from app.index.types import Hit


def conversation_ids_from_meta(meta: dict) -> list[str]:
    ids = meta.get("conversation_ids")
    if isinstance(ids, list):
        return [str(x) for x in ids if x]
    legacy = meta.get("conversation_id")
    return [str(legacy)] if legacy else []


def merge_adjacent_conversation_hits(hits: list[Hit]) -> list[Hit]:
    conv_hits = [h for h in hits if h.message_id is not None]
    other = [h for h in hits if h.message_id is None]
    conv_hits.sort(key=lambda h: (h.source, h.message_id or "", h.start_char or 0))
    merged: list[Hit] = []
    for h in conv_hits:
        if (
            merged
            and merged[-1].message_id == h.message_id
            and merged[-1].source == h.source
            and merged[-1].end_char == h.start_char
        ):
            prev = merged[-1]
            merged[-1] = Hit(
                doc_id=prev.doc_id,
                chunk=prev.chunk + h.chunk,
                score=max(prev.score, h.score),
                source=prev.source,
                message_id=prev.message_id,
                start_char=prev.start_char,
                end_char=h.end_char,
                offset_version=prev.offset_version,
            )
        else:
            merged.append(h)
    return other + merged


def group_provenance(
    hits: list[Hit],
    *,
    doc_conversation_ids: dict[str, list[str]],
) -> list[dict]:
    buckets: dict[str, list[Hit]] = {}
    for h in hits:
        if h.source.startswith("conv:"):
            cid = h.source[5:]
            buckets.setdefault(f"conversation:{cid}", []).append(h)
        elif h.source in doc_conversation_ids:
            for cid in doc_conversation_ids[h.source]:
                buckets.setdefault(f"conversation:{cid}", []).append(h)
    groups: list[dict] = []
    for key, group_hits in buckets.items():
        if len(group_hits) < 2:
            continue
        has_summary = any(not gh.source.startswith("conv:") for gh in group_hits)
        has_message = any(gh.source.startswith("conv:") for gh in group_hits)
        if has_summary and has_message:
            groups.append({
                "group_key": key,
                "nav_preference": "summary",
                "hits": group_hits,
            })
    return groups
```

`retriever.py` 变更要点：

1. `__init__` 增加 `repo: KnowledgeRepo | None = None`
2. `_conv_vector_lane` 在 `hits = [self._conversation_hit(ch) for ch in raw]` 后加 `hits = [h for h in hits if h.score >= self.min_score]`
3. `search()` 在 `page_hits` 切片后调用 `merge_adjacent_conversation_hits`
4. 若 `self.repo`，为 KB hits 批量 `read_doc` 解析 frontmatter 构建 `doc_conversation_ids`
5. `SearchPage` 增加可选字段 `provenance_groups: list[dict] = field(default_factory=list)`

`tools._search_kb` 把 `page.provenance_groups` 透传到 tool result（模型可见，前端可忽略）。

- [ ] **Step 4: 补会话向量低分过滤测试并提交**

```python
# tests/test_retriever_provenance.py 追加
from app.engine.retriever import Retriever
from app.index.conversation_vector import ConversationVector, ConversationVectorHit
from app.index.fulltext import FullTextIndex
from app.index.message_chunk import MessageChunk
from app.index.revision import IndexRevision
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient


def test_conv_vector_lane_respects_min_score(tmp_path, monkeypatch):
    llm = FakeLLMClient(embed_dim=8)
    retr = Retriever(
        VectorIndex(tmp_path / "vec"),
        FullTextIndex(tmp_path / "fts.db"),
        llm,
        min_score=0.45,
        conversation_vector=ConversationVector(tmp_path / "vec"),
        index_revision=IndexRevision(tmp_path / "rev.txt"),
    )
    cv = retr.conversation_vector
    assert cv is not None
    cv.upsert_message_chunks(
        conversation_id="c1",
        message_id="low",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, "低分命中", 0, 4)],
        embeddings=[[0.01] * 8],
    )
    cv.upsert_message_chunks(
        conversation_id="c1",
        message_id="high",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, "高分命中", 0, 4)],
        embeddings=[[1.0] * 8],
    )

    def fake_query(embedding, k=5, *, conversation_id=None):
        return [
            ConversationVectorHit("a", "c1", "low", "user", 0, 4, "低分", 0.1),
            ConversationVectorHit("b", "c1", "high", "user", 0, 4, "高分", 0.95),
        ]

    monkeypatch.setattr(cv, "query", fake_query)
    ids, hit_map = retr._conv_vector_lane("q", 5, conversation_id="c1")
    assert ids == ["b"]
    assert "a" not in hit_map
```

```bash
cd backend && python -m pytest tests/test_retriever_provenance.py tests/test_retriever_rrf.py -q
git add backend/app/engine/provenance.py backend/app/index/types.py backend/app/engine/retriever.py backend/app/deps.py backend/app/engine/agent/tools.py backend/tests/test_retriever_provenance.py
git commit -m "feat: retriever provenance grouping, adjacent merge, and conv vector min score"
```

---

## Task 4: Summary provenance API 与 frontmatter

**Files:**
- Modify: `backend/app/engine/conversations.py:281-295`
- Modify: `backend/app/engine/organizer.py:729-775`
- Modify: `backend/app/storage/repo.py`（可选 `read_meta` 薄封装）
- Test: `backend/tests/test_summary_provenance.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_summary_provenance.py
from app.engine.conversations import ConversationStore
from app.engine.organizer import Organizer
from app.storage.repo import KnowledgeRepo


def test_get_conversation_includes_summaries_array(tmp_path):
    store = ConversationStore(tmp_path / "kb" / ".kb" / "conversations")
    cid = store.create()
    store.mark_summarized(cid, "娱乐/盘点.md")
    conv = store.get(cid)
    assert "summaries" in conv
    assert len(conv["summaries"]) == 1
    assert conv["summaries"][0]["doc_path"] == "娱乐/盘点.md"
    assert conv["summaries"][0]["status"] == "current"
    assert conv["summary_path"] == "娱乐/盘点.md"  # 兼容


def test_append_message_marks_summary_stale(tmp_path):
    store = ConversationStore(tmp_path / "kb" / ".kb" / "conversations")
    cid = store.create()
    turn = store.begin_turn(cid, "first", client_message_id="c1", observation_allowed=False)
    store.finalize_turn(turn["turn_id"], assistant_text="ok", timeline=[], sources=[])
    store.mark_summarized(cid, "娱乐/盘点.md")
    store.begin_turn(cid, "second", client_message_id="c2", observation_allowed=False)
    summaries = store.list_summaries(cid)
    assert any(s["status"] == "stale" for s in summaries)


def test_organizer_writes_conversation_ids_list(tmp_path):
    from app.engine.organizer import Organizer, PlacementDecision
    from app.engine.pending import PendingStore
    from app.engine.retriever import Retriever
    from app.index.fulltext import FullTextIndex
    from app.index.indexer import Indexer
    from app.index.vector import VectorIndex
    from app.models.llm import FakeLLMClient
    from app.storage.repo import KnowledgeRepo

    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    llm = FakeLLMClient(chat_responses=["# 标题\n\n正文"], embed_dim=8)
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    org = Organizer(
        repo=repo,
        retriever=Retriever(vi, fi, llm),
        indexer=Indexer(vi, fi, llm),
        pending=PendingStore(tmp_path / "pending.json"),
        llm=llm,
    )
    decision = PlacementDecision(
        action="new",
        rel_path="娱乐/盘点.md",
        title="盘点",
        category="娱乐",
        tags=[],
        ambiguous=False,
        reason="test",
    )
    org._apply(decision, "正文\n", conversation_id="cid-abc")
    doc = repo.read_doc("娱乐/盘点.md")
    assert doc.meta.get("conversation_ids") == ["cid-abc"]
    assert "conversation_id" not in doc.meta
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_summary_provenance.py -q
```

Expected: FAIL（`summaries` 字段缺失或 frontmatter 仍为单值 `conversation_id`）

- [ ] **Step 3: 实现**

`conversations._conv_to_dict`：

```python
def _conv_to_dict(self, row: sqlite3.Row) -> dict:
  ...
  summaries = self.list_summaries(cid)
  return {
      ...
      "summaries": summaries,
      "summary_path": summary_path,
      "summarized": summarized,
  }
```

`organizer._apply` frontmatter 助手：

```python
def _conversation_ids_meta(meta: dict, conversation_id: str | None) -> dict:
    if not conversation_id:
        return meta
    existing = meta.get("conversation_ids")
    if isinstance(existing, list):
        ids = list(dict.fromkeys([*existing, conversation_id]))
    else:
        legacy = meta.get("conversation_id")
        ids = list(dict.fromkeys([x for x in (legacy, conversation_id) if x]))
    meta = {k: v for k, v in meta.items() if k not in ("conversation_id",)}
    meta["conversation_ids"] = ids
    meta["source"] = "conversation"
    return meta
```

在 merge 与 new 分支写入前调用 `_conversation_ids_meta`。

- [ ] **Step 4: 跑通并提交**

```bash
cd backend && python -m pytest tests/test_summary_provenance.py tests/test_summarize.py -q
git add backend/app/engine/conversations.py backend/app/engine/organizer.py backend/tests/test_summary_provenance.py
git commit -m "feat: expose summaries array and conversation_ids frontmatter provenance"
```

---

## Task 5: 长会话分段总结

**Files:**
- Modify: `backend/app/engine/organizer.py`（`summarize_conversation`、`_synthesize_segmented`）
- Modify: `backend/app/engine/conversations.py`（`iter_transcript_segments`）
- Modify: `backend/app/config.py`（`summarize_segment_chars`）
- Test: `backend/tests/test_summarize_segmented.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_summarize_segmented.py
from app.engine.conversations import ConversationStore


def test_iter_transcript_segments_splits_on_message_boundary(tmp_path):
    store = ConversationStore(tmp_path / "kb" / ".kb" / "conversations")
    cid = store.create()
    for i in range(5):
        t = store.begin_turn(cid, f"用户消息{i}" + ("×" * 200), client_message_id=f"c{i}", observation_allowed=False)
        store.finalize_turn(t["turn_id"], assistant_text="回复", timeline=[], sources=[])
    conv = store.get(cid)
    segments = list(ConversationStore.iter_transcript_segments(conv, max_chars=500))
    assert len(segments) >= 2
    for seg in segments:
        assert seg["messages"]
        assert seg["first_message_id"] != seg["last_message_id"] or len(seg["messages"]) == 1


def test_summarize_long_conversation_calls_merge(tmp_path):
    from app.config import Settings
    from app.engine.organizer import Organizer
    from app.engine.pending import PendingStore
    from app.engine.retriever import Retriever
    from app.index.fulltext import FullTextIndex
    from app.index.indexer import Indexer
    from app.index.vector import VectorIndex
    from app.models.llm import FakeLLMClient
    from app.storage.repo import KnowledgeRepo

    calls: list[int] = []

    class CountingLLM(FakeLLMClient):
        def chat(self, messages, big=False):
            calls.append(len(messages))
            return "段摘要或终稿\n"

    store = ConversationStore(tmp_path / "kb" / ".kb" / "conversations")
    cid = store.create()
    for i in range(8):
        t = store.begin_turn(
            cid, "内容" + ("长" * 4000), client_message_id=f"c{i}", observation_allowed=False
        )
        store.finalize_turn(t["turn_id"], assistant_text="收到", timeline=[], sources=[])
    conv = store.get(cid)
    llm = CountingLLM(chat_responses=[], embed_dim=8)
    repo = KnowledgeRepo(tmp_path / "kb", protected_dirs=("系统",))
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    org = Organizer(
        repo=repo,
        retriever=Retriever(vi, fi, llm),
        indexer=Indexer(vi, fi, llm),
        pending=PendingStore(tmp_path / "pending.json"),
        llm=llm,
    )
    org.settings = Settings(summarize_segment_chars=5000)
    transcript = ConversationStore.full_transcript(conv)
    assert len(transcript) > 5000
    monkeypatch_decision = '{"action":"new","rel_path":"娱乐/长会话.md","title":"长会话","category":"娱乐","tags":[],"ambiguous":false,"reason":"归档"}'
    llm.chat_responses = [monkeypatch_decision]
    result = org.summarize_conversation(
        transcript, conv=conv, conversation_id=cid, system_rules=""
    )
    assert result.status == "saved"
    assert len(calls) >= 2
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_summarize_segmented.py -q
```

Expected: FAIL

- [ ] **Step 3: 实现**

`conversations.py`：

```python
@classmethod
def iter_transcript_segments(cls, conv: dict, *, max_chars: int) -> Iterable[dict]:
    batch: list[dict] = []
    used = 0
    for msg in conv.get("messages", []):
        if msg.get("role") not in ("user", "assistant"):
            continue
        piece = cls._message_transcript_line(msg)
        if not piece:
            continue
        plen = len(piece)
        if batch and used + plen > max_chars:
            yield {
                "messages": batch,
                "first_message_id": batch[0]["id"],
                "last_message_id": batch[-1]["id"],
                "text": "\n\n".join(cls._message_transcript_line(m) for m in batch),
            }
            batch, used = [], 0
        batch.append(msg)
        used += plen + 2
    if batch:
        yield {
            "messages": batch,
            "first_message_id": batch[0]["id"],
            "last_message_id": batch[-1]["id"],
            "text": "\n\n".join(cls._message_transcript_line(m) for m in batch),
        }
```

`organizer.summarize_conversation` 增加 `conv: dict | None = None` 参数（`routes.py` / `tools._summarize_conversation` 传入 `store.get(cid)`）：

```python
def summarize_conversation(
    self,
    transcript: str,
    *,
    conv: dict | None = None,
    hint_path: str | None = None,
    system_rules: str = "",
    conversation_id: str | None = None,
) -> IngestResult:
    if conv is None:
        conv = {"messages": []}
    if len(transcript) <= self.settings.summarize_segment_chars:
        body = self._synthesize(transcript, system_rules)
    else:
        segments = list(
            ConversationStore.iter_transcript_segments(
                conv, max_chars=self.settings.summarize_segment_chars
            )
        )
        partials = [self._synthesize_segment(seg["text"], system_rules, seg) for seg in segments]
        body = self._synthesize_merge_segments(partials, system_rules)
```

`_synthesize_segment` 在 prompt 中注明 `first_message_id`/`last_message_id`；`_synthesize_merge_segments` 将多段摘要合并为终稿。`mark_summarized` 的 `covered_through_message_id` 仍用最后一条消息 id。

- [ ] **Step 4: 跑通并提交**

```bash
cd backend && python -m pytest tests/test_summarize_segmented.py tests/test_summarize.py -q
git add backend/app/engine/organizer.py backend/app/engine/conversations.py backend/app/config.py backend/tests/test_summarize_segmented.py
git commit -m "feat: chunked conversation summarize with message-boundary segments"
```

---

## Task 6: 前端消息锚点与 unicode 区间高亮

**Files:**
- Create: `frontend/src/utils/unicodeHighlight.ts`
- Create: `frontend/src/components/chat/MessageRangeHighlight.tsx`
- Modify: `frontend/src/components/chat/ChatMessageRow.tsx`
- Modify: `frontend/src/api.ts`（`ChatMessage.id`）
- Test: `frontend/src/utils/unicodeHighlight.test.ts`

- [ ] **Step 1: 写失败测试**

```typescript
// frontend/src/utils/unicodeHighlight.test.ts
import { describe, expect, it } from "vitest";
import { sliceByCodepoint, splitForHighlight } from "./unicodeHighlight";

describe("unicodeHighlight", () => {
  it("slices by unicode codepoint not utf16 code unit", () => {
    const text = "a😀b";
    expect(sliceByCodepoint(text, 1, 2)).toBe("😀");
    expect(sliceByCodepoint(text, 0, 3)).toBe("a😀b");
  });

  it("splitForHighlight returns before/highlight/after", () => {
    const parts = splitForHighlight("hello", 1, 4);
    expect(parts).toEqual({ before: "h", highlight: "ell", after: "o" });
  });
});
```

- [ ] **Step 2: 跑失败**

```bash
cd frontend && npm test -- unicodeHighlight.test.ts
```

Expected: FAIL

- [ ] **Step 3: 实现**

```typescript
// frontend/src/utils/unicodeHighlight.ts
export function sliceByCodepoint(text: string, start: number, end: number): string {
  const chars = Array.from(text);
  return chars.slice(start, end).join("");
}

export function splitForHighlight(
  text: string,
  start: number,
  end: number,
): { before: string; highlight: string; after: string } {
  const chars = Array.from(text);
  return {
    before: chars.slice(0, start).join(""),
    highlight: chars.slice(start, end).join(""),
    after: chars.slice(end).join(""),
  };
}
```

```tsx
// frontend/src/components/chat/MessageRangeHighlight.tsx
import { splitForHighlight } from "../../utils/unicodeHighlight";

export function MessageRangeHighlight({
  text,
  start,
  end,
}: {
  text: string;
  start: number;
  end: number;
}) {
  const { before, highlight, after } = splitForHighlight(text, start, end);
  return (
    <span>
      {before}
      <mark className="message-range-highlight">{highlight}</mark>
      {after}
    </span>
  );
}
```

`ChatMessageRow.tsx` 根节点加 `data-message-id={m.id}`；用户纯文本与 assistant 顶层 `m.text` 在传入 `highlightRange` 时用 `MessageRangeHighlight`。

`api.ts`：`ChatMessage` 增加 `id?: string`。

CSS（`frontend/src/index.css` 或现有 chat 样式文件）：

```css
.message-range-highlight {
  background: rgba(255, 214, 102, 0.55);
  padding: 0 1px;
  border-radius: 2px;
}
```

- [ ] **Step 4: 跑通并提交**

```bash
cd frontend && npm test -- unicodeHighlight.test.ts
git add frontend/src/utils/unicodeHighlight.ts frontend/src/utils/unicodeHighlight.test.ts frontend/src/components/chat/MessageRangeHighlight.tsx frontend/src/components/chat/ChatMessageRow.tsx frontend/src/api.ts
git commit -m "feat: unicode codepoint message range highlight and anchors"
```

---

## Task 7: 前端会话来源跳转

**Files:**
- Create: `frontend/src/hooks/chat/useConversationJump.ts`
- Modify: `frontend/src/hooks/chat/useChatConversation.ts`
- Modify: `frontend/src/components/Chat.tsx:279-290`
- Modify: `frontend/src/App.tsx:78-85`
- Modify: `frontend/src/hooks/app/useConversationShell.ts`
- Test: `frontend/src/hooks/chat/useConversationJump.test.ts`

- [ ] **Step 1: 写失败测试**

```typescript
// frontend/src/hooks/chat/useConversationJump.test.ts
import { describe, expect, it, vi } from "vitest";
import { scrollToMessageHighlight } from "./useConversationJump";

describe("scrollToMessageHighlight", () => {
  it("scrolls to data-message-id and applies highlight class", () => {
    const el = document.createElement("div");
    el.dataset.messageId = "m1";
    document.body.appendChild(el);
    const scrollIntoView = vi.fn();
    el.scrollIntoView = scrollIntoView;
    scrollToMessageHighlight("m1", { start: 0, end: 2 });
    expect(scrollIntoView).toHaveBeenCalled();
    document.body.removeChild(el);
  });
});
```

- [ ] **Step 2: 跑失败**

```bash
cd frontend && npm test -- useConversationJump.test.ts
```

Expected: FAIL

- [ ] **Step 3: 实现**

```typescript
// frontend/src/hooks/chat/useConversationJump.ts
export type JumpTarget = {
  conversationId: string;
  messageId: string;
  startChar?: number;
  endChar?: number;
  offsetVersion?: string;
};

export function scrollToMessageHighlight(
  messageId: string,
  range?: { start: number; end: number },
): boolean {
  const el = document.querySelector(`[data-message-id="${messageId}"]`);
  if (!el) return false;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("chat-message-jump-flash");
  window.setTimeout(() => el.classList.remove("chat-message-jump-flash"), 3000);
  if (range) {
    el.dispatchEvent(
      new CustomEvent("highlight-range", {
        detail: range,
        bubbles: true,
      }),
    );
  }
  return true;
}
```

`useChatConversation` 增加 `pendingJump: JumpTarget | null` 与 `requestJump(target)`；消息加载完成后若 `pendingJump?.conversationId === conversationId` 则 `requestAnimationFrame` 调 `scrollToMessageHighlight`。

`Chat.tsx` `handleOpenSource`：

```typescript
function handleOpenSource(src: SourceRef) {
  if (src.type === "conversation" && src.message_id) {
    onJumpToConversation?.({
      conversationId: src.cid,
      messageId: src.message_id,
      startChar: src.start_char,
      endChar: src.end_char,
      offsetVersion: src.offset_version,
    });
    return;
  }
  if (src.type === "kb" && src.path) {
    openDoc(src.path, src.excerpt);
    return;
  }
  ...
}
```

`App.tsx`：

```typescript
function handleJumpToConversation(target: JumpTarget) {
  if (conversation.activeConversationId !== target.conversationId) {
    conversation.setActiveConversationId(target.conversationId);
  }
  conversation.requestJump(target);
  doc.requestCloseDocPreview();
}

// Chat props
onJumpToConversation={handleJumpToConversation}
```

删除 `if (src.type === "conversation") return;` 早退。

`ChatMessageRow` 监听 `highlight-range` 事件，在对应消息上渲染 `MessageRangeHighlight`（仅当 `offset_version` 缺省或为 `unicode-codepoint-v1`）。

- [ ] **Step 4: 手动冒烟 + 提交**

```bash
cd frontend && npm test -- useConversationJump.test.ts
cd backend && python -m pytest -q
git add frontend/src/hooks/chat/useConversationJump.ts frontend/src/hooks/chat/useConversationJump.test.ts frontend/src/hooks/chat/useChatConversation.ts frontend/src/components/Chat.tsx frontend/src/App.tsx frontend/src/hooks/app/useConversationShell.ts
git commit -m "feat: jump to conversation message source with unicode range highlight"
```

---

## 1C 验收清单

| 验收项 | Task |
|--------|------|
| 来源去重键三处一致（orchestrator / timeline / frontend） | 1 |
| `read_conversation_context` 0–10 条、12k 上限、secret 脱敏 | 2 |
| 会话向量 lane 应用 `min_vector_score` | 3 |
| 相邻 message chunk 合并 | 3 |
| summary 文档与原始消息同源分组 + `nav_preference` | 3 |
| `GET /conversations/{id}` 返回 `summaries[]` | 4 |
| 新消息追加后 current summary → `stale` | 4 |
| 总结 frontmatter `conversation_ids` 列表 | 4 |
| 长会话分段总结 + 归并 | 5 |
| 消息 DOM `data-message-id` | 6 |
| `Array.from` code point 高亮 | 6 |
| 点击 conversation 来源跳转并高亮区间 | 7 |
| 不做 `记忆.md` / `memory.db` / `observe_memory` | 范围外 |

---

## Plan Self-Review

1. **Spec coverage (1C):** §6.3 message+range 全链路 → T1；`read_conversation_context` → T2；cursor（revision 已有）+ 检索增强 → T3；§6.4 provenance/stale/frontmatter → T4；长会话分层总结 → T5；前端跳转+unicode → T6–T7。§16 阶段 1C 四项全部覆盖。
2. **Placeholders:** 无 TBD、无 `...` 测试占位。
3. **Type consistency:** `source_dedupe_key` 与 `dedupeSources` 键格式一致；`offset_version` 固定 `unicode-codepoint-v1`；`JumpTarget` 字段与 `SourceRef` conversation 分支对齐；`summaries[]` 元素字段与 `list_summaries()` 一致。

---

## 执行方式

在 `master` 上按 Task 1→7 顺序 TDD 实施；每 Task 提交一次。1C 验收通过后进入阶段 2 计划。

**Plan complete and saved to `docs/superpowers/plans/2026-07-14-second-brain-phase-1c.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — 每个 Task 派发全新 subagent，Task 间做代码审查，迭代快。

**2. Inline Execution** — 本会话用 executing-plans 按检查点批量执行。

**Which approach?**
