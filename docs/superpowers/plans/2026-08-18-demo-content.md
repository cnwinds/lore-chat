# Demo 内容与快照工具链 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在一台普通实例上按剧本真跑出一份有厚度、可交叉跳转的演示知识库与六条会话，人工定稿后以纯文本固化进 git，并能被确定性地重建成演示站的运行时知识库。

**Architecture:** 空库起步 → `demo/seed/run.py` 按 `script.yaml` 驱动真实 HTTP API 跑出内容 → 人工修改（Markdown 直接改，会话与记忆经 `dump.py` / `load.py` 的 JSON 往返）→ 定稿产物以纯文本进 git（`demo/knowledge/`、`demo/conversations/*.json`、`demo/memory.json`、`demo/manifest.json`）→ `demo/build.py` 物化到运行时 KB、按「距今多少天」平移时间戳、重建索引。部署与重置是同一条路径。

**Tech Stack:** Python 3（标准库 + `httpx` + `pyyaml`）、SQLite、pytest。

## Global Constraints

- 设计依据：`docs/superpowers/specs/2026-08-18-demo-mode-design.md` §10-11。
- **SQLite 一律不进 git。** 进 git 的只有 Markdown 与 JSON。
- **绝不能提交**：`.kb/settings.json`、`.kb/auth.json`、`.kb/sessions.json`、任何 `*.db` / `*.db-wal` / `*.db-shm`、`.kb/index/`、`*_cooldown.json`。这条由 CI 检查钉死（Task 7）。
- 记忆事实必须逐条通过 `AGENTS.md` §2 的三道门槛（关于主人 / 耐久性 / 语境保全）。演示站的记忆面板是对外的记忆质量样板，写错等于对外示范错误用法。
- 所有访谈对象用化名；页脚要有一行「演示内容为虚构示例」。
- 真跑用的实例**必须** `DEMO_MODE=0`（demo 下写工具只出预览，跑不出内容）。
- 时间戳一律相对化：`manifest.json` 存 `reference_date`，构建时平移。
- 本计划不依赖 `2026-08-18-demo-runtime.md` 的任何 Task，可并行推进。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `demo/README.md` | 内容生产与构建流程说明 |
| `demo/manifest.json` | `reference_date`、内容版本、构建元数据 |
| `demo/assets/knowledge/` | 前置资产：系统层与 Skill 包（人工撰写，真跑前导入） |
| `demo/seed/script.yaml` | 六条会话的剧本 |
| `demo/seed/run.py` | 按剧本驱动真实 API 产出内容 |
| `demo/tools/dump.py` | KB 的 SQLite → JSON |
| `demo/tools/load.py` | JSON → KB 的 SQLite |
| `demo/tools/timeshift.py` | 时间戳平移纯函数 |
| `demo/build.py` | 物化 `demo/` 内容为运行时 KB 并重建索引 |
| `demo/knowledge/` | 定稿后的 Markdown 与附件（Task 6 产出） |
| `demo/conversations/*.json` | 定稿后的会话（Task 6 产出） |
| `demo/memory.json` | 定稿后的记忆事实（Task 6 产出） |
| `scripts/check_demo_content.py` | CI：拦截密钥与二进制入库 |
| `demo/tests/` | 工具链测试 |

**运行时路径参考（读代码得来，不要猜）**

- 会话库：`{KB_PATH}/.kb/conversations/conversations.db`（`backend/app/engine/conversations.py:152`）
- 记忆库：`{KB_PATH}/.kb/memory/memory.db`（`backend/app/deps.py:114-117`）
- 建索引：`app.backup.reindex.reindex_all(container)`（`backend/app/backup/reindex.py:53`）

---

## Task 1: demo 目录骨架与 manifest

**Files:**
- Create: `demo/README.md`
- Create: `demo/manifest.json`
- Create: `demo/tools/__init__.py`
- Test: `demo/tests/test_manifest.py`

**Interfaces:**
- Produces: `demo/manifest.json` 结构
  ```json
  {
    "format_version": 1,
    "reference_date": "2026-08-18",
    "content_version": "0.1.0",
    "persona": "林知遥",
    "highlight_conversation": null
  }
  ```
  `highlight_conversation` 在 Task 6 定稿时填入首屏高光会话的 id。

- [ ] **Step 1: 写失败的测试**

创建 `demo/tests/test_manifest.py`：

```python
import json
from datetime import date
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.json"


def test_manifest_exists_and_parses():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["format_version"] == 1


def test_reference_date_is_iso():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    date.fromisoformat(data["reference_date"])


def test_manifest_declares_required_keys():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key in ("format_version", "reference_date", "content_version", "persona"):
        assert key in data
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest ../demo/tests/test_manifest.py -v`
Expected: FAIL，`FileNotFoundError: manifest.json`

- [ ] **Step 3: 实现**

创建 `demo/manifest.json`：

```json
{
  "format_version": 1,
  "reference_date": "2026-08-18",
  "content_version": "0.1.0",
  "persona": "林知遥",
  "highlight_conversation": null
}
```

创建 `demo/tools/__init__.py`（空文件）。

创建 `demo/README.md`：

```markdown
# 演示内容

演示站的知识库、会话与记忆事实。设计见
`docs/superpowers/specs/2026-08-18-demo-mode-design.md` §10-11。

## 进 git 的是什么

| 路径 | 内容 |
|------|------|
| `knowledge/` | 全部 Markdown 与附件，原样即定稿 |
| `conversations/*.json` | 每会话一个，`tools/dump.py` 产出 |
| `memory.json` | 记忆事实 |
| `manifest.json` | `reference_date` 等构建元数据 |

**SQLite 一律不进 git**：`*.db` 是构建产物，不是源。

## 生产流程

1. 准备一台普通实例（`DEMO_MODE=0`、空 KB、配好模型链与搜索 provider）
2. `python demo/seed/run.py --base-url http://localhost:8080 --password <管理员密码>`
3. 人工定稿：Markdown 直接改；会话与记忆用 `tools/dump.py` 导出改完再 `tools/load.py` 导回
4. `python demo/tools/dump.py --kb <实例 KB 路径> --out demo/`
5. 提交 `demo/`

## 构建（部署即重置）

```bash
python demo/build.py --kb /data/knowledge
```

会清空运行时 KB、从 `knowledge/` 物化、灌入会话与记忆、按「距今多少天」平移时间戳、重建索引。
演示站容器每次启动执行一次，任何运行期漂移自动消失。
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest ../demo/tests/test_manifest.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add demo
git commit -m "chore(demo): 演示内容目录骨架与 manifest"
```

---

## Task 2: 时间戳平移

**Files:**
- Create: `demo/tools/timeshift.py`
- Test: `demo/tests/test_timeshift.py`

**Interfaces:**
- Produces:
  - `compute_offset_days(reference_date: str, today: date) -> int`
  - `shift_iso_timestamp(value: str, offset_days: int) -> str`（非法值原样返回）
  - `shift_in_place(obj: Any, offset_days: int, keys: set[str]) -> Any`（递归处理 dict / list）

**为什么需要：** 真跑那天是什么日期，会话与文档就永远停在那天。三个月后访客看到最新一条会话是三个月前的，演示站的可信度直接掉一档。

- [ ] **Step 1: 写失败的测试**

创建 `demo/tests/test_timeshift.py`：

```python
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.timeshift import compute_offset_days, shift_in_place, shift_iso_timestamp


def test_compute_offset_days():
    assert compute_offset_days("2026-08-18", date(2026, 9, 17)) == 30
    assert compute_offset_days("2026-08-18", date(2026, 8, 18)) == 0


def test_shift_iso_timestamp_keeps_time_of_day():
    out = shift_iso_timestamp("2026-08-18T09:30:00+00:00", 30)
    assert out.startswith("2026-09-17T09:30:00")


def test_shift_iso_timestamp_handles_zulu():
    assert shift_iso_timestamp("2026-08-18T09:30:00Z", 1).startswith("2026-08-19T09:30:00")


def test_shift_iso_timestamp_passes_through_garbage():
    assert shift_iso_timestamp("not-a-date", 30) == "not-a-date"
    assert shift_iso_timestamp("", 30) == ""


def test_shift_in_place_walks_nested_structures():
    payload = {
        "created_at": "2026-08-18T00:00:00+00:00",
        "title": "不该动",
        "messages": [{"ts": "2026-08-18T01:00:00+00:00", "text": "也不该动"}],
    }
    out = shift_in_place(payload, 1, {"created_at", "ts"})
    assert out["created_at"].startswith("2026-08-19")
    assert out["messages"][0]["ts"].startswith("2026-08-19")
    assert out["title"] == "不该动"
    assert out["messages"][0]["text"] == "也不该动"


def test_zero_offset_is_identity():
    payload = {"ts": "2026-08-18T00:00:00+00:00"}
    assert shift_in_place(payload, 0, {"ts"})["ts"] == "2026-08-18T00:00:00+00:00"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest ../demo/tests/test_timeshift.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'tools.timeshift'`

- [ ] **Step 3: 实现**

创建 `demo/tools/timeshift.py`：

```python
"""把定稿时的绝对时间戳整体平移到「距今多少天」的当前时间。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def compute_offset_days(reference_date: str, today: date) -> int:
    return (today - date.fromisoformat(reference_date)).days


def shift_iso_timestamp(value: str, offset_days: int) -> str:
    if not value or offset_days == 0:
        return value
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return value
    return (parsed + timedelta(days=offset_days)).isoformat()


def shift_in_place(obj: Any, offset_days: int, keys: set[str]) -> Any:
    if offset_days == 0:
        return obj
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in keys and isinstance(value, str):
                obj[key] = shift_iso_timestamp(value, offset_days)
            else:
                shift_in_place(value, offset_days, keys)
    elif isinstance(obj, list):
        for item in obj:
            shift_in_place(item, offset_days, keys)
    return obj
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest ../demo/tests/test_timeshift.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add demo/tools/timeshift.py demo/tests/test_timeshift.py
git commit -m "feat(demo): 演示内容时间戳平移工具"
```

---

## Task 3: 会话与记忆的 dump / load

**Files:**
- Create: `demo/tools/dump.py`
- Create: `demo/tools/load.py`
- Test: `demo/tests/test_dump_load.py`

**Interfaces:**
- Produces:
  - `dump_conversations(db_path: Path) -> list[dict]`：每会话一个 dict，键为 `conversation` / `messages` / `turns` / `summaries` / `system_events`
  - `dump_memory(db_path: Path) -> dict`：键为 `facts` / `evidence`
  - `write_dump(kb_path: Path, out_dir: Path) -> None`
  - `load_conversations(db_path: Path, payloads: list[dict]) -> None`
  - `load_memory(db_path: Path, payload: dict) -> None`
  - `read_and_load(kb_path: Path, content_dir: Path, offset_days: int = 0) -> None`

**表结构（读代码得来）**

- `conversations(id, title, created_at, updated_at, active_turn_id, indexed_dirty)`
- `messages(id, conversation_id, seq, role, text, ts, status, client_message_id, in_reply_to_message_id, timeline_json, sources_json, total_duration_ms, doc_context_json, attachments_json, primary_doc, model_name, model_failover, web_enabled)`
- `turns(id, conversation_id, client_message_id, user_message_id, assistant_message_id, status, observation_allowed, locked_by, locked_until, started_at, finalized_at)`
- `conversation_summaries(...)`、`conversation_system_events(...)`
- `memory_facts(...)`、`memory_evidence(...)`

**不导出**：`derivation_outbox`（运行时队列）、`conversation_deletion_ledger`、`migration_meta`、`memory_render_state`、`memory_tombstones`、`memory_source_barriers`。它们是运行状态而非内容。

- [ ] **Step 1: 写失败的测试**

创建 `demo/tests/test_dump_load.py`：

```python
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.dump import dump_conversations, dump_memory, write_dump
from tools.load import load_conversations, load_memory

CONV_DDL = """
CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  active_turn_id TEXT, indexed_dirty INTEGER NOT NULL DEFAULT 0);
CREATE TABLE messages (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
  seq INTEGER NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL DEFAULT '',
  ts TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'complete',
  client_message_id TEXT, in_reply_to_message_id TEXT, timeline_json TEXT,
  sources_json TEXT, total_duration_ms INTEGER, doc_context_json TEXT,
  attachments_json TEXT, primary_doc TEXT, model_name TEXT,
  model_failover INTEGER NOT NULL DEFAULT 0, web_enabled INTEGER);
CREATE TABLE turns (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
  client_message_id TEXT NOT NULL, user_message_id TEXT NOT NULL,
  assistant_message_id TEXT, status TEXT NOT NULL DEFAULT 'running',
  observation_allowed INTEGER NOT NULL DEFAULT 0, locked_by TEXT,
  locked_until TEXT, started_at TEXT NOT NULL, finalized_at TEXT);
CREATE TABLE conversation_summaries (id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id TEXT NOT NULL, doc_path TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 1, covered_through_message_id TEXT,
  status TEXT NOT NULL DEFAULT 'current', is_primary INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);
CREATE TABLE conversation_system_events (id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL, event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL, created_at TEXT NOT NULL);
"""

MEM_DDL = """
CREATE TABLE memory_facts (id TEXT PRIMARY KEY, owner_key TEXT NOT NULL,
  slot_key TEXT NOT NULL, category TEXT NOT NULL, statement TEXT NOT NULL,
  normalized_value_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'confirmed',
  origin TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 1.0,
  sensitivity TEXT NOT NULL DEFAULT 'normal', first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL, confirmed_at TEXT, valid_until TEXT,
  supersedes_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE memory_evidence (fact_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
  message_id TEXT NOT NULL, start_char INTEGER NOT NULL, end_char INTEGER NOT NULL,
  quote_hash TEXT NOT NULL, observed_at TEXT NOT NULL);
"""


def _seed_conv(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(CONV_DDL)
    conn.execute(
        "INSERT INTO conversations VALUES ('c1','选型','2026-08-18T00:00:00+00:00',"
        "'2026-08-18T01:00:00+00:00',NULL,0)"
    )
    conn.execute(
        "INSERT INTO messages (id,conversation_id,seq,role,text,ts) "
        "VALUES ('m1','c1',1,'user','向量库怎么选','2026-08-18T00:10:00+00:00')"
    )
    conn.commit()
    conn.close()


def _seed_mem(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(MEM_DDL)
    conn.execute(
        "INSERT INTO memory_facts VALUES ('f1','w1','identity','identity',"
        "'独立开发者','h1','confirmed','user',1.0,'normal',"
        "'2026-08-18T00:00:00+00:00','2026-08-18T00:00:00+00:00',NULL,NULL,NULL,"
        "'2026-08-18T00:00:00+00:00','2026-08-18T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()


def test_dump_conversations_groups_by_conversation(tmp_path):
    db = tmp_path / "conversations.db"
    _seed_conv(db)
    out = dump_conversations(db)
    assert len(out) == 1
    assert out[0]["conversation"]["id"] == "c1"
    assert out[0]["messages"][0]["text"] == "向量库怎么选"


def test_dump_memory_returns_facts(tmp_path):
    db = tmp_path / "memory.db"
    _seed_mem(db)
    out = dump_memory(db)
    assert out["facts"][0]["statement"] == "独立开发者"


def test_write_dump_emits_one_json_per_conversation(tmp_path):
    kb = tmp_path / "knowledge"
    (kb / ".kb" / "conversations").mkdir(parents=True)
    (kb / ".kb" / "memory").mkdir(parents=True)
    _seed_conv(kb / ".kb" / "conversations" / "conversations.db")
    _seed_mem(kb / ".kb" / "memory" / "memory.db")
    out_dir = tmp_path / "content"
    write_dump(kb, out_dir)
    assert (out_dir / "conversations" / "c1.json").is_file()
    assert json.loads((out_dir / "memory.json").read_text(encoding="utf-8"))["facts"]


def test_load_roundtrip_restores_rows(tmp_path):
    src = tmp_path / "src.db"
    _seed_conv(src)
    payloads = dump_conversations(src)

    dst = tmp_path / "dst.db"
    conn = sqlite3.connect(dst)
    conn.executescript(CONV_DDL)
    conn.commit()
    conn.close()

    load_conversations(dst, payloads)
    conn = sqlite3.connect(dst)
    rows = conn.execute("SELECT id, text FROM messages").fetchall()
    conn.close()
    assert rows == [("m1", "向量库怎么选")]


def test_load_memory_roundtrip(tmp_path):
    src = tmp_path / "src.db"
    _seed_mem(src)
    payload = dump_memory(src)

    dst = tmp_path / "dst.db"
    conn = sqlite3.connect(dst)
    conn.executescript(MEM_DDL)
    conn.commit()
    conn.close()

    load_memory(dst, payload)
    conn = sqlite3.connect(dst)
    rows = conn.execute("SELECT statement FROM memory_facts").fetchall()
    conn.close()
    assert rows == [("独立开发者",)]


def test_load_is_idempotent(tmp_path):
    src = tmp_path / "src.db"
    _seed_conv(src)
    payloads = dump_conversations(src)
    dst = tmp_path / "dst.db"
    conn = sqlite3.connect(dst)
    conn.executescript(CONV_DDL)
    conn.commit()
    conn.close()

    load_conversations(dst, payloads)
    load_conversations(dst, payloads)
    conn = sqlite3.connect(dst)
    count = conn.execute("SELECT count(*) FROM messages").fetchone()[0]
    conn.close()
    assert count == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest ../demo/tests/test_dump_load.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'tools.dump'`

- [ ] **Step 3: 实现 dump**

创建 `demo/tools/dump.py`：

```python
"""KB 的 SQLite → 可 diff 的 JSON。会话与记忆因此能被人工编辑与 review。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

CONVERSATION_TABLES = (
    "messages",
    "turns",
    "conversation_summaries",
    "conversation_system_events",
)

CONVERSATIONS_DB_REL = Path(".kb") / "conversations" / "conversations.db"
MEMORY_DB_REL = Path(".kb") / "memory" / "memory.db"


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def dump_conversations(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    try:
        out: list[dict] = []
        for conv in _rows(conn, "SELECT * FROM conversations ORDER BY created_at"):
            payload = {"conversation": conv}
            for table in CONVERSATION_TABLES:
                order = " ORDER BY seq" if table == "messages" else ""
                payload[table] = _rows(
                    conn,
                    f"SELECT * FROM {table} WHERE conversation_id = ?{order}",
                    (conv["id"],),
                )
            out.append(payload)
        return out
    finally:
        conn.close()


def dump_memory(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        return {
            "facts": _rows(conn, "SELECT * FROM memory_facts ORDER BY created_at"),
            "evidence": _rows(conn, "SELECT * FROM memory_evidence"),
        }
    finally:
        conn.close()


def write_dump(kb_path: Path, out_dir: Path) -> None:
    conv_dir = out_dir / "conversations"
    conv_dir.mkdir(parents=True, exist_ok=True)
    for payload in dump_conversations(kb_path / CONVERSATIONS_DB_REL):
        cid = payload["conversation"]["id"]
        (conv_dir / f"{cid}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    memory = dump_memory(kb_path / MEMORY_DB_REL)
    (out_dir / "memory.json").write_text(
        json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="导出演示会话与记忆为 JSON")
    parser.add_argument("--kb", required=True, type=Path, help="实例的 KB 目录")
    parser.add_argument("--out", required=True, type=Path, help="输出目录（通常是 demo/）")
    args = parser.parse_args()
    write_dump(args.kb, args.out)
    print(f"已导出到 {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 实现 load**

创建 `demo/tools/load.py`：

```python
"""JSON → KB 的 SQLite。表结构由 app 侧建好，这里只灌数据。"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from tools.dump import CONVERSATIONS_DB_REL, MEMORY_DB_REL
from tools.timeshift import shift_in_place

TIMESTAMP_KEYS = {
    "created_at",
    "updated_at",
    "ts",
    "started_at",
    "finalized_at",
    "observed_at",
    "first_seen_at",
    "last_seen_at",
    "confirmed_at",
}


def _upsert(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    for row in rows:
        cols = ", ".join(row.keys())
        marks = ", ".join("?" for _ in row)
        conn.execute(
            f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({marks})",
            tuple(row.values()),
        )


def load_conversations(db_path: Path, payloads: list[dict]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        for payload in payloads:
            _upsert(conn, "conversations", [payload["conversation"]])
            for table in (
                "messages",
                "turns",
                "conversation_summaries",
                "conversation_system_events",
            ):
                _upsert(conn, table, payload.get(table) or [])
        conn.commit()
    finally:
        conn.close()


def load_memory(db_path: Path, payload: dict) -> None:
    conn = sqlite3.connect(db_path)
    try:
        _upsert(conn, "memory_facts", payload.get("facts") or [])
        _upsert(conn, "memory_evidence", payload.get("evidence") or [])
        conn.commit()
    finally:
        conn.close()


def read_and_load(kb_path: Path, content_dir: Path, offset_days: int = 0) -> None:
    payloads = []
    conv_dir = content_dir / "conversations"
    if conv_dir.is_dir():
        for path in sorted(conv_dir.glob("*.json")):
            payloads.append(json.loads(path.read_text(encoding="utf-8")))
    shift_in_place(payloads, offset_days, TIMESTAMP_KEYS)
    load_conversations(kb_path / CONVERSATIONS_DB_REL, payloads)

    memory_file = content_dir / "memory.json"
    if memory_file.is_file():
        memory = json.loads(memory_file.read_text(encoding="utf-8"))
        shift_in_place(memory, offset_days, TIMESTAMP_KEYS)
        load_memory(kb_path / MEMORY_DB_REL, memory)


def main() -> None:
    parser = argparse.ArgumentParser(description="把 JSON 会话与记忆导回实例")
    parser.add_argument("--kb", required=True, type=Path)
    parser.add_argument("--content", required=True, type=Path, help="通常是 demo/")
    parser.add_argument("--offset-days", type=int, default=0)
    args = parser.parse_args()
    read_and_load(args.kb, args.content, args.offset_days)
    print(f"已导入到 {args.kb}")


if __name__ == "__main__":
    main()
```

`demo/tools/load.py` 里用了 `from tools.xxx import`，因此运行时需要把 `demo/` 加进 `sys.path`（`demo/build.py` 与测试均已处理；命令行直接跑时用 `cd demo && python -m tools.load ...`）。在 `demo/README.md` 的流程段落把命令改成 `cd demo && python -m tools.dump --kb <路径> --out .`。

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest ../demo/tests/test_dump_load.py -v`
Expected: 6 passed

- [ ] **Step 6: 提交**

```bash
git add demo/tools demo/tests/test_dump_load.py demo/README.md
git commit -m "feat(demo): 会话与记忆的 JSON dump/load 工具"
```

---

## Task 4: 构建脚本（部署即重置）

**Files:**
- Create: `demo/build.py`
- Test: `demo/tests/test_build.py`

**Interfaces:**
- Consumes: `read_and_load`（Task 3）、`compute_offset_days`（Task 2）
- Produces:
  - `materialize(content_dir: Path, kb_path: Path, today: date | None = None, reindex: bool = True) -> dict`
  - 返回 `{"docs": int, "conversations": int, "offset_days": int}`

**顺序（不可颠倒）：** 清空运行时 KB → 拷贝 `knowledge/` → 由 app 侧建表（构造 Container 会建 DDL）→ 灌会话与记忆 → 平移时间戳（在灌入时一并完成）→ 重建索引。

- [ ] **Step 1: 写失败的测试**

创建 `demo/tests/test_build.py`：

```python
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build import materialize


def _content(tmp_path: Path) -> Path:
    content = tmp_path / "content"
    (content / "knowledge" / "技术").mkdir(parents=True)
    (content / "knowledge" / "技术" / "a.md").write_text("# A\n正文\n", encoding="utf-8")
    (content / "conversations").mkdir(parents=True)
    (content / "conversations" / "c1.json").write_text(
        json.dumps(
            {
                "conversation": {
                    "id": "c1",
                    "title": "选型",
                    "created_at": "2026-08-18T00:00:00+00:00",
                    "updated_at": "2026-08-18T01:00:00+00:00",
                    "active_turn_id": None,
                    "indexed_dirty": 0,
                },
                "messages": [
                    {
                        "id": "m1",
                        "conversation_id": "c1",
                        "seq": 1,
                        "role": "user",
                        "text": "向量库怎么选",
                        "ts": "2026-08-18T00:10:00+00:00",
                        "status": "complete",
                    }
                ],
                "turns": [],
                "conversation_summaries": [],
                "conversation_system_events": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (content / "memory.json").write_text(
        json.dumps({"facts": [], "evidence": []}), encoding="utf-8"
    )
    (content / "manifest.json").write_text(
        json.dumps({"format_version": 1, "reference_date": "2026-08-18"}),
        encoding="utf-8",
    )
    return content


def test_materialize_copies_markdown(tmp_path):
    content = _content(tmp_path)
    kb = tmp_path / "knowledge"
    materialize(content, kb, today=date(2026, 8, 18), reindex=False)
    assert (kb / "技术" / "a.md").read_text(encoding="utf-8").startswith("# A")


def test_materialize_loads_conversations(tmp_path):
    import sqlite3

    content = _content(tmp_path)
    kb = tmp_path / "knowledge"
    materialize(content, kb, today=date(2026, 8, 18), reindex=False)
    conn = sqlite3.connect(kb / ".kb" / "conversations" / "conversations.db")
    rows = conn.execute("SELECT id FROM conversations").fetchall()
    conn.close()
    assert rows == [("c1",)]


def test_materialize_shifts_timestamps(tmp_path):
    import sqlite3

    content = _content(tmp_path)
    kb = tmp_path / "knowledge"
    result = materialize(content, kb, today=date(2026, 9, 17), reindex=False)
    assert result["offset_days"] == 30
    conn = sqlite3.connect(kb / ".kb" / "conversations" / "conversations.db")
    ts = conn.execute("SELECT ts FROM messages WHERE id='m1'").fetchone()[0]
    conn.close()
    assert ts.startswith("2026-09-17")


def test_materialize_wipes_previous_drift(tmp_path):
    content = _content(tmp_path)
    kb = tmp_path / "knowledge"
    kb.mkdir(parents=True)
    (kb / "脏文件.md").write_text("访客留下的漂移", encoding="utf-8")
    materialize(content, kb, today=date(2026, 8, 18), reindex=False)
    assert not (kb / "脏文件.md").exists()


def test_materialize_is_repeatable(tmp_path):
    content = _content(tmp_path)
    kb = tmp_path / "knowledge"
    first = materialize(content, kb, today=date(2026, 8, 18), reindex=False)
    second = materialize(content, kb, today=date(2026, 8, 18), reindex=False)
    assert first == second
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest ../demo/tests/test_build.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'build'`

- [ ] **Step 3: 实现**

创建 `demo/build.py`：

```python
"""把 demo/ 的纯文本内容物化成运行时知识库。

部署与重置是同一条路径：演示站容器每次启动跑一次，运行期漂移自动消失。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.load import read_and_load  # noqa: E402
from tools.timeshift import compute_offset_days  # noqa: E402


def _wipe(kb_path: Path) -> None:
    if kb_path.exists():
        shutil.rmtree(kb_path)
    kb_path.mkdir(parents=True, exist_ok=True)


def _copy_knowledge(content_dir: Path, kb_path: Path) -> int:
    src = content_dir / "knowledge"
    if not src.is_dir():
        return 0
    shutil.copytree(src, kb_path, dirs_exist_ok=True)
    return sum(1 for _ in kb_path.rglob("*.md"))


def _init_schema(kb_path: Path) -> None:
    """借 app 侧建表，避免在 demo 工具里复制一份会漂移的 DDL。"""
    from app.engine.conversations import ConversationStore
    from app.engine.memory.store import MemoryStore

    ConversationStore(kb_path / ".kb" / "conversations")
    MemoryStore(kb_path / ".kb" / "memory" / "memory.db", owner_key="demo")


def _reindex(kb_path: Path) -> None:
    from app.config import Settings
    from app.backup.reindex import reindex_all
    from app.deps import build_container

    settings = Settings(kb_path=kb_path)
    reindex_all(build_container(settings))


def materialize(
    content_dir: Path,
    kb_path: Path,
    today: date | None = None,
    reindex: bool = True,
) -> dict:
    manifest = json.loads((content_dir / "manifest.json").read_text(encoding="utf-8"))
    offset = compute_offset_days(manifest["reference_date"], today or date.today())

    _wipe(kb_path)
    docs = _copy_knowledge(content_dir, kb_path)
    _init_schema(kb_path)
    read_and_load(kb_path, content_dir, offset_days=offset)

    conv_dir = content_dir / "conversations"
    conversations = len(list(conv_dir.glob("*.json"))) if conv_dir.is_dir() else 0

    if reindex:
        _reindex(kb_path)

    return {"docs": docs, "conversations": conversations, "offset_days": offset}


def main() -> None:
    parser = argparse.ArgumentParser(description="构建演示站运行时知识库")
    parser.add_argument("--kb", required=True, type=Path)
    parser.add_argument("--content", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--no-reindex", action="store_true")
    args = parser.parse_args()
    result = materialize(args.content, args.kb, reindex=not args.no_reindex)
    print(
        f"已构建：{result['docs']} 篇文档、{result['conversations']} 条会话、"
        f"时间平移 {result['offset_days']} 天"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest ../demo/tests/test_build.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add demo/build.py demo/tests/test_build.py
git commit -m "feat(demo): 演示内容构建脚本（部署即重置）"
```

---

## Task 5: 剧本与真跑脚本

**Files:**
- Create: `demo/seed/script.yaml`
- Create: `demo/seed/run.py`
- Create: `demo/assets/knowledge/系统/戒律.md`
- Create: `demo/assets/knowledge/系统/心法.md`
- Create: `demo/assets/knowledge/技能/周报生成/SKILL.md`
- Create: `demo/assets/knowledge/技能/周报生成/模板.md`
- Create: `demo/assets/knowledge/技能/竞品调研/SKILL.md`
- Create: `demo/assets/knowledge/技能/竞品调研/调研维度清单.md`
- Test: `demo/tests/test_script.py`

**Interfaces:**
- Produces:
  - `demo/seed/script.yaml` 结构：
    ```yaml
    conversations:
      - key: retrieval-selection
        note: 展示联网调研 + 落库
        skills: []
        turns:
          - text: "我在做一个面向教培场景的 AI 学习产品……"
            web_enabled: true
            doc_context: []
    ```
  - `load_script(path: Path) -> dict`
  - `validate_script(script: dict) -> list[str]`（返回问题列表，空表示通过）

**前置资产为什么单独放：** 系统层《戒律》《心法》与 Skill 包是人工撰写的输入，不是跑出来的产物。真跑前由 `run.py` 第 0 步导入，之后才有「按周报 Skill 出周报」这条会话可跑。

- [ ] **Step 1: 写失败的测试**

创建 `demo/tests/test_script.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seed.run import load_script, validate_script

SCRIPT = Path(__file__).resolve().parents[1] / "seed" / "script.yaml"


def test_script_parses():
    assert load_script(SCRIPT)["conversations"]


def test_script_has_six_conversations():
    assert len(load_script(SCRIPT)["conversations"]) == 6


def test_script_keys_are_unique():
    keys = [c["key"] for c in load_script(SCRIPT)["conversations"]]
    assert len(keys) == len(set(keys))


def test_script_passes_validation():
    assert validate_script(load_script(SCRIPT)) == []


def test_validation_catches_empty_turns():
    problems = validate_script({"conversations": [{"key": "a", "turns": []}]})
    assert problems


def test_validation_catches_duplicate_keys():
    script = {
        "conversations": [
            {"key": "a", "turns": [{"text": "x"}]},
            {"key": "a", "turns": [{"text": "y"}]},
        ]
    }
    assert validate_script(script)


def test_skill_assets_have_trigger_header():
    """无 YAML 触发头的 Skill 包在启用与对话时都会报错。"""
    root = Path(__file__).resolve().parents[1] / "assets" / "knowledge" / "技能"
    for skill_md in root.rglob("SKILL.md"):
        text = skill_md.read_text(encoding="utf-8")
        assert text.startswith("---"), skill_md
        assert "name:" in text and "description:" in text, skill_md
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest ../demo/tests/test_script.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'seed.run'`

- [ ] **Step 3: 写前置资产**

按 `CONTEXT.md` 的 Skill 正文头硬约束（`SKILL.md` 开头必须有 `---` YAML，含非空 `name` 与 `description`），创建：

`demo/assets/knowledge/技能/周报生成/SKILL.md`：

```markdown
---
name: 周报生成
description: 当需要把一段时间内的进展整理成周报时使用。会先检索本周相关文档与会话，再按模板成文。
---

# 周报生成

## 步骤

1. `list_kb_structure` 确认「运营/周报」下最近一期的编号与格式
2. `search_kb` 检索本周新增或更新的文档，范围覆盖知识库与会话
3. 读取 `技能/周报生成/模板.md`，按其结构组织内容
4. 每条进展必须给出来源文档路径，没有来源的不写
5. `write_doc` 写入 `运营/周报/<年>-W<周数>.md`

## 边界

- 不臆造未在知识库中出现的进展
- 与用户当次消息冲突时以用户消息为准
```

`demo/assets/knowledge/技能/周报生成/模板.md`：正文包含「本周完成 / 进行中 / 下周计划 / 风险与待决」四段，每段说明写法与来源要求。

`demo/assets/knowledge/技能/竞品调研/SKILL.md`：同样的 YAML 头，描述何时使用（需要横向对比外部产品或方案时），步骤覆盖读取维度清单 → 联网检索 → 逐维度填表 → 落库。

`demo/assets/knowledge/技能/竞品调研/调研维度清单.md`：定位、目标用户、核心能力、数据与隐私、部署形态、定价、我们的差异点。

`demo/assets/knowledge/系统/戒律.md` 与 `心法.md`：按人物设定写行为策略与处世准则，语气与产品一致，不含任何真实密钥、真实人名或可识别信息。

- [ ] **Step 4: 写剧本**

创建 `demo/seed/script.yaml`，六条会话与 spec §10.3 一一对应：

```yaml
# 演示内容剧本。每条会话对应 spec §10.3 表格的一行。
# 真跑用普通实例（DEMO_MODE=0），跑完人工定稿。
persona: 林知遥
conversations:
  - key: retrieval-selection
    note: 联网调研 + 多来源对比 + 落库；首屏高光会话
    skills: []
    turns:
      - text: >-
          我在做一个面向教培场景的 AI 学习产品，要给老师和学生的资料做检索。
          向量库这块现在有哪些主流选择，各自适合什么规模？帮我横向比一下。
        web_enabled: true
      - text: 我们初期数据量不大，但要本地部署、不能把资料传到外部服务。按这个约束再收敛一下。
        web_enabled: true
      - text: 把结论整理成一篇笔记存进知识库。
        web_enabled: false

  - key: chunking-experiment
    note: edit_doc 局部编辑；新建实验记录
    skills: []
    turns:
      - text: 打开那篇向量库选型的笔记，我们实测了几组分块参数，想把实测数据补进去。
        web_enabled: false
      - text: >-
          实测是这样：512 字无重叠召回偏低；512 字 + 80 字重叠明显变好；
          1024 字 + 150 字重叠在长文档上最好但短问答会带噪声。把这段补到笔记的对应小节。
        web_enabled: false
      - text: 另外把这次实验的完整过程单独记一篇实验记录。
        web_enabled: false

  - key: interview-notes
    note: 非结构化 → 结构化；AI 判断归位，用户全程不指定路径
    skills: []
    turns:
      - text: >-
          这是我今天跟一位初中数学老师聊完的原始记录，很乱，帮我整理一下：
          （此处在真跑前替换为一段 400-600 字的虚构访谈原文，对象化名「王老师」）
        web_enabled: false
      - text: 这次访谈里有几个问题问得不好，帮我把有效的问题沉淀到访谈问题库里。
        web_enabled: false

  - key: merge-retrieval-docs
    note: 多文档合并的审阅会话；目录收敛
    skills: []
    turns:
      - text: 技术/检索 下面这几篇内容有重叠，读一下，然后告诉我该怎么合并才不丢信息。
        web_enabled: false
      - text: 按你说的合并方案来。
        web_enabled: false

  - key: weekly-report
    note: Skill 启用 → 读多篇资料 → 跑完整流程
    skills: ["技能/周报生成"]
    turns:
      - text: 按周报 Skill 出这周的周报。
        web_enabled: false

  - key: partnership-prep
    note: 跨会话记忆生效；未交代背景却引用访谈纪要与周报
    skills: []
    turns:
      - text: 下周要跟一家教培机构谈合作，帮我准备一份材料。
        web_enabled: false
      - text: 对方最关心数据放在哪、会不会外传，这块再展开一点。
        web_enabled: false
```

- [ ] **Step 5: 实现 run.py**

创建 `demo/seed/__init__.py`（空文件）与 `demo/seed/run.py`：

```python
"""按剧本驱动真实 API 跑出演示内容。

跑之前确认目标实例：DEMO_MODE=0、KB 为空、模型链与搜索 provider 已配置。
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import httpx
import yaml


def load_script(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate_script(script: dict) -> list[str]:
    problems: list[str] = []
    conversations = script.get("conversations") or []
    if not conversations:
        problems.append("剧本没有任何会话")
    seen: set[str] = set()
    for index, conv in enumerate(conversations):
        key = conv.get("key")
        if not key:
            problems.append(f"第 {index + 1} 条会话缺少 key")
        elif key in seen:
            problems.append(f"会话 key 重复：{key}")
        else:
            seen.add(key)
        if not (conv.get("turns") or []):
            problems.append(f"会话 {key or index + 1} 没有任何轮次")
        for turn_index, turn in enumerate(conv.get("turns") or []):
            if not (turn.get("text") or "").strip():
                problems.append(f"会话 {key} 第 {turn_index + 1} 轮缺少 text")
    return problems


def _login(client: httpx.Client, password: str) -> None:
    r = client.post("/api/auth/login", json={"password": password})
    r.raise_for_status()


def _import_assets(client: httpx.Client, assets_dir: Path) -> int:
    count = 0
    root = assets_dir / "knowledge"
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        directory = str(rel.parent).replace("\\", "/")
        directory = "" if directory == "." else directory
        r = client.post(
            "/api/kb/import",
            files={"file": (rel.name, path.read_bytes(), "text/markdown")},
            data={"directory": directory},
        )
        r.raise_for_status()
        count += 1
    return count


def _enable_skills(client: httpx.Client, roots: list[str]) -> None:
    if not roots:
        return
    client.put("/api/enabled-skills", json={"roots": roots}).raise_for_status()


def _run_turn(client: httpx.Client, cid: str, turn: dict) -> None:
    with client.stream(
        "POST",
        "/api/chat",
        json={
            "text": turn["text"],
            "conversation_id": cid,
            "web_enabled": bool(turn.get("web_enabled")),
            "doc_context": turn.get("doc_context") or [],
        },
        timeout=600.0,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("event: done"):
                return


def run(base_url: str, password: str, script_path: Path, assets_dir: Path, pause: float) -> None:
    script = load_script(script_path)
    problems = validate_script(script)
    if problems:
        raise SystemExit("剧本校验失败：\n" + "\n".join(problems))

    with httpx.Client(base_url=base_url, timeout=60.0, follow_redirects=True) as client:
        _login(client, password)
        imported = _import_assets(client, assets_dir)
        print(f"已导入前置资产 {imported} 篇")

        for conv in script["conversations"]:
            _enable_skills(client, conv.get("skills") or [])
            cid = client.post("/api/conversations").json()["id"]
            print(f"[{conv['key']}] conversation_id={cid}")
            for index, turn in enumerate(conv["turns"], start=1):
                print(f"  第 {index} 轮…")
                _run_turn(client, cid, turn)
                time.sleep(pause)


def main() -> None:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="按剧本真跑演示内容")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--password", required=True, help="目标实例的管理员密码")
    parser.add_argument("--script", type=Path, default=here / "script.yaml")
    parser.add_argument("--assets", type=Path, default=here.parent / "assets")
    parser.add_argument("--pause", type=float, default=2.0, help="轮次间隔秒数")
    args = parser.parse_args()
    run(args.base_url, args.password, args.script, args.assets, args.pause)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 补依赖**

在 `backend/requirements.txt`（或新建 `demo/requirements.txt`）加：

```
httpx
pyyaml
```

若 `backend/requirements.txt` 已含 `httpx`，只补 `pyyaml`。

- [ ] **Step 7: 运行测试确认通过**

Run: `cd backend && python -m pytest ../demo/tests/test_script.py -v`
Expected: 7 passed

- [ ] **Step 8: 提交**

```bash
git add demo/seed demo/assets demo/tests/test_script.py backend/requirements.txt
git commit -m "feat(demo): 演示内容剧本、前置资产与真跑脚本"
```

---

## Task 6: 真跑与人工定稿

这个 Task 没有可预写的代码——它是一个带明确验收标准的人工迭代循环。产出物是 `demo/knowledge/`、`demo/conversations/*.json`、`demo/memory.json`。

**Files:**
- Create: `demo/knowledge/**`（真跑产出后定稿）
- Create: `demo/conversations/*.json`
- Create: `demo/memory.json`
- Modify: `demo/manifest.json`（填 `reference_date` 与 `highlight_conversation`）

- [ ] **Step 1: 准备真跑实例**

启动一台普通实例：`DEMO_MODE=0`、KB 为空、已配置 chat / embed 模型链与至少一个搜索 provider。确认 `GET /api/health` 正常、`GET /api/tree` 为空。

- [ ] **Step 2: 真跑**

Run: `cd demo && python -m seed.run --base-url http://localhost:8080 --password <管理员密码>`
Expected: 打印 6 个 `conversation_id`，无异常退出。

- [ ] **Step 3: 逐条检查会话质量**

对照 spec §10.3 的表格，逐条确认「展示能力」是否真的发生了：

- [ ] `retrieval-selection`：时间线里有真实 `web_search` 调用与来源列表，最后有 `write_doc`
- [ ] `chunking-experiment`：有 `edit_doc` 的局部改动（不是整篇重写），另有一篇新建的实验记录
- [ ] `interview-notes`：`write_doc` 的目标路径落在 `产品/用户访谈/`，且用户消息里从未指定过该路径
- [ ] `merge-retrieval-docs`：产生了合并审阅会话，目录确实收敛
- [ ] `weekly-report`：周报正文每条进展都能对上一个已存在的文档路径
- [ ] `partnership-prep`：回答中体现了产品方向、目标用户与数据不外传的约束，且引用了访谈纪要与周报

任何一条不达标，调整该会话在 `script.yaml` 里的措辞后重跑该条（删掉对应会话再跑）。**不要**靠事后手改会话来伪造能力展示——手改用于润色，不用于制造没发生过的工具调用。

- [ ] **Step 4: 检查目录树形态**

Run: `curl -s http://localhost:8080/api/tree`（带管理员 cookie）
Expected: 结构接近 spec §10.2；文档总数在 20-30 篇之间；分布不均匀（技术最厚，灵感最薄）。缺的部分直接补写 Markdown 文件，不必强行靠对话跑出来。

- [ ] **Step 5: 校准记忆事实**

打开记忆面板，逐条对照 spec §10.4 的两张表：

- [ ] 应有的六条稳定画像都在（身份、长期方向、结论先行、结构化中文 Markdown、工作日晚上约 1 小时、数据必须本地保存）
- [ ] 没有与主人无关的常识（例如把「RAG 是检索增强生成」记成画像）
- [ ] 没有阶段性任务（例如「本周要写周报」）
- [ ] 没有剥掉语境的通项（例如把「学某课期间时间紧」写成「我每周都没空」）

不达标的条目在面板里直接编辑或遗忘。这一步的产出是演示站对外的记忆质量样板，标准不能松。

- [ ] **Step 6: 润色文档**

直接编辑实例 KB 目录下的 `.md`：修事实错误、统一口吻、删掉模型的套话、确认所有访谈对象都是化名、确认没有任何真实密钥或可识别信息。

- [ ] **Step 7: 导出定稿**

Run: `cd demo && python -m tools.dump --kb <实例 KB 路径> --out .`
Expected: 生成 `demo/conversations/*.json`（6 个文件）与 `demo/memory.json`

把实例 KB 里的 Markdown 与附件拷进 `demo/knowledge/`（**不要**拷 `.kb/`）：

```bash
rsync -a --exclude='.kb' --exclude='.git' <实例 KB 路径>/ demo/knowledge/
```

- [ ] **Step 8: 更新 manifest**

把 `demo/manifest.json` 的 `reference_date` 改成定稿当天的日期，`highlight_conversation` 填 `retrieval-selection` 对应的 conversation id，`content_version` 升到 `1.0.0`。

- [ ] **Step 9: 验证构建可复现**

Run: `cd backend && python ../demo/build.py --kb /tmp/demo-kb`
Expected: 打印文档数与会话数，与定稿一致；`/tmp/demo-kb` 下有 Markdown 与 `.kb/conversations/conversations.db`

- [ ] **Step 10: 提交**

```bash
git add demo/knowledge demo/conversations demo/memory.json demo/manifest.json
git commit -m "content(demo): 演示知识库与六条会话定稿"
```

---

## Task 7: CI 拦截密钥与二进制入库

**Files:**
- Create: `scripts/check_demo_content.py`
- Modify: `.github/workflows/ci.yml`
- Test: `demo/tests/test_check_demo_content.py`

**Interfaces:**
- Produces: `find_forbidden(root: Path) -> list[Path]`

**为什么必须有：** `demo/` 是从一台真实实例拷出来的，`.kb/settings.json` 里是明文 API Key，`.kb/auth.json` 是管理员口令哈希。一次手滑就会把它们推上公开仓库。这条检查是防止那次手滑的唯一屏障。

- [ ] **Step 1: 写失败的测试**

创建 `demo/tests/test_check_demo_content.py`：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_demo_content import find_forbidden


def test_clean_tree_passes(tmp_path):
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "a.md").write_text("# A", encoding="utf-8")
    (tmp_path / "memory.json").write_text("{}", encoding="utf-8")
    assert find_forbidden(tmp_path) == []


def test_settings_json_is_rejected(tmp_path):
    (tmp_path / ".kb").mkdir()
    (tmp_path / ".kb" / "settings.json").write_text("{}", encoding="utf-8")
    assert find_forbidden(tmp_path)


def test_auth_json_is_rejected(tmp_path):
    (tmp_path / ".kb").mkdir()
    (tmp_path / ".kb" / "auth.json").write_text("{}", encoding="utf-8")
    assert find_forbidden(tmp_path)


def test_sqlite_is_rejected(tmp_path):
    (tmp_path / "conversations.db").write_bytes(b"SQLite")
    assert find_forbidden(tmp_path)


def test_wal_and_shm_are_rejected(tmp_path):
    (tmp_path / "x.db-wal").write_bytes(b"")
    (tmp_path / "y.db-shm").write_bytes(b"")
    assert len(find_forbidden(tmp_path)) == 2


def test_index_dir_is_rejected(tmp_path):
    (tmp_path / ".kb" / "index").mkdir(parents=True)
    (tmp_path / ".kb" / "index" / "fts.db").write_bytes(b"")
    assert find_forbidden(tmp_path)


def test_cooldown_json_is_rejected(tmp_path):
    (tmp_path / "model_cooldown.json").write_text("{}", encoding="utf-8")
    assert find_forbidden(tmp_path)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest ../demo/tests/test_check_demo_content.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'check_demo_content'`

- [ ] **Step 3: 实现**

创建 `scripts/check_demo_content.py`：

```python
#!/usr/bin/env python3
"""拦截演示内容目录里的密钥、口令与构建产物。

demo/ 是从真实实例拷出来的，.kb/settings.json 含明文 API Key、
.kb/auth.json 含管理员口令哈希。这条检查是防止手滑推上公开仓库的屏障。
"""

from __future__ import annotations

import sys
from pathlib import Path

FORBIDDEN_NAMES = {
    "settings.json",
    "auth.json",
    "sessions.json",
}

FORBIDDEN_SUFFIXES = (".db", ".db-wal", ".db-shm")

FORBIDDEN_PATTERNS = ("_cooldown.json",)

FORBIDDEN_DIRS = {"index"}


def find_forbidden(root: Path) -> list[Path]:
    hits: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            if path.name in FORBIDDEN_DIRS and path.parent.name == ".kb":
                hits.append(path)
            continue
        if path.name in FORBIDDEN_NAMES and ".kb" in path.parts:
            hits.append(path)
        elif path.name.endswith(FORBIDDEN_SUFFIXES):
            hits.append(path)
        elif any(path.name.endswith(p) for p in FORBIDDEN_PATTERNS):
            hits.append(path)
    return hits


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "demo")
    if not root.is_dir():
        print(f"跳过：{root} 不存在")
        return 0
    hits = find_forbidden(root)
    if not hits:
        print(f"{root} 检查通过")
        return 0
    print("演示内容目录里出现了不该提交的文件：")
    for path in hits:
        print(f"  {path}")
    print("\nSQLite 是构建产物不是源；密钥与口令绝不进 git。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

在 `.github/workflows/ci.yml` 的测试 job 里加一步（放在 checkout 之后、其余步骤之前）：

```yaml
      - name: 检查演示内容目录
        run: python scripts/check_demo_content.py demo
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest ../demo/tests/test_check_demo_content.py -v`
Expected: 7 passed

- [ ] **Step 5: 对真实目录跑一次**

Run: `python scripts/check_demo_content.py demo`
Expected: `demo 检查通过`。若报出文件，删掉它们并确认不在 git 索引里（`git rm --cached <路径>`）。

- [ ] **Step 6: 提交**

```bash
git add scripts/check_demo_content.py .github/workflows/ci.yml demo/tests/test_check_demo_content.py
git commit -m "ci(demo): 拦截密钥与构建产物进入演示内容目录"
```

---

## Task 8: 容器启动时构建

**Files:**
- Modify: `docker/docker-compose.yml`（或新增 `docker/docker-compose.demo.yml`）
- Create: `docker/demo-entrypoint.sh`
- Test: 手工验收

- [ ] **Step 1: 写 entrypoint**

创建 `docker/demo-entrypoint.sh`：

```bash
#!/bin/sh
set -e

# 部署即重置：每次启动从 demo/ 的纯文本内容重建运行时知识库，
# 运行期漂移（若有）自动消失。
python /app/demo/build.py --kb "${KB_PATH:-/data/knowledge}"

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: 加 compose 叠加层**

创建 `docker/docker-compose.demo.yml`：

```yaml
services:
  backend:
    environment:
      DEMO_MODE: "1"
    entrypoint: ["/bin/sh", "/app/docker/demo-entrypoint.sh"]
```

确认镜像里包含 `demo/` 目录（若 Dockerfile 只拷 `backend/`，需要补一行 `COPY demo /app/demo`）。

- [ ] **Step 3: 手工验收**

启动叠加了 demo compose 的栈，确认：

- 首页无需登录直接进入
- 侧栏能看到完整目录树与六条会话
- 打开高光会话，时间线里的搜索来源与写入动作都在
- 记忆面板有预置画像
- 提问能正常回答，刷新后该对话消失
- 重启容器后，任何运行期变化都被抹掉

- [ ] **Step 4: 提交**

```bash
git add docker/demo-entrypoint.sh docker/docker-compose.demo.yml
git commit -m "feat(demo): 演示站容器启动时重建知识库"
```
