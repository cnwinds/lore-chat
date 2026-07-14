# 第二大脑 · 阶段 1B 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为会话消息建立与 FTS 同 ID 的 Vector v2，并用四路 RRF（知识 FTS / 知识 Vector / 会话 FTS / 会话 Vector）合并检索；向量故障时 FTS 仍可用；提供幂等向量回填与 `index_revision` 绑定的 cursor。

**Architecture:** 新建 `ConversationVector`（Chroma collection `conversation_chunks_v2`，`upsert` 语义）；`begin_turn`/`finalize_turn` 同时入队 `index_fts` 与 `index_vector`；`DerivationWorker` 分支处理 embedding；`Retriever.search` 改为四路召回 + RRF，返回 `SearchPage(hits, has_more, next_cursor, index_revision)`；扩展 `search_kb` 的 `scope`/`conversation_id`/`cursor`。本阶段不做前端跳转、不做 `read_conversation_context`、不做 `记忆.md`。

**Tech Stack:** Python 3.12 / FastAPI / SQLite / Chroma / pytest；现有 `LLMClient.embed`。

**Spec:** [2026-07-13-memory-layer-design.md](../specs/2026-07-13-memory-layer-design.md) §6.2–6.3、§7.4 outbox、§16 阶段 1B。

**前置：** 阶段 1A 已合并入 `master`。

**后续（本文件不实现）：** 1C 来源跳转与 summary provenance；2–4 记忆层。

---

## 文件结构（1B）

| 文件 | 职责 |
|------|------|
| `backend/app/index/conversation_vector.py` | 会话向量索引 upsert/query/delete |
| `backend/app/engine/rrf.py` | Reciprocal Rank Fusion 纯函数 |
| `backend/app/engine/retriever.py` | 四路召回 + RRF + cursor/revision |
| `backend/app/engine/derivation_worker.py` | 处理 `index_vector` |
| `backend/app/engine/conversations.py` | 入队 `index_vector`；bump `index_revision`；删除清向量 |
| `backend/app/engine/conversation_backfill.py` | 向量回填 + checkpoint |
| `backend/app/engine/agent/tools.py` | `search_kb` 扩展参数 |
| `backend/app/config.py` / `deps.py` / `main.py` | 装配 |
| `backend/tests/test_*.py` | 对应测试 |

---

## 决策记录（1B 冻结）

| 项 | 决策 |
|----|------|
| Vector 存储 | 独立 Chroma collection `conversation_chunks_v2`，与 KB collection `kbs` 同 PersistentClient 目录或子目录均可；推荐 `index/vec` 同 client 不同 collection |
| chunk ID | 与 FTS 一致：`conv:{cid}:msg:{mid}:chunk:{i}` |
| upsert | delete-by-message 再 add（与 ConversationFTS 一致） |
| RRF | `score = Σ 1/(k_rrf + rank)`，默认 `k_rrf=60`；同分按 doc_id 稳定排序 |
| 每路候选窗口 | 默认 `lane_candidate_k = max(20, k*4)` |
| index_revision | 整数存 `knowledge/.kb/index/revision.txt`（或 sqlite meta）；任意会话 FTS/向量 upsert/delete 时 +1 |
| cursor | base64url(json `{q, filters, rev, offset}`)；rev 不匹配 → 工具返回 `cursor_expired` |
| 同源分组 / 邻近合并 | **留给 1C**；1B 只做 RRF + 逻辑 ID 去重（同 doc_id 留最高 RRF） |
| search_kb 新参 | `scope`/`conversation_id`/`cursor`；`date_from`/`date_to` 可先接受并忽略过滤（测标记 skip）或最小实现 |

---

## Task 1: ConversationVector

**Files:**
- Create: `backend/app/index/conversation_vector.py`
- Test: `backend/tests/test_conversation_vector.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_conversation_vector.py
from app.index.conversation_vector import ConversationVector
from app.index.message_chunk import MessageChunk


def test_upsert_and_query_by_embedding(tmp_path):
    idx = ConversationVector(tmp_path / "vec")
    chunks = [MessageChunk(index=0, text="漫剧剪辑工具", start_char=0, end_char=6)]
    emb = [[0.1] * 8]  # FakeLLM 可用任意维；测试里直接传入
    # 为简化：ConversationVector.upsert_message_chunks 接受预计算 embeddings
    idx.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="t",
        chunks=chunks,
        embeddings=[[0.2] * 8],
    )
    hits = idx.query([0.2] * 8, k=5)
    assert len(hits) >= 1
    assert hits[0].message_id == "m1"
    assert hits[0].conversation_id == "c1"
    assert hits[0].chunk_id.startswith("conv:c1:msg:m1:chunk:")


def test_upsert_replaces_same_message(tmp_path):
    idx = ConversationVector(tmp_path / "vec")
    c1 = [MessageChunk(index=0, text="旧内容AAA", start_char=0, end_char=5)]
    c2 = [MessageChunk(index=0, text="新内容BBB", start_char=0, end_char=5)]
    idx.upsert_message_chunks(
        conversation_id="c1", message_id="m1", role="user", ts="t",
        conversation_title="", chunks=c1, embeddings=[[0.1] * 8],
    )
    idx.upsert_message_chunks(
        conversation_id="c1", message_id="m1", role="user", ts="t",
        conversation_title="", chunks=c2, embeddings=[[0.9] * 8],
    )
    # 同 message 不应残留两条
    assert idx.count_for_message("c1", "m1") == 1


def test_delete_conversation(tmp_path):
    idx = ConversationVector(tmp_path / "vec")
    idx.upsert_message_chunks(
        conversation_id="c1", message_id="m1", role="user", ts="t",
        conversation_title="", chunks=[MessageChunk(0, "hello world xx", 0, 14)],
        embeddings=[[0.3] * 8],
    )
    idx.delete_conversation("c1")
    assert idx.query([0.3] * 8, k=5) == []
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_conversation_vector.py -q
```

Expected: FAIL / ImportError

- [ ] **Step 3: 实现**

```python
# backend/app/index/conversation_vector.py
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import chromadb

from app.index.message_chunk import MessageChunk


@dataclass
class ConversationVectorHit:
    chunk_id: str
    conversation_id: str
    message_id: str
    role: str
    start_char: int
    end_char: int
    text: str
    score: float
    offset_version: str = "unicode-codepoint-v1"


class ConversationVector:
    COLLECTION = "conversation_chunks_v2"

    def __init__(self, path: str | Path):
        self._path = str(path)
        Path(self._path).mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._lock = threading.Lock()

    def _collection(self):
        col = getattr(self._local, "col", None)
        if col is None:
            client = chromadb.PersistentClient(path=self._path)
            col = client.get_or_create_collection(
                name=self.COLLECTION, metadata={"hnsw:space": "cosine"}
            )
            self._local.col = col
        return col

    @staticmethod
    def chunk_id(conversation_id: str, message_id: str, chunk_index: int) -> str:
        return f"conv:{conversation_id}:msg:{message_id}:chunk:{chunk_index}"

    def upsert_message_chunks(
        self,
        *,
        conversation_id: str,
        message_id: str,
        role: str,
        ts: str,
        conversation_title: str,
        chunks: list[MessageChunk],
        embeddings: list[list[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks/embeddings length mismatch")
        with self._lock:
            col = self._collection()
            existing = col.get(where={
                "$and": [
                    {"conversation_id": conversation_id},
                    {"message_id": message_id},
                ]
            })
            if existing and existing.get("ids"):
                col.delete(ids=existing["ids"])
            if not chunks:
                return
            ids, docs, metas = [], [], []
            for c, _emb in zip(chunks, embeddings):
                cid = self.chunk_id(conversation_id, message_id, c.index)
                ids.append(cid)
                docs.append(c.text)
                metas.append({
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "role": role,
                    "chunk_index": c.index,
                    "start_char": c.start_char,
                    "end_char": c.end_char,
                    "ts": ts,
                    "conversation_title": conversation_title or "",
                })
            col.add(ids=ids, documents=docs, embeddings=embeddings, metadatas=metas)

    def query(self, embedding: list[float], k: int = 5, *, conversation_id: str | None = None) -> list[ConversationVectorHit]:
        where = {"conversation_id": conversation_id} if conversation_id else None
        with self._lock:
            kwargs = {"query_embeddings": [embedding], "n_results": max(k, 1)}
            if where:
                kwargs["where"] = where
            res = self._collection().query(**kwargs)
        hits: list[ConversationVectorHit] = []
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        ids = (res.get("ids") or [[]])[0]
        for doc, meta, dist, cid in zip(docs, metas, dists, ids):
            if meta is None:
                continue
            hits.append(ConversationVectorHit(
                chunk_id=cid,
                conversation_id=meta["conversation_id"],
                message_id=meta["message_id"],
                role=meta.get("role") or "",
                start_char=int(meta["start_char"]),
                end_char=int(meta["end_char"]),
                text=doc or "",
                score=1.0 - float(dist),
            ))
        return hits[:k]

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock:
            col = self._collection()
            existing = col.get(where={"conversation_id": conversation_id})
            if existing and existing.get("ids"):
                col.delete(ids=existing["ids"])

    def count_for_message(self, conversation_id: str, message_id: str) -> int:
        with self._lock:
            existing = self._collection().get(where={
                "$and": [
                    {"conversation_id": conversation_id},
                    {"message_id": message_id},
                ]
            })
        return len(existing.get("ids") or [])
```

注意：Chroma metadata 值需为 str/int/float/bool；`chunk_index` 用 int。若 `get(where=...)` 在空 collection 报错，捕获后当空处理。

- [ ] **Step 4: 跑通测试并提交**

```bash
cd backend && python -m pytest tests/test_conversation_vector.py -q
git add backend/app/index/conversation_vector.py backend/tests/test_conversation_vector.py
git commit -m "feat: add ConversationVector upsert/query for message chunks"
```

---

## Task 2: RRF 纯函数

**Files:**
- Create: `backend/app/engine/rrf.py`
- Test: `backend/tests/test_rrf.py`

- [ ] **Step 1: 测试**

```python
# backend/tests/test_rrf.py
from app.engine.rrf import reciprocal_rank_fusion


def test_rrf_prefers_multi_lane_agreement():
    # item A rank1 in both lanes beats B rank1 in one lane only
    lanes = [
        ["A", "B", "C"],
        ["A", "C", "B"],
    ]
    fused = reciprocal_rank_fusion(lanes, k=60)
    assert fused[0][0] == "A"
    assert fused[0][1] > fused[1][1]


def test_rrf_stable_empty():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
```

- [ ] **Step 2: 实现**

```python
# backend/app/engine/rrf.py
from __future__ import annotations


def reciprocal_rank_fusion(
    ranked_id_lists: list[list[str]],
    *,
    k: int = 60,
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranked in ranked_id_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
```

- [ ] **Step 3: 提交**

```bash
git add backend/app/engine/rrf.py backend/tests/test_rrf.py
git commit -m "feat: add reciprocal rank fusion helper"
```

---

## Task 3: index_revision + enqueue index_vector

**Files:**
- Create: `backend/app/index/revision.py`（或放 conversations/config）
- Modify: `backend/app/engine/conversations.py`（`_enqueue_index_fts` → 同时入队 vector；delete 清 vector；暴露 bump/get revision）
- Modify: `backend/app/config.py`（可选 `rrf_k`、`lane_candidate_k`）
- Test: `backend/tests/test_index_revision.py`、扩展 `test_conversations.py` / `test_derivation_worker.py`

- [ ] **Step 1: revision 文件**

```python
# backend/app/index/revision.py
from __future__ import annotations
import threading
from pathlib import Path


class IndexRevision:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("0", encoding="utf-8")

    def get(self) -> int:
        with self._lock:
            return int(self.path.read_text(encoding="utf-8").strip() or "0")

    def bump(self) -> int:
        with self._lock:
            cur = int(self.path.read_text(encoding="utf-8").strip() or "0")
            cur += 1
            self.path.write_text(str(cur), encoding="utf-8")
            return cur
```

- [ ] **Step 2: conversations 入队**

把 `_enqueue_index_fts` 改为 `_enqueue_index_jobs`，同时插入 `index_fts` 与 `index_vector` 两行 outbox（同 message_id/turn_id）。

`delete()` 增加可选 `conversation_vector`，调用 `delete_conversation`；成功变更索引后 `index_revision.bump()`（也可由 worker 在 complete 时 bump——**冻结决策：worker 每次成功 upsert/delete 后 bump**，避免 begin_turn 未索引就变 revision）。

- [ ] **Step 3: 测试**

```python
def test_begin_turn_enqueues_fts_and_vector(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    store.begin_turn(cid, "hi", "cli-1", observation_allowed=False)
    rows = store.conn.execute(
        "SELECT kind FROM derivation_outbox WHERE status='pending' ORDER BY kind"
    ).fetchall()
    kinds = [r[0] for r in rows]
    assert kinds == ["index_fts", "index_vector"]
```

- [ ] **Step 4: 提交**

```bash
git commit -m "feat: enqueue index_vector outbox and track index_revision"
```

---

## Task 4: DerivationWorker 处理 index_vector

**Files:**
- Modify: `backend/app/engine/derivation_worker.py`
- Modify: `backend/app/deps.py`、`backend/app/main.py`
- Test: `backend/tests/test_derivation_worker.py`

- [ ] **Step 1: Worker 扩展**

```python
class DerivationWorker:
    def __init__(self, conversations, conversation_fts, *, conversation_vector=None, llm=None, index_revision=None, chunk_chars=1000, overlap=150):
        ...
        self.vector = conversation_vector
        self.llm = llm
        self.revision = index_revision

    def drain(self, max_jobs: int = 50) -> int:
        done = 0
        for kind in ("index_fts", "index_vector"):
            while done < max_jobs:
                jobs = self.conversations.claim_outbox(kind=kind, limit=min(10, max_jobs - done), lease_seconds=60)
                if not jobs:
                    break
                for job in jobs:
                    if kind == "index_fts":
                        self.process_fts_job(job)
                    else:
                        self.process_vector_job(job)
                    done += 1
        return done

    def process_vector_job(self, job: dict) -> None:
        if self.vector is None or self.llm is None:
            self.conversations.fail_outbox(job["id"], "vector not configured", backoff=1.0)
            return
        message = self.conversations.get_message(job["source_message_id"])
        if message is None:
            self.conversations.complete_outbox(job["id"])
            return
        masked, _ = mask_secrets(message.get("text") or "")
        chunks = chunk_message(masked, size=self.chunk_chars, overlap=self.overlap)
        if chunks:
            embs = self.llm.embed([c.text for c in chunks])
            self.vector.upsert_message_chunks(
                conversation_id=message["conversation_id"],
                message_id=message["id"],
                role=message.get("role", ""),
                ts=message.get("ts", ""),
                conversation_title=message.get("conversation_title", ""),
                chunks=chunks,
                embeddings=embs,
            )
            if self.revision:
                self.revision.bump()
        self.conversations.complete_outbox(job["id"])
```

FTS 成功路径同样 bump revision（或仅 vector bump——**冻结：两路成功都 bump**，保证 cursor 在任一索引变化时失效）。

- [ ] **Step 2: FakeLLM.embed** 确保返回与输入等长向量（已有则复用）。

- [ ] **Step 3: 测试**

```python
def test_worker_indexes_vector(tmp_path):
    # begin_turn + finalize → drain → ConversationVector.query 能命中
    ...
```

- [ ] **Step 4: 提交**

```bash
git commit -m "feat: derivation worker indexes conversation vectors"
```

---

## Task 5: Retriever 四路 RRF + SearchPage cursor

**Files:**
- Modify: `backend/app/engine/retriever.py`
- Modify: `backend/app/index/types.py`（可选 `lane` 字段）
- Test: `backend/tests/test_retriever_rrf.py`

- [ ] **Step 1: API**

```python
@dataclass
class SearchPage:
    hits: list[Hit]
    has_more: bool
    next_cursor: str | None
    index_revision: int
    cursor_expired: bool = False


class Retriever:
    def __init__(..., conversation_vector=None, index_revision=None, rrf_k=60, lane_candidate_k=20):
        ...

    def search(
        self,
        query: str,
        k: int = 5,
        *,
        scope: str = "all",  # all|knowledge|conversations
        conversation_id: str | None = None,
        cursor: str | None = None,
    ) -> SearchPage:
        ...
```

兼容：保留旧调用 `search(q, k)` 返回 `list[Hit]` **或** 全面改成 SearchPage 并更新所有调用方（**冻结：改成 SearchPage，更新调用方**）。

Cursor 编解码：

```python
import base64, json, hashlib

def _make_cursor(query, filters, rev, offset) -> str:
    payload = {"q": query, "f": filters, "rev": rev, "off": offset}
    return base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode()

def _parse_cursor(cursor: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()))
```

流程：
1. 解析 cursor；若 `rev != index_revision.get()` → 返回空 hits + `cursor_expired=True`
2. 按 scope 决定启用哪些 lane
3. 每路取 `lane_candidate_k` 候选，生成 ranked id 列表（用 `Hit.doc_id`）
4. RRF 融合 → 按 offset 切片 `k` 条 → 组装 SearchPage
5. 向量 lane 失败：记 warning，该路空列表，其余继续

`conversation_id` 过滤：会话 FTS/Vector query 传过滤；知识 lane 在 scope=conversations 时跳过。

- [ ] **Step 2: 测试**

```python
def test_rrf_merges_four_lanes(tmp_path, ...):
    # 植入 KB + conv FTS + conv vector；search scope=all 返回 SearchPage
    page = retriever.search("漫剧工具", k=5)
    assert isinstance(page.hits, list)
    assert page.index_revision >= 0

def test_cursor_expires_on_revision_bump(...):
    page1 = retriever.search("q", k=1)
    rev.bump()
    page2 = retriever.search("q", k=1, cursor=page1.next_cursor)
    assert page2.cursor_expired
```

- [ ] **Step 3: 更新 `answer()`、tools、tests 中所有 `retriever.search` 用法。**

- [ ] **Step 4: 提交**

```bash
git commit -m "feat: four-lane RRF search with revision-bound cursor"
```

---

## Task 6: search_kb 工具参数扩展

**Files:**
- Modify: `backend/app/engine/agent/tools.py`、`prompts` 若有 schema
- Test: `backend/tests/test_agent_tools.py`

- [ ] **Step 1: TOOL_DEFINITIONS 为 search_kb 增加**

```json
"scope": {"type": "string", "enum": ["all", "knowledge", "conversations"]},
"conversation_id": {"type": "string"},
"cursor": {"type": "string"}
```

- [ ] **Step 2: `_search_kb` 调用 `retriever.search(..., scope=..., conversation_id=..., cursor=...)`**

返回 summary 中若 `cursor_expired` 明确告知；sources 仍用 `_hit_source`。`content` 可附加 `next_cursor`/`has_more` 供模型续取（写入 tool_result extra 字段）。

- [ ] **Step 3: 提交**

```bash
git commit -m "feat: extend search_kb with scope conversation_id and cursor"
```

---

## Task 7: 向量回填 + checkpoint

**Files:**
- Modify: `backend/app/engine/conversation_backfill.py`
- Test: `backend/tests/test_conversation_backfill.py`

- [ ] **Step 1: API**

```python
def backfill_conversation_vectors(
    store,
    vector: ConversationVector,
    llm: LLMClient,
    deletion_ledger_path=None,
    *,
    checkpoint_path: Path | None = None,
    chunk_chars=1000,
    overlap=150,
    batch_size=20,
) -> dict:
    """跳过 ledger 已删 cid；按 message id 序处理；checkpoint 记录 last_message_id。"""
```

Checkpoint JSON：`{"last_message_id": "...", "indexed": N}`。第二次运行从 checkpoint 续跑；已覆盖消息（`count_for_message>0` 且与 chunk 数一致）跳过。

CLI：`python -m app.engine.conversation_backfill --vectors`（或子命令）；默认仍可只跑 FTS。

- [ ] **Step 2: 测试幂等与续跑**

- [ ] **Step 3: 删除会话路径清理 ConversationVector（若 Task 3 未完成）**

- [ ] **Step 4: 全量回归**

```bash
cd backend && python -m pytest -q
git commit -m "feat: backfill conversation vectors with checkpoint"
```

---

## 1B 验收清单

| 验收项 | Task |
|--------|------|
| ConversationVector upsert/query/delete | 1 |
| index_vector outbox 独立入队/完成/失败 | 3–4 |
| Vector 故障时 FTS 仍可搜 | 5 |
| 四路 RRF | 2, 5 |
| index_revision + cursor_expired | 3, 5 |
| search_kb scope/cursor | 6 |
| 向量回填幂等 + checkpoint | 7 |
| 不做前端跳转 / 记忆.md / observe_memory | 范围外 |

---

## Plan Self-Review

1. **Spec coverage (1B):** Vector v2 → T1；RRF+revision → T2/T3/T5；FTS 降级 → T5；向量回填 checkpoint → T7；outbox index_vector → T3/T4。同源分组与 `read_conversation_context` 明确留给 1C。
2. **Placeholders:** 无 TBD。
3. **Type consistency:** chunk_id 与 FTS 相同；Hit 继续用 message_id/start_char/end_char；SearchPage 为新返回类型。

---

## 执行方式

在 `master` 上按 Task 1→7 顺序 TDD 实施；每 Task 提交一次。用户目标要求连续完成全部后续阶段，1B 验收通过后立即撰写并执行 1C 计划。
