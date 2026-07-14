# 第二大脑 · 阶段 1A 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把会话从 JSON 分片升级为 SQLite 消息级持久化，并为每条消息建立完整、可脱敏的 FTS v2 索引，使归档后原文仍可检索、长会话不再因截断丢失。

**Architecture:** `ConversationStore` 迁到 `conversations.db`（WAL + 事务）；`/api/chat` 改为「先读旧历史 → 同事务落用户消息与 index_fts outbox → 流式回答 → 拦截 done 后落助手消息 → 再发 done」；后台 worker 消费 `index_fts` outbox，写入 `conversation_chunks_v2`。本阶段不引入 Vector、记忆画像或自动学习。

**Tech Stack:** Python 3.12 / FastAPI / SQLite / pytest；React + TypeScript（仅透传 `client_message_id`）。

**Spec:** [2026-07-13-memory-layer-design.md](../specs/2026-07-13-memory-layer-design.md) §6.1–6.2、§12、§14、§16 阶段 1A。

**后续计划（本文件不实现）：** 1B Vector+RRF；1C 来源跳转与总结关系完善；2 `记忆.md`；3 自动学习；4 衰减。

---

## 文件结构（1A）

| 文件 | 职责 |
|------|------|
| `backend/app/engine/workspace.py` | 创建/读取稳定 `workspace_id` |
| `backend/app/engine/secrets.py` | 确定性 secret scanner + 等长掩码 |
| `backend/app/index/message_chunk.py` | Unicode code point 分块与覆盖校验 |
| `backend/app/index/conversation_fts.py` | `conversation_chunks_v2` FTS upsert/query/delete |
| `backend/app/engine/conversations.py` | 重写为 SQLite ConversationStore |
| `backend/app/engine/conversation_migrate.py` | JSON → SQLite 幂等迁移 |
| `backend/app/engine/derivation_worker.py` | 消费 `index_fts` outbox |
| `backend/app/api/routes.py` | 聊天持久化顺序、done 拦截、finally interrupted |
| `backend/app/index/indexer.py` | 去掉归档后 `remove_conversation`；委托消息级 FTS |
| `backend/app/config.py` / `deps.py` | chunk 参数、装配 worker |
| `frontend/src/api.ts` / `useAgentStream.ts` | 生成并透传 `client_message_id` |
| `backend/tests/test_*.py` | 对应单元/集成测试 |

---

## 决策记录（1A 冻结）

| 项 | 决策 |
|----|------|
| 会话规范存储 | 仅 SQLite；JSON 只读迁移源，验证后保留 7 天再删 |
| 本阶段 outbox kind | 只实现 `index_fts`；schema 预留 `index_vector`/`observe_memory` 但不入队 |
| 归档后检索 | **不再** `remove_conversation`；原文消息索引永久保留 |
| 同步索引 vs worker | 默认走 outbox + worker；测试可用同步 drain helper |
| `append_exchange` | 保留为测试兼容薄封装，内部改调 `begin_turn` + `finalize_turn` |
| 前端改动 | 仅 `client_message_id`；消息跳转留给 1C |

---

## Task 1: Workspace ID

**Files:**
- Create: `backend/app/engine/workspace.py`
- Modify: `backend/app/deps.py`
- Test: `backend/tests/test_workspace.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_workspace.py
from app.engine.workspace import ensure_workspace_id


def test_ensure_workspace_id_stable(tmp_path):
    a = ensure_workspace_id(tmp_path)
    b = ensure_workspace_id(tmp_path)
    assert a == b
    assert len(a) >= 8
    data = (tmp_path / ".kb" / "workspace.json").read_text(encoding="utf-8")
    assert a in data
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_workspace.py -q
```

Expected: `ImportError` 或 `ModuleNotFoundError`

- [ ] **Step 3: 实现**

```python
# backend/app/engine/workspace.py
from __future__ import annotations

import json
import uuid
from pathlib import Path


def ensure_workspace_id(kb_path: Path) -> str:
    kb = Path(kb_path)
    path = kb / ".kb" / "workspace.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        wid = data.get("workspace_id")
        if isinstance(wid, str) and wid.strip():
            return wid.strip()
    wid = uuid.uuid4().hex
    path.write_text(
        json.dumps({"workspace_id": wid}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return wid
```

在 `build_container` 开头调用 `ensure_workspace_id(settings.kb_path)`（返回值暂存 Container 可选字段 `workspace_id`，1A 可不暴露给业务）。

- [ ] **Step 4: 跑通过**

```bash
cd backend && python -m pytest tests/test_workspace.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/workspace.py backend/app/deps.py backend/tests/test_workspace.py
git commit -m "feat: persist stable workspace_id under .kb/workspace.json"
```

---

## Task 2: Secret scanner（等长掩码）

**Files:**
- Create: `backend/app/engine/secrets.py`
- Test: `backend/tests/test_secrets.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_secrets.py
from app.engine.secrets import mask_secrets, scan_secrets


def test_mask_openai_key_preserves_codepoint_length():
    text = "key=sk-abcdefghijklmnopqrstuvwxyz012345"
    masked, spans = mask_secrets(text)
    assert len(list(masked)) == len(list(text))
    assert spans
    assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in masked
    assert "•" in masked


def test_scan_finds_github_pat():
    text = "token ghp_abcdefghijklmnopqrstuvwx1234567890ABCD"
    spans = scan_secrets(text)
    assert spans
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_secrets.py -q
```

Expected: FAIL ImportError

- [ ] **Step 3: 实现最小规则集**

```python
# backend/app/engine/secrets.py
from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*\S{8,}"),
]


@dataclass(frozen=True)
class SecretSpan:
    start: int  # unicode code point index
    end: int    # exclusive


def _codepoints(text: str) -> list[str]:
    return list(text)


def scan_secrets(text: str) -> list[SecretSpan]:
    cps = _codepoints(text)
    joined = "".join(cps)
    spans: list[SecretSpan] = []
    for pat in _PATTERNS:
        for m in pat.finditer(joined):
            spans.append(SecretSpan(m.start(), m.end()))
    # merge overlaps
    if not spans:
        return []
    spans.sort(key=lambda s: (s.start, s.end))
    merged = [spans[0]]
    for s in spans[1:]:
        last = merged[-1]
        if s.start <= last.end:
            merged[-1] = SecretSpan(last.start, max(last.end, s.end))
        else:
            merged.append(s)
    return merged


def mask_secrets(text: str, mask_char: str = "•") -> tuple[str, list[SecretSpan]]:
    cps = _codepoints(text)
    spans = scan_secrets(text)
    for s in spans:
        for i in range(s.start, min(s.end, len(cps))):
            cps[i] = mask_char
    return "".join(cps), spans
```

说明：规则是启发式，验收只覆盖「scanner 检出的」值；未知格式不承诺。

- [ ] **Step 4: 跑通过并提交**

```bash
cd backend && python -m pytest tests/test_secrets.py -q
git add backend/app/engine/secrets.py backend/tests/test_secrets.py
git commit -m "feat: add equal-length secret masking for conversation indexing"
```

---

## Task 3: 消息分块（unicode-codepoint-v1）

**Files:**
- Create: `backend/app/index/message_chunk.py`
- Modify: `backend/app/config.py`（增加 chunk 配置）
- Test: `backend/tests/test_message_chunk.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_message_chunk.py
from app.index.message_chunk import chunk_message, coverage_ok


def test_chunk_covers_all_codepoints():
    text = "甲" * 50 + "\n\n" + "乙" * 50
    chunks = chunk_message(text, size=40, overlap=10)
    assert chunks
    assert coverage_ok(text, chunks)


def test_chunk_preserves_offsets_after_masking():
    from app.engine.secrets import mask_secrets

    raw = "before sk-abcdefghijklmnopqrstuvwxyz012345 after"
    masked, _ = mask_secrets(raw)
    chunks = chunk_message(masked, size=20, overlap=5)
    assert coverage_ok(masked, chunks)
    # offsets refer to same codepoint length as raw
    assert len(list(raw)) == len(list(masked))
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_message_chunk.py -q
```

Expected: FAIL ImportError

- [ ] **Step 3: 实现**

```python
# backend/app/index/message_chunk.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MessageChunk:
    index: int
    start_char: int  # unicode code point, half-open
    end_char: int
    text: str
    offset_version: str = "unicode-codepoint-v1"


def chunk_message(text: str, *, size: int = 1000, overlap: int = 150) -> list[MessageChunk]:
    cps = list(text)
    n = len(cps)
    if n == 0:
        return []
    if n <= size:
        return [MessageChunk(0, 0, n, text)]
    step = max(1, size - overlap)
    out: list[MessageChunk] = []
    i = 0
    idx = 0
    while i < n:
        j = min(n, i + size)
        # prefer paragraph / sentence breaks near end
        window = "".join(cps[i:j])
        cut = j
        if j < n:
            for sep in ("\n\n", "\n", "。", "！", "？", ". ", "! ", "? "):
                pos = window.rfind(sep)
                if pos >= size // 3:
                    cut = i + pos + len(list(sep))
                    break
        piece = "".join(cps[i:cut])
        out.append(MessageChunk(idx, i, cut, piece))
        idx += 1
        if cut >= n:
            break
        i = max(cut - overlap, i + 1)
    return out


def coverage_ok(text: str, chunks: list[MessageChunk]) -> bool:
    n = len(list(text))
    if n == 0:
        return chunks == []
    covered = [False] * n
    for c in chunks:
        for i in range(c.start_char, c.end_char):
            if 0 <= i < n:
                covered[i] = True
    return all(covered)
```

`config.py` 增加：

```python
conversation_chunk_chars: int = 1000
conversation_chunk_overlap_chars: int = 150
```

- [ ] **Step 4: 跑通过并提交**

```bash
cd backend && python -m pytest tests/test_message_chunk.py -q
git add backend/app/index/message_chunk.py backend/app/config.py backend/tests/test_message_chunk.py
git commit -m "feat: add unicode-codepoint message chunker with full coverage"
```

---

## Task 4: `conversation_chunks_v2` FTS

**Files:**
- Create: `backend/app/index/conversation_fts.py`
- Test: `backend/tests/test_conversation_fts.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_conversation_fts.py
from app.index.conversation_fts import ConversationFTS
from app.index.message_chunk import MessageChunk


def test_upsert_and_query_by_message(tmp_path):
    fts = ConversationFTS(tmp_path / "fts.db")
    chunks = [
        MessageChunk(0, 0, 5, "你好世界"),
        MessageChunk(1, 5, 10, "漫剧工具"),
    ]
    fts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-07-14T10:00:00",
        conversation_title="测试",
        chunks=chunks,
    )
    hits = fts.query("漫剧", k=5)
    assert hits
    assert hits[0].message_id == "m1"
    assert hits[0].conversation_id == "c1"


def test_delete_conversation_removes_all_chunks(tmp_path):
    fts = ConversationFTS(tmp_path / "fts.db")
    fts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="t",
        chunks=[MessageChunk(0, 0, 2, "ab")],
    )
    fts.delete_conversation("c1")
    assert fts.query("ab", k=5) == []
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_conversation_fts.py -q
```

Expected: FAIL ImportError

- [ ] **Step 3: 实现**

```python
# backend/app/index/conversation_fts.py
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from app.index.fulltext import prepare_fts_query
from app.index.message_chunk import MessageChunk


@dataclass
class ConversationHit:
    chunk_id: str
    conversation_id: str
    message_id: str
    role: str
    start_char: int
    end_char: int
    text: str
    score: float
    offset_version: str = "unicode-codepoint-v1"


class ConversationFTS:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS conversation_chunks_v2
                USING fts5(
                    chunk_id UNINDEXED,
                    conversation_id UNINDEXED,
                    message_id UNINDEXED,
                    role UNINDEXED,
                    start_char UNINDEXED,
                    end_char UNINDEXED,
                    ts UNINDEXED,
                    conversation_title UNINDEXED,
                    body,
                    tokenize='trigram'
                )
                """
            )
            self.conn.commit()

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
    ) -> None:
        with self._lock:
            self.conn.execute(
                "DELETE FROM conversation_chunks_v2 WHERE conversation_id = ? AND message_id = ?",
                (conversation_id, message_id),
            )
            for c in chunks:
                cid = self.chunk_id(conversation_id, message_id, c.index)
                self.conn.execute(
                    """
                    INSERT INTO conversation_chunks_v2(
                        chunk_id, conversation_id, message_id, role,
                        start_char, end_char, ts, conversation_title, body
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cid,
                        conversation_id,
                        message_id,
                        role,
                        c.start_char,
                        c.end_char,
                        ts,
                        conversation_title,
                        c.text,
                    ),
                )
            self.conn.commit()

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock:
            self.conn.execute(
                "DELETE FROM conversation_chunks_v2 WHERE conversation_id = ?",
                (conversation_id,),
            )
            self.conn.commit()

    def delete_message(self, conversation_id: str, message_id: str) -> None:
        with self._lock:
            self.conn.execute(
                "DELETE FROM conversation_chunks_v2 WHERE conversation_id = ? AND message_id = ?",
                (conversation_id, message_id),
            )
            self.conn.commit()

    def query(self, text: str, k: int = 5) -> list[ConversationHit]:
        text = text.strip()
        if not text:
            return []
        match = prepare_fts_query(text)
        with self._lock:
            try:
                rows = self.conn.execute(
                    """
                    SELECT chunk_id, conversation_id, message_id, role,
                           start_char, end_char, body, bm25(conversation_chunks_v2) AS rank
                    FROM conversation_chunks_v2
                    WHERE conversation_chunks_v2 MATCH ?
                    ORDER BY rank LIMIT ?
                    """,
                    (match, k),
                ).fetchall()
            except sqlite3.OperationalError:
                return []
        return [
            ConversationHit(
                chunk_id=r[0],
                conversation_id=r[1],
                message_id=r[2],
                role=r[3],
                start_char=int(r[4]),
                end_char=int(r[5]),
                text=r[6],
                score=-float(r[7]),
            )
            for r in rows
        ]
```

注意：1A 的 `search_kb` 仍走旧 `Retriever`；本 Task 只建立消息级 FTS 能力与写入路径。把会话命中并入 `search_kb` 可在本阶段末做一个最小桥接（Task 10），否则留到 1B。**本计划在 Task 10 做最小桥接**：`Retriever.search` 合并 `ConversationFTS.query` 结果。

- [ ] **Step 4: 跑通过并提交**

```bash
cd backend && python -m pytest tests/test_conversation_fts.py -q
git add backend/app/index/conversation_fts.py backend/tests/test_conversation_fts.py
git commit -m "feat: add conversation_chunks_v2 FTS with message-level upsert"
```

---

## Task 5: SQLite ConversationStore 核心 schema + CRUD

**Files:**
- Rewrite: `backend/app/engine/conversations.py`
- Test: `backend/tests/test_conversations.py`（更新现有测试 + 新测试）

- [ ] **Step 1: 写/改失败测试（幂等与消息 ID）**

在 `test_conversations.py` 追加：

```python
def test_begin_and_finalize_turn_assigns_message_ids(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(
        cid,
        user_text="你好",
        client_message_id="cli-1",
        observation_allowed=False,
    )
    assert turn["user_message"]["id"]
    assert turn["user_message"]["role"] == "user"
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "你好呀",
            "timeline": [{"type": "text", "content": "你好呀", "ts": "t"}],
            "sources": [],
            "status": "complete",
        },
    )
    conv = store.get(cid)
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["id"]
    assert conv["messages"][1]["in_reply_to_message_id"] == conv["messages"][0]["id"]


def test_duplicate_client_message_id_while_running_raises(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    store.begin_turn(cid, user_text="a", client_message_id="cli-1", observation_allowed=False)
    try:
        store.begin_turn(cid, user_text="a", client_message_id="cli-1", observation_allowed=False)
        assert False, "expected TurnInProgress"
    except Exception as e:
        assert e.__class__.__name__ == "TurnInProgress"
```

保留并适配现有 `append_exchange` 测试：`append_exchange` 应仍可用。

- [ ] **Step 2: 跑失败确认新 API 不存在**

```bash
cd backend && python -m pytest tests/test_conversations.py -k "begin_and_finalize or duplicate_client" -q
```

Expected: FAIL AttributeError

- [ ] **Step 3: 实现 SQLite ConversationStore（关键骨架）**

实现要点（完整代码写入 `conversations.py`）：

1. DB 路径：`{conversations_dir}/conversations.db`
2. `CREATE TABLE`：`conversations / messages / turns / derivation_outbox / conversation_summaries / conversation_deletion_ledger`（按 spec §6.1）
3. `create/get/list_all/delete` 读写 SQLite，`get` 返回兼容 dict：`messages` 列表字段仍叫 `text`/`ts`，并含 `id`
4. `begin_turn(...)`：
   - 事务内插入 user message + turn(status=running) + `index_fts` outbox(pending)
   - **1A 不入队** `observe_memory`
   - 唯一约束 `(conversation_id, client_message_id)`；冲突且 turn running → `TurnInProgress`
5. `finalize_turn(...)`：
   - 写 assistant message（含 `in_reply_to_message_id`）
   - 再入队 assistant 的 `index_fts`
   - turn → complete/interrupted
6. `append_exchange`：生成临时 `client_message_id`，调用 begin+finalize，保持旧测试绿
7. `llm_history`：只取 user/assistant 的 `text`，排除本轮未 finalize 的 running turn 之外的行为与现有一致（最近 20 轮 / 32k）
8. `mark_summarized`：写入 `conversation_summaries`，**不再**依赖会触发删索引的逻辑

异常类：

```python
class TurnInProgress(Exception):
    def __init__(self, turn_id: str, retry_after_ms: int = 1000):
        self.turn_id = turn_id
        self.retry_after_ms = retry_after_ms
```

`_store` fixture 不变：`ConversationStore(tmp_path / "conversations")`。

- [ ] **Step 4: 跑全部 conversations 测试**

```bash
cd backend && python -m pytest tests/test_conversations.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/conversations.py backend/tests/test_conversations.py
git commit -m "feat: migrate ConversationStore to SQLite with turn-based persistence"
```

---

## Task 6: JSON → SQLite 幂等迁移

**Files:**
- Create: `backend/app/engine/conversation_migrate.py`
- Modify: `backend/app/engine/conversations.py`（构造时触发）
- Test: `backend/tests/test_conversation_migrate.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_conversation_migrate.py
import json
from pathlib import Path

from app.engine.conversation_migrate import migrate_json_shards
from app.engine.conversations import ConversationStore


def _write_shard(dir: Path, date: str, convs: dict):
    dir.mkdir(parents=True, exist_ok=True)
    (dir / "index.json").write_text(
        json.dumps({cid: date for cid in convs}, ensure_ascii=False),
        encoding="utf-8",
    )
    (dir / f"{date}.json").write_text(
        json.dumps(convs, ensure_ascii=False), encoding="utf-8"
    )


def test_migrate_is_idempotent_and_rebuilds_assistant_text(tmp_path):
    root = tmp_path / "conversations"
    cid = "abc123"
    _write_shard(
        root,
        "2026-07-12",
        {
            cid: {
                "id": cid,
                "title": "旧会话",
                "created_at": "2026-07-12T10:00:00",
                "updated_at": "2026-07-12T10:01:00",
                "messages": [
                    {"role": "user", "text": "你好", "ts": "2026-07-12T10:00:00"},
                    {
                        "role": "assistant",
                        "ts": "2026-07-12T10:00:30",
                        "timeline": [
                            {"type": "text", "content": "你好呀", "ts": "t"}
                        ],
                        "sources": [],
                    },
                ],
                "summarized": True,
                "summary_path": "主题/旧.md",
            }
        },
    )
    r1 = migrate_json_shards(root)
    r2 = migrate_json_shards(root)
    assert r1["conversations"] == 1
    assert r2["conversations"] == 1
    store = ConversationStore(root)
    conv = store.get(cid)
    assert conv["messages"][0]["id"] == store.get(cid)["messages"][0]["id"]
    assert conv["messages"][1]["text"] == "你好呀"
    assert any(s.get("doc_path") == "主题/旧.md" for s in store.list_summaries(cid))
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_conversation_migrate.py -q
```

Expected: FAIL ImportError

- [ ] **Step 3: 实现迁移**

关键规则（写入 `conversation_migrate.py`）：

1. 若 `conversations.db` 已有行且 `migration_meta.completed=1`，直接返回统计
2. 扫描 `index.json` + `*.json` shards（跳过 `conversations.db`）
3. 用户消息：`text` 原样；助手：拼接 timeline `type==text` 的 content
4. 消息 ID：`uuid.uuid5(NAMESPACE, f"{cid}|{seq}|{role}|{ts}|{text_hash}|{timeline_hash}")`
5. 建立 `conversation_summaries`：旧 `summarized/summary_path` → relation；无法证明覆盖末条时 `status=stale`
6. **不**自动创建历史 `observe_memory`；可为每条消息创建 `index_fts` outbox（pending）供 worker 回填
7. 迁移成功写 `migration_meta`；原 JSON 保留为只读（不改名也可，但不得再作为写路径）

`ConversationStore.__init__`：若存在 `index.json` 且 db 未完成迁移，调用 `migrate_json_shards`。

- [ ] **Step 4: 跑通过并提交**

```bash
cd backend && python -m pytest tests/test_conversation_migrate.py tests/test_conversations.py -q
git add backend/app/engine/conversation_migrate.py backend/app/engine/conversations.py backend/tests/test_conversation_migrate.py
git commit -m "feat: idempotent JSON conversation shard migration into SQLite"
```

---

## Task 7: index_fts worker

**Files:**
- Create: `backend/app/engine/derivation_worker.py`
- Modify: `backend/app/deps.py`、`backend/app/main.py`（或现有 lifespan 入口）
- Modify: `backend/app/index/indexer.py`（委托消息级索引）
- Test: `backend/tests/test_derivation_worker.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_derivation_worker.py
from app.engine.conversations import ConversationStore
from app.engine.derivation_worker import DerivationWorker
from app.index.conversation_fts import ConversationFTS


def test_worker_indexes_user_and_assistant_messages(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    fts = ConversationFTS(tmp_path / "conv_fts.db")
    cid = store.create()
    turn = store.begin_turn(cid, user_text="漫剧剪辑工具有哪些", client_message_id="c1", observation_allowed=False)
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "剪映和小云雀", "timeline": [{"type": "text", "content": "剪映和小云雀"}], "sources": [], "status": "complete"},
    )
    worker = DerivationWorker(store, fts, chunk_chars=1000, overlap=150)
    n = worker.drain(max_jobs=10)
    assert n >= 2
    hits = fts.query("剪映", k=5)
    assert hits
    assert hits[0].conversation_id == cid
```

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_derivation_worker.py -q
```

Expected: FAIL ImportError

- [ ] **Step 3: 实现 worker**

```python
# backend/app/engine/derivation_worker.py （核心逻辑）
class DerivationWorker:
    def __init__(self, conversations, conversation_fts, *, chunk_chars, overlap):
        self.conversations = conversations
        self.fts = conversation_fts
        self.chunk_chars = chunk_chars
        self.overlap = overlap

    def claim_jobs(self, *, kind: str = "index_fts", limit: int = 10) -> list[dict]:
        return self.conversations.claim_outbox(kind=kind, limit=limit, lease_seconds=60)

    def process_job(self, job: dict) -> None:
        # 1) load message by source_message_id
        # 2) mask_secrets(message["text"])
        # 3) chunk_message(masked)
        # 4) fts.upsert_message_chunks(...)
        # 5) conversations.complete_outbox(job_id)
        # on error: conversations.fail_outbox(job_id, error, backoff)

    def drain(self, max_jobs: int = 50) -> int:
        done = 0
        while done < max_jobs:
            jobs = self.claim_jobs(limit=min(10, max_jobs - done))
            if not jobs:
                break
            for job in jobs:
                self.process_job(job)
                done += 1
        return done
```

在 FastAPI lifespan（查找 `backend/app/main.py` 或现有启动点）启动后台线程/asyncio task：每 0.5s `drain(20)`。测试不依赖 lifespan，直接 `drain`。

`Indexer`：保留旧 `index_conversation` 供过渡，但 chat 路径不再调用它；新增 `index_message(...)` 供 worker 或同步路径使用亦可放在 worker 内。

- [ ] **Step 4: 跑通过并提交**

```bash
cd backend && python -m pytest tests/test_derivation_worker.py -q
git add backend/app/engine/derivation_worker.py backend/app/deps.py backend/app/index/indexer.py backend/tests/test_derivation_worker.py
git commit -m "feat: add derivation worker for conversation FTS outbox jobs"
```

---

## Task 8: 重写 `/api/chat` 持久化顺序

**Files:**
- Modify: `backend/app/api/routes.py`
- Modify: `frontend/src/api.ts`、`frontend/src/hooks/chat/useAgentStream.ts`
- Test: `backend/tests/test_chat_persistence.py`（新建）

- [ ] **Step 1: 写失败集成测试**

复用 `tests/conftest.py` 的 `client` fixture（`create_app` + `Settings(kb_path=tmp_path/knowledge)` + `AgentFakeLLM`）。在 `test_chat_persistence.py` 写入：

```python
# backend/tests/test_chat_persistence.py
import json

from app.engine.agent.events import done, text_delta


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_type = data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_type and data is not None:
            events.append((event_type, data))
    return events


def test_chat_persists_message_ids(client):
    cid = client.post("/api/conversations", json={"title": "t"}).json()["id"]
    r = client.post(
        "/api/chat",
        json={"text": "你好", "conversation_id": cid, "client_message_id": "cli-1"},
    )
    assert r.status_code == 200
    assert "done" in [t for t, _ in _parse_sse(r.text)]
    conv = client.get(f"/api/conversations/{cid}").json()
    msgs = conv["messages"]
    assert len(msgs) >= 2
    assert msgs[0]["role"] == "user" and msgs[0]["id"]
    assert msgs[1]["role"] == "assistant" and msgs[1]["id"]
    assert msgs[1].get("in_reply_to_message_id") == msgs[0]["id"]


def test_chat_duplicate_client_message_id_returns_409(client, monkeypatch):
    cid = client.post("/api/conversations", json={"title": "t"}).json()["id"]

    async def slow_run(self, user_text, **kwargs):
        yield text_delta("…")
        # 不立刻 done，让第二次请求撞上 running turn
        import asyncio
        await asyncio.sleep(60)
        yield done([], 1)

    # 将 container.agent.run 替换为 slow_run 的方式：
    # monkeypatch.setattr(client.app.state.container.agent, "run", slow_run.__get__(..., type(...)))
    # 若项目 FakeLLM 难模拟长阻塞，可改为直接调 ConversationStore.begin_turn 两次断言 TurnInProgress，
    # 本用例至少覆盖 HTTP 层对 TurnInProgress → 409 的翻译（可用 monkeypatch begin_turn raise）。
    from app.engine.conversations import TurnInProgress

    def boom(*a, **k):
        raise TurnInProgress("turn-x", retry_after_ms=500)

    monkeypatch.setattr(
        client.app.state.container.conversations, "begin_turn", boom
    )
    r = client.post(
        "/api/chat",
        json={"text": "你好", "conversation_id": cid, "client_message_id": "cli-x"},
    )
    assert r.status_code == 409
```

另增单元级（不经 HTTP）测试 `test_history_excludes_current_user_message`：手动 `begin_turn` 后调用 `llm_history`，断言返回列表不含刚写入的用户句；Agent 入参仍由 routes 传入「begin_turn 前快照」。

`CancelledError` / interrupted：在 `tests/test_chat_persistence.py` 用直接调用 store 的 finalize 路径单测覆盖；HTTP 断流可用 `monkeypatch` 让 `agent.run` 在首个 delta 后 `raise asyncio.CancelledError`，再断言 DB 中 assistant `status=="interrupted"`。

`ChatBody` 增加：

```python
client_message_id: str | None = None
```

前端 `chatStream` body 增加：

```typescript
client_message_id: crypto.randomUUID(),
```

在 `useAgentStream` 每次发送时生成一次并随请求发送。

- [ ] **Step 2: 跑失败**

```bash
cd backend && python -m pytest tests/test_chat_persistence.py -q
```

Expected: FAIL（缺字段或旧 append_exchange 行为）

- [ ] **Step 3: 改 routes 事件循环**

伪代码（落到真实代码）：

```python
async def event_generator():
    acc = _TimelineAccumulator()
    history = c.conversations.llm_history(c.conversations.get(cid))  # 旧历史
    client_message_id = body.client_message_id or uuid.uuid4().hex
    try:
        turn = c.conversations.begin_turn(
            cid,
            user_text=body.text,
            client_message_id=client_message_id,
            observation_allowed=False,  # 1A
            doc_context=paths or None,
            primary_doc=primary,
            attachments=body.attachments or None,
        )
    except TurnInProgress as e:
        raise HTTPException(409, detail={"code": "turn_in_progress", "retry_after_ms": e.retry_after_ms})

    assistant_saved = False
    try:
        async for ev in c.agent.run(..., history=history, ...):
            parsed = _parse_sse(ev)
            if parsed and parsed[0] == "done":
                acc.accumulate(*parsed)
                c.conversations.finalize_turn(
                    cid,
                    turn_id=turn["turn_id"],
                    assistant={
                        "text": acc.assistant_text,  # 新增：拼接 text_delta
                        "timeline": acc.timeline,
                        "sources": acc.all_sources,
                        "total_duration_ms": acc.total_duration_ms,
                        "status": "complete",
                    },
                )
                assistant_saved = True
                # 可选：同步 drain 一次加速本地体验；默认依赖 worker
                yield ev
            else:
                if parsed:
                    acc.accumulate(*parsed)
                yield ev
    except asyncio.CancelledError:
        async def _finalize_partial():
            if not assistant_saved and (acc.timeline or acc.assistant_text):
                c.conversations.finalize_turn(
                    cid,
                    turn_id=turn["turn_id"],
                    assistant={
                        "text": acc.assistant_text,
                        "timeline": acc.timeline,
                        "sources": acc.all_sources,
                        "status": "interrupted",
                    },
                )
        await asyncio.shield(asyncio.to_thread(_finalize_partial))
        raise
    finally:
        # 若异常路径未保存且有部分输出，同样 finalize interrupted
        ...
```

`_TimelineAccumulator` 增加 `assistant_text`：在 `text_delta` 时拼接。

删除旧的 `append_exchange` + `_reindex_conversation` 同步整段重索引路径（改由 outbox）。

- [ ] **Step 4: 跑测试**

```bash
cd backend && python -m pytest tests/test_chat_persistence.py tests/test_api.py -q
```

Expected: PASS（必要时更新 `test_api` 适配新持久化）

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes.py backend/tests/test_chat_persistence.py frontend/src/api.ts frontend/src/hooks/chat/useAgentStream.ts
git commit -m "feat: persist chat turns before/after stream with client_message_id"
```

---

## Task 9: 归档后保留原文索引

**Files:**
- Modify: `backend/app/api/routes.py`（summarize 端点）
- Modify: `backend/app/engine/agent/tools.py`（`_summarize_conversation`）
- Modify: `backend/tests/test_summarize.py`
- Test: 扩展 summarize 测试

- [ ] **Step 1: 改测试预期**

将「归档后 `search_kb` / FTS 不再命中原会话」改为：

- 归档后 `conversation_summaries` 有 primary 关系
- 原消息仍可被 `ConversationFTS.query` 命中
- **不再**调用 `indexer.remove_conversation`

示例：

```python
def test_summarize_keeps_message_fts(tmp_path, ...):
    ...
    # after summarize
    hits = conversation_fts.query("漫剧", k=5)
    assert any(h.conversation_id == cid for h in hits)
```

- [ ] **Step 2: 跑失败（若旧代码仍 remove）**

```bash
cd backend && python -m pytest tests/test_summarize.py -q
```

- [ ] **Step 3: 删除 remove 调用**

在 `tools.py` 与 `routes.py` 去掉：

```python
self.indexer.remove_conversation(conversation_id)
c.indexer.remove_conversation(cid)
```

`mark_summarized` 改为写 `conversation_summaries`。可保留 `Indexer.remove_conversation` 方法供删除会话时使用，但归档不再调用。

- [ ] **Step 4: 跑通过并提交**

```bash
cd backend && python -m pytest tests/test_summarize.py -q
git add backend/app/api/routes.py backend/app/engine/agent/tools.py backend/app/engine/conversations.py backend/tests/test_summarize.py
git commit -m "fix: keep original conversation FTS after summarize archive"
```

---

## Task 10: Retriever 最小桥接（消息 FTS → search_kb）

**Files:**
- Modify: `backend/app/engine/retriever.py`
- Modify: `backend/app/engine/agent/tools.py`（conversation source 带 `message_id`）
- Modify: `backend/app/deps.py`
- Test: `backend/tests/test_retriever_conversation_v2.py`

- [ ] **Step 1: 写失败测试**

```python
def test_retriever_includes_conversation_message_hits(tmp_path, ...):
    # index one message via ConversationFTS
    # Retriever.search("关键词") 返回 source 含 conversation_id + message_id
    ...
```

- [ ] **Step 2: 实现桥接**

`Retriever.__init__` 增加可选 `conversation_fts: ConversationFTS | None`。

`search()`：

1. 现有知识 FTS + Vector（不变）
2. 若有 `conversation_fts`，合并其 `query` 结果
3. Hit/dict 增加字段：`message_id`, `start_char`, `end_char`, `offset_version`
4. **1A 不做 RRF/cursor**；简单按 score 排序截断 k

`tools._search_kb` 产出：

```python
{
  "type": "conversation",
  "cid": hit.conversation_id,
  "message_id": hit.message_id,
  "start_char": hit.start_char,
  "end_char": hit.end_char,
  "offset_version": "unicode-codepoint-v1",
  "excerpt": hit.text[:240],
}
```

Orchestrator `_source_key` 暂改（为 1A 防吞掉）：

```python
if st == "conversation":
    return f"conversation:{source.get('cid')}:{source.get('message_id')}:{source.get('start_char')}:{source.get('end_char')}"
```

前端 `dedupeSources` 同步改键（即使 1C 才做跳转，1A 也不能丢来源）。

- [ ] **Step 3: 跑通过并提交**

```bash
cd backend && python -m pytest tests/test_retriever_conversation_v2.py tests/test_agent_tools.py -q
# 前端若有 dedupe 单测一并跑
git add backend/app/engine/retriever.py backend/app/engine/agent/tools.py backend/app/engine/agent/orchestrator.py backend/app/deps.py frontend/src/api.ts backend/tests/test_retriever_conversation_v2.py
git commit -m "feat: bridge message-level conversation FTS into search_kb sources"
```

---

## Task 11: 删除会话清理 FTS + deletion ledger 写入

**Files:**
- Modify: `backend/app/engine/conversations.py`（delete）
- Modify: `backend/app/api/routes.py`（delete conversation 端点）
- Test: `backend/tests/test_conversation_delete.py`

- [ ] **Step 1: 测试**

```python
def test_delete_conversation_removes_fts_and_writes_ledger(tmp_path):
    ...
    store.delete(cid)
    assert fts.query("漫剧") == []
    ledger = (tmp_path / ".kb" / "migrations" / "conversation-deletions.jsonl").read_text(encoding="utf-8")
    assert cid in ledger
```

1A 删除选项可先固定：`delete_summary=true`，`forget_auto_memories` 忽略（无记忆层）。

- [ ] **Step 2: 实现**

删除事务：

1. append `conversation_deletion_ledger` + fsync jsonl ledger
2. cancel pending outbox for messages in cid
3. delete messages/turns/summaries/conversation row
4. `conversation_fts.delete_conversation(cid)`
5. 若有旧 `conv:{cid}` 文档级 FTS，也 `indexer.remove_conversation(cid)` 清遗留

- [ ] **Step 3: 提交**

```bash
git add backend/app/engine/conversations.py backend/app/api/routes.py backend/tests/test_conversation_delete.py
git commit -m "feat: delete conversations with FTS cleanup and deletion ledger"
```

---

## Task 12: 历史 FTS 回填命令 + 全量回归

**Files:**
- Create: `backend/app/engine/conversation_backfill.py`（或管理命令脚本）
- Test: `backend/tests/test_conversation_backfill.py`

- [ ] **Step 1: 测试**

```python
def test_backfill_indexes_all_retained_messages(tmp_path):
    # migrate sample shard with 2 messages, no outbox processed
    # run backfill
    # both messages queryable; second run is no-op / idempotent
    ...
```

- [ ] **Step 2: 实现**

`backfill_conversation_fts(store, fts, deletion_ledger_path)`：

1. 加载 deletion ledger，跳过已删 cid
2. 扫描全部 messages，对缺失/失败的 `index_fts` 重新入队或直接同步 upsert
3. 校验每条消息 `coverage_ok`

提供：

```bash
cd backend && python -m app.engine.conversation_backfill
```

（或 `python scripts/backfill_conversation_fts.py`，与仓库脚本风格一致）

- [ ] **Step 3: 全量回归**

```bash
cd backend && python -m pytest -q
```

Expected: 全绿。若有与本阶段无关的既有 flaky，在 PR 说明中标注，不在 1A 顺手大修。

- [ ] **Step 4: Commit**

```bash
git add backend/app/engine/conversation_backfill.py backend/tests/test_conversation_backfill.py
git commit -m "feat: backfill conversation message FTS from SQLite store"
```

---

## 1A 验收清单（对照 spec）

| 验收项 | 对应 Task |
|--------|----------|
| SQLite 为会话规范存储；JSON 迁移幂等 | 5, 6 |
| 稳定 workspace_id | 1 |
| 用户消息先于 Agent 落盘；本轮 history 不重复 | 8 |
| client_message_id 幂等 / 409 turn_in_progress | 5, 8 |
| interrupted 助手可保存 | 8 |
| 消息全文分块覆盖；secret 等长掩码 | 2, 3, 7 |
| conversation_chunks_v2 upsert/query | 4, 7 |
| 归档后原文仍可 FTS | 9, 10 |
| search_kb 可返回 message_id 级会话来源 | 10 |
| 删除清理 FTS + ledger | 11 |
| 历史回填幂等 | 12 |
| 不实现 Vector / 记忆.md / 自动学习 | 全计划范围外 |

---

## Plan Self-Review

1. **Spec coverage (阶段 1A):** §6.1 存储/turn/迁移 → Tasks 5–6,8；§6.2 分块/secret/FTS v2 → Tasks 2–4,7；归档保留检索 → Task 9；删除 ledger → Task 11；回填 → Task 12；search 桥接为 1A 可用性最小集 → Task 10。1B/1C/2/3 明确排除。
2. **Placeholders:** 无 TBD；Task 8 明确复用 `conftest.client` 与 `TurnInProgress → 409` 的 monkeypatch 路径。
3. **Type consistency:** 消息字段统一 `text`/`ts`/`id`；FTS hit 使用 `conversation_id`/`message_id`/`start_char`/`end_char`/`offset_version=unicode-codepoint-v1`；outbox kind 仅实际入队 `index_fts`。

---

## 执行方式

Plan complete and saved to `docs/superpowers/plans/2026-07-14-second-brain-phase-1a.md`.

**两种执行选项：**

1. **Subagent-Driven（推荐）** — 每个 Task 派一个新子代理，任务间人工/父代理复查，迭代快  
2. **Inline Execution** — 本会话用 executing-plans 按批执行并设检查点  

选哪种？
