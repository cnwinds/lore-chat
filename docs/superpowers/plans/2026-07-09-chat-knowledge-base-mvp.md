# 对话式知识管家 MVP 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个对话式知识管家的第一期（MVP）：用户用聊天方式录入内容与文件，后端自动组织为 `目录 + md 文件`（git 版本化），提问时混合检索并给出带来源的回答，可返回附件。

**Architecture:** 统一的"知识大脑"后端（FastAPI）+ React Web 聊天前端。后端分层：模型抽象层（OpenAI 兼容，大/小/embedding）→ 存储层（git 版本化的 md + 附件 + changelog）→ 索引层（markitdown 抽取 + 向量 Chroma + 全文 SQLite FTS5）→ 引擎层（组织引擎写入流水线 + 混合检索引擎）→ API 层。所有外部 AI 调用通过依赖注入，测试用 Fake 实现，无需联网。

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, pydantic-settings, openai SDK, chromadb, markitdown, GitPython, SQLite FTS5, pytest, httpx；前端 React + Vite + TypeScript。

---

## 关键契约（跨任务共享的类型与签名，务必保持一致）

这些定义在后续任务中实现，此处集中列出以保证命名一致：

```python
# app/models/llm.py
class LLMClient(Protocol):
    def chat(self, messages: list[dict], *, big: bool = False, temperature: float = 0.2) -> str: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...

# app/storage/repo.py
@dataclass
class Document:
    rel_path: str          # 相对 knowledge/ 的路径，如 "技术/docker/常用命令.md"
    meta: dict             # frontmatter 元信息
    body: str              # 正文（不含 frontmatter）

# app/index/types.py
@dataclass
class Hit:
    doc_id: str            # == rel_path
    chunk: str             # 命中的文本片段
    score: float           # 越大越相关
    source: str            # == rel_path（用于展示来源）

# app/engine/retriever.py
@dataclass
class Answer:
    text: str
    sources: list[str]         # rel_path 列表
    attachments: list[str]     # 需要返回给用户的附件 rel_path 列表

# app/engine/organizer.py
@dataclass
class PlacementDecision:
    action: str            # "new" | "merge" | "append"
    rel_path: str          # 目标 md 的相对路径
    title: str
    category: str          # 顶层/多层目录，如 "技术/docker"
    tags: list[str]
    ambiguous: bool        # True 时需要问用户
    reason: str

@dataclass
class IngestResult:
    status: str            # "saved" | "question"
    rel_path: str | None
    question_id: str | None
    message: str
```

---

## 文件结构

```
backend/
  app/
    __init__.py
    config.py                # Settings（pydantic-settings）
    main.py                  # FastAPI app 装配
    models/
      __init__.py
      llm.py                 # LLMClient 协议 + OpenAILLMClient + FakeLLMClient
    storage/
      __init__.py
      frontmatter.py         # frontmatter 解析/序列化
      repo.py                # KnowledgeRepo：git 版本化文件操作 + changelog
    index/
      __init__.py
      types.py               # Hit
      extract.py             # extract_text（markitdown）
      chunk.py               # chunk_text
      vector.py              # VectorIndex（chroma）
      fulltext.py            # FullTextIndex（sqlite fts5）
      indexer.py             # Indexer：协调两个索引
    engine/
      __init__.py
      pending.py             # PendingStore：待用户确认的问题
      retriever.py           # Retriever：混合检索 + 组织回答
      organizer.py           # Organizer：写入流水线
    api/
      __init__.py
      routes.py              # 所有 HTTP 端点
  tests/
    conftest.py
    test_frontmatter.py
    test_repo.py
    test_chunk.py
    test_vector.py
    test_fulltext.py
    test_indexer.py
    test_pending.py
    test_retriever.py
    test_organizer.py
    test_api.py
  requirements.txt
  pytest.ini
frontend/
  (Vite React TS 脚手架，见 Task 12)
```

---

## Task 0: 后端项目脚手架

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/pytest.ini`
- Create: `backend/app/__init__.py`（空）
- Create: `backend/app/models/__init__.py`（空）
- Create: `backend/app/storage/__init__.py`（空）
- Create: `backend/app/index/__init__.py`（空）
- Create: `backend/app/engine/__init__.py`（空）
- Create: `backend/app/api/__init__.py`（空）
- Create: `backend/tests/__init__.py`（空）

- [ ] **Step 1: 写 requirements.txt**

```
fastapi==0.115.*
uvicorn[standard]==0.32.*
pydantic-settings==2.*
openai==1.*
chromadb==0.5.*
markitdown==0.0.1a3
GitPython==3.1.*
python-multipart==0.0.*
pytest==8.*
httpx==0.27.*
```

- [ ] **Step 2: 写 pytest.ini**

```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 3: 建空的 `__init__.py` 包文件**

为 `app/`, `app/models/`, `app/storage/`, `app/index/`, `app/engine/`, `app/api/`, `tests/` 各创建空 `__init__.py`。

- [ ] **Step 4: 安装依赖并验证 pytest 可运行**

Run: `cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt && .venv\Scripts\pytest -q`
Expected: `no tests ran`（0 收集，退出码 5 或提示无用例，说明环境就绪）

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "chore: 后端项目脚手架与依赖"
```

---

## Task 1: 配置层 Settings

**Files:**
- Create: `backend/app/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config.py
from app.config import Settings

def test_settings_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_PATH", str(tmp_path / "knowledge"))
    monkeypatch.setenv("SMALL_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("BIG_MODEL", "gpt-4o")
    monkeypatch.setenv("EMBED_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example.com/v1")
    s = Settings()
    assert s.small_model == "gpt-4o-mini"
    assert s.big_model == "gpt-4o"
    assert s.embed_model == "text-embedding-3-small"
    assert str(s.kb_path).endswith("knowledge")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\pytest tests/test_config.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: 实现 config.py**

```python
# app/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kb_path: Path = Path("./knowledge")

    # OpenAI 兼容配置：小/大/embedding 可各自覆盖，默认回退到统一配置
    openai_api_key: str = "sk-none"
    openai_base_url: str = "https://api.openai.com/v1"

    small_model: str = "gpt-4o-mini"
    big_model: str = "gpt-4o"
    embed_model: str = "text-embedding-3-small"

    # 可选：为不同档位单独配置 base_url / key（留空则回退到 openai_*）
    small_base_url: str | None = None
    small_api_key: str | None = None
    big_base_url: str | None = None
    big_api_key: str | None = None
    embed_base_url: str | None = None
    embed_api_key: str | None = None


def get_settings() -> "Settings":
    return Settings()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat: 配置层 Settings（OpenAI 兼容大小模型）"
```

---

## Task 2: 模型抽象层 LLMClient

**Files:**
- Create: `backend/app/models/llm.py`
- Test: `backend/tests/test_llm.py`

说明：`OpenAILLMClient` 走 OpenAI SDK；`FakeLLMClient` 供全项目测试注入，避免联网。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_llm.py
from app.models.llm import FakeLLMClient

def test_fake_chat_scripted():
    llm = FakeLLMClient(chat_responses=["hello"], embed_dim=4)
    out = llm.chat([{"role": "user", "content": "hi"}])
    assert out == "hello"

def test_fake_embed_dim_and_determinism():
    llm = FakeLLMClient(embed_dim=8)
    v1 = llm.embed(["abc"])
    v2 = llm.embed(["abc"])
    assert len(v1) == 1 and len(v1[0]) == 8
    assert v1 == v2  # 相同输入产生相同向量

def test_fake_chat_records_big_flag():
    llm = FakeLLMClient(chat_responses=["x", "y"])
    llm.chat([{"role": "user", "content": "a"}], big=True)
    assert llm.calls[-1]["big"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\pytest tests/test_llm.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.models.llm'`

- [ ] **Step 3: 实现 llm.py**

```python
# app/models/llm.py
from __future__ import annotations
import hashlib
from typing import Protocol, runtime_checkable
from openai import OpenAI
from app.config import Settings


@runtime_checkable
class LLMClient(Protocol):
    def chat(self, messages: list[dict], *, big: bool = False, temperature: float = 0.2) -> str: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAILLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._small = OpenAI(
            api_key=settings.small_api_key or settings.openai_api_key,
            base_url=settings.small_base_url or settings.openai_base_url,
        )
        self._big = OpenAI(
            api_key=settings.big_api_key or settings.openai_api_key,
            base_url=settings.big_base_url or settings.openai_base_url,
        )
        self._embed = OpenAI(
            api_key=settings.embed_api_key or settings.openai_api_key,
            base_url=settings.embed_base_url or settings.openai_base_url,
        )

    def chat(self, messages: list[dict], *, big: bool = False, temperature: float = 0.2) -> str:
        client = self._big if big else self._small
        model = self.settings.big_model if big else self.settings.small_model
        resp = client.chat.completions.create(model=model, messages=messages, temperature=temperature)
        return resp.choices[0].message.content or ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._embed.embeddings.create(model=self.settings.embed_model, input=texts)
        return [d.embedding for d in resp.data]


class FakeLLMClient:
    """测试用：脚本化 chat 返回；embed 基于哈希产生确定性向量。"""

    def __init__(self, chat_responses: list[str] | None = None, embed_dim: int = 16):
        self.chat_responses = list(chat_responses or [])
        self.embed_dim = embed_dim
        self.calls: list[dict] = []
        self._i = 0

    def chat(self, messages: list[dict], *, big: bool = False, temperature: float = 0.2) -> str:
        self.calls.append({"messages": messages, "big": big})
        if self._i < len(self.chat_responses):
            out = self.chat_responses[self._i]
            self._i += 1
            return out
        return ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            vec = [((h[i % len(h)] / 255.0) * 2 - 1) for i in range(self.embed_dim)]
            vecs.append(vec)
        return vecs
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/llm.py backend/tests/test_llm.py
git commit -m "feat: 模型抽象层 LLMClient（OpenAI 兼容 + Fake）"
```

---

## Task 3: frontmatter 解析/序列化

**Files:**
- Create: `backend/app/storage/frontmatter.py`
- Test: `backend/tests/test_frontmatter.py`

采用简单的 `---` YAML-lite（仅 str/list[str]），避免额外依赖。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_frontmatter.py
from app.storage.frontmatter import parse, dump

def test_parse_with_frontmatter():
    text = "---\ntitle: 常用命令\ntags: [docker, cli]\n---\n正文第一行\n正文第二行\n"
    meta, body = parse(text)
    assert meta["title"] == "常用命令"
    assert meta["tags"] == ["docker", "cli"]
    assert body == "正文第一行\n正文第二行\n"

def test_parse_without_frontmatter():
    meta, body = parse("只有正文\n")
    assert meta == {}
    assert body == "只有正文\n"

def test_dump_roundtrip():
    meta = {"title": "T", "tags": ["a", "b"], "source": "chat"}
    body = "hello\nworld\n"
    text = dump(meta, body)
    meta2, body2 = parse(text)
    assert meta2["title"] == "T"
    assert meta2["tags"] == ["a", "b"]
    assert body2 == body
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\pytest tests/test_frontmatter.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 frontmatter.py**

```python
# app/storage/frontmatter.py
from __future__ import annotations

_DELIM = "---"


def parse(text: str) -> tuple[dict, str]:
    if not text.startswith(_DELIM + "\n"):
        return {}, text
    end = text.find("\n" + _DELIM + "\n", len(_DELIM) + 1)
    if end == -1:
        return {}, text
    header = text[len(_DELIM) + 1 : end]
    body = text[end + len("\n" + _DELIM + "\n") :]
    meta: dict = {}
    for line in header.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            meta[key] = [x.strip() for x in inner.split(",") if x.strip()] if inner else []
        else:
            meta[key] = val
    return meta, body


def dump(meta: dict, body: str) -> str:
    lines = [_DELIM]
    for key, val in meta.items():
        if isinstance(val, list):
            lines.append(f"{key}: [{', '.join(str(x) for x in val)}]")
        else:
            lines.append(f"{key}: {val}")
    lines.append(_DELIM)
    header = "\n".join(lines)
    if not body.endswith("\n"):
        body += "\n"
    return header + "\n" + body
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_frontmatter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage/frontmatter.py backend/tests/test_frontmatter.py
git commit -m "feat: md frontmatter 解析与序列化"
```

---

## Task 4: 存储层 KnowledgeRepo（git 版本化）

**Files:**
- Create: `backend/app/storage/repo.py`
- Test: `backend/tests/test_repo.py`

职责：管理 `knowledge/` 目录（git 仓库）：读写 md（带 frontmatter）、追加、列目录树、存/取附件、写 changelog，每次改动一次 commit。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_repo.py
import pytest
from app.storage.repo import KnowledgeRepo, Document

@pytest.fixture
def repo(tmp_path):
    return KnowledgeRepo(tmp_path / "knowledge")

def test_write_and_read_doc(repo):
    repo.write_doc("技术/docker/常用命令.md",
                   meta={"title": "常用命令", "tags": ["docker"]},
                   body="docker ps\n",
                   commit_msg="add docker note")
    doc = repo.read_doc("技术/docker/常用命令.md")
    assert isinstance(doc, Document)
    assert doc.meta["title"] == "常用命令"
    assert "docker ps" in doc.body

def test_write_creates_git_commit(repo):
    repo.write_doc("a.md", {"title": "A"}, "body\n", commit_msg="first")
    commits = list(repo.repo.iter_commits())
    assert any("first" in c.message for c in commits)

def test_append_doc(repo):
    repo.write_doc("a.md", {"title": "A"}, "line1\n", commit_msg="c1")
    repo.append_doc("a.md", "line2\n", commit_msg="c2")
    doc = repo.read_doc("a.md")
    assert "line1" in doc.body and "line2" in doc.body

def test_list_tree(repo):
    repo.write_doc("技术/x.md", {"title": "X"}, "b\n", commit_msg="c")
    repo.write_doc("生活/y.md", {"title": "Y"}, "b\n", commit_msg="c")
    tree = repo.list_tree()
    assert "技术/x.md" in tree and "生活/y.md" in tree

def test_save_and_get_attachment(repo):
    p = repo.save_attachment("技术/docker", "plan.pdf", b"%PDF-1.4 fake", commit_msg="add file")
    assert p == "技术/docker/attachments/plan.pdf"
    assert repo.get_attachment(p) == b"%PDF-1.4 fake"

def test_log_change_appends_changelog(repo):
    repo.log_change("创建 技术/x.md：docker 笔记", commit_msg="log")
    doc_text = (repo.root / ".kb" / "changelog.md").read_text(encoding="utf-8")
    assert "docker 笔记" in doc_text

def test_read_missing_doc_raises(repo):
    with pytest.raises(FileNotFoundError):
        repo.read_doc("nope.md")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\pytest tests/test_repo.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 repo.py**

```python
# app/storage/repo.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from git import Repo
from app.storage import frontmatter


@dataclass
class Document:
    rel_path: str
    meta: dict
    body: str


class KnowledgeRepo:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        git_dir = self.root / ".git"
        if git_dir.exists():
            self.repo = Repo(self.root)
        else:
            self.repo = Repo.init(self.root)
        (self.root / ".kb").mkdir(exist_ok=True)

    # ---------- 内部 ----------
    def _abs(self, rel_path: str) -> Path:
        p = (self.root / rel_path).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise ValueError(f"路径越界: {rel_path}")
        return p

    def _commit(self, rel_paths: list[str], msg: str) -> None:
        self.repo.index.add(rel_paths)
        self.repo.index.commit(msg)

    # ---------- md 文档 ----------
    def read_doc(self, rel_path: str) -> Document:
        abs_p = self._abs(rel_path)
        if not abs_p.exists():
            raise FileNotFoundError(rel_path)
        meta, body = frontmatter.parse(abs_p.read_text(encoding="utf-8"))
        return Document(rel_path=rel_path, meta=meta, body=body)

    def write_doc(self, rel_path: str, meta: dict, body: str, *, commit_msg: str) -> None:
        abs_p = self._abs(rel_path)
        abs_p.parent.mkdir(parents=True, exist_ok=True)
        meta = {"updated": datetime.now().isoformat(timespec="seconds"), **meta}
        abs_p.write_text(frontmatter.dump(meta, body), encoding="utf-8")
        self._commit([rel_path], commit_msg)

    def append_doc(self, rel_path: str, extra_body: str, *, commit_msg: str) -> None:
        doc = self.read_doc(rel_path)
        new_body = doc.body
        if not new_body.endswith("\n"):
            new_body += "\n"
        new_body += extra_body
        self.write_doc(rel_path, doc.meta, new_body, commit_msg=commit_msg)

    def list_tree(self) -> list[str]:
        out: list[str] = []
        for p in sorted(self.root.rglob("*.md")):
            rel = p.relative_to(self.root).as_posix()
            if rel.startswith(".kb/"):
                continue
            out.append(rel)
        return out

    # ---------- 附件 ----------
    def save_attachment(self, rel_dir: str, filename: str, data: bytes, *, commit_msg: str) -> str:
        rel_path = f"{rel_dir.rstrip('/')}/attachments/{filename}"
        abs_p = self._abs(rel_path)
        abs_p.parent.mkdir(parents=True, exist_ok=True)
        abs_p.write_bytes(data)
        self._commit([rel_path], commit_msg)
        return rel_path

    def get_attachment(self, rel_path: str) -> bytes:
        abs_p = self._abs(rel_path)
        if not abs_p.exists():
            raise FileNotFoundError(rel_path)
        return abs_p.read_bytes()

    # ---------- changelog ----------
    def log_change(self, entry: str, *, commit_msg: str = "chore: update changelog") -> None:
        path = self.root / ".kb" / "changelog.md"
        stamp = datetime.now().isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"- {stamp} {entry}\n")
        self._commit([".kb/changelog.md"], commit_msg)
```

注意：GitPython 的 `index.add` 需要相对仓库根的路径；本实现传入的 `rel_path` 已是相对根路径，`_commit` 直接使用。若首个 commit 前需要用户身份，测试环境应已通过 `git config` 设置，或在 `__init__` 中检测并设置本地默认（见 Step 3b）。

- [ ] **Step 3b: 若测试因缺少 git user 报错，补充仓库本地身份**

在 `KnowledgeRepo.__init__` 的 `Repo.init` 后追加：

```python
        with self.repo.config_writer() as cw:
            if not cw.has_option("user", "email"):
                cw.set_value("user", "email", "kb@localhost")
            if not cw.has_option("user", "name"):
                cw.set_value("user", "name", "knowledge-brain")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_repo.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage/repo.py backend/tests/test_repo.py
git commit -m "feat: 存储层 KnowledgeRepo（git 版本化 md + 附件 + changelog）"
```

---

## Task 5: 索引类型与文本抽取/分块

**Files:**
- Create: `backend/app/index/types.py`
- Create: `backend/app/index/extract.py`
- Create: `backend/app/index/chunk.py`
- Test: `backend/tests/test_chunk.py`
- Test: `backend/tests/test_extract.py`

- [ ] **Step 1: 写失败测试（chunk + extract）**

```python
# tests/test_chunk.py
from app.index.chunk import chunk_text

def test_chunk_short_text_single_chunk():
    chunks = chunk_text("hello world", size=100, overlap=10)
    assert chunks == ["hello world"]

def test_chunk_long_text_overlaps():
    text = "a" * 250
    chunks = chunk_text(text, size=100, overlap=20)
    assert len(chunks) == 3
    assert all(len(c) <= 100 for c in chunks)
    # 相邻块有重叠
    assert chunks[0][-20:] == chunks[1][:20]

def test_chunk_empty_returns_empty():
    assert chunk_text("   ", size=100, overlap=10) == []
```

```python
# tests/test_extract.py
from app.index.extract import extract_text

def test_extract_plain_md(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# 标题\n正文\n", encoding="utf-8")
    out = extract_text(p)
    assert "正文" in out

def test_extract_txt(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("纯文本内容", encoding="utf-8")
    assert "纯文本内容" in extract_text(p)

def test_extract_binary_returns_empty(tmp_path):
    p = tmp_path / "a.zip"
    p.write_bytes(b"PK\x03\x04binary")
    assert extract_text(p) == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\pytest tests/test_chunk.py tests/test_extract.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 types.py / chunk.py / extract.py**

```python
# app/index/types.py
from dataclasses import dataclass

@dataclass
class Hit:
    doc_id: str
    chunk: str
    score: float
    source: str
```

```python
# app/index/chunk.py
def chunk_text(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    step = max(1, size - overlap)
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + size])
        if i + size >= len(text):
            break
        i += step
    return chunks
```

```python
# app/index/extract.py
from pathlib import Path

_PLAIN = {".md", ".txt", ".markdown"}
_READABLE = {".pdf", ".docx", ".pptx", ".xlsx", ".doc", ".ppt", ".xls", ".html", ".htm", ".csv"}


def extract_text(path: str | Path) -> str:
    path = Path(path)
    ext = path.suffix.lower()
    if ext in _PLAIN:
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext in _READABLE:
        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(str(path))
            return result.text_content or ""
        except Exception:
            return ""
    # 二进制（zip/rar 等）不抽取内容
    return ""
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_chunk.py tests/test_extract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/index/types.py backend/app/index/chunk.py backend/app/index/extract.py backend/tests/test_chunk.py backend/tests/test_extract.py
git commit -m "feat: 索引类型、文本抽取（markitdown）与分块"
```

---

## Task 6: 向量索引 VectorIndex（Chroma）

**Files:**
- Create: `backend/app/index/vector.py`
- Test: `backend/tests/test_vector.py`

传入预计算好的 embedding（由 LLMClient.embed 产生），避免在 Chroma 内做 embedding。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_vector.py
from app.index.vector import VectorIndex

def _vec(seed, dim=8):
    return [float((seed + i) % 5) for i in range(dim)]

def test_add_and_query(tmp_path):
    vi = VectorIndex(tmp_path / "vec")
    vi.add("doc1.md", ["docker 命令", "启动容器"], [_vec(1), _vec(2)], source="doc1.md")
    vi.add("doc2.md", ["做饭菜谱"], [_vec(9)], source="doc2.md")
    hits = vi.query(_vec(1), k=1)
    assert len(hits) == 1
    assert hits[0].doc_id == "doc1.md"

def test_delete_removes_doc(tmp_path):
    vi = VectorIndex(tmp_path / "vec")
    vi.add("doc1.md", ["x"], [_vec(1)], source="doc1.md")
    vi.delete("doc1.md")
    hits = vi.query(_vec(1), k=5)
    assert all(h.doc_id != "doc1.md" for h in hits)

def test_reindex_same_doc_replaces(tmp_path):
    vi = VectorIndex(tmp_path / "vec")
    vi.add("doc1.md", ["旧内容"], [_vec(1)], source="doc1.md")
    vi.delete("doc1.md")
    vi.add("doc1.md", ["新内容"], [_vec(2)], source="doc1.md")
    hits = vi.query(_vec(2), k=5)
    texts = [h.chunk for h in hits if h.doc_id == "doc1.md"]
    assert "新内容" in texts and "旧内容" not in texts
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\pytest tests/test_vector.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 vector.py**

```python
# app/index/vector.py
from __future__ import annotations
from pathlib import Path
import chromadb
from app.index.types import Hit


class VectorIndex:
    def __init__(self, path: str | Path):
        Path(path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        self._col = self._client.get_or_create_collection(
            name="kb", metadata={"hnsw:space": "cosine"}
        )

    def add(self, doc_id: str, chunks: list[str], embeddings: list[list[float]], *, source: str) -> None:
        if not chunks:
            return
        ids = [f"{doc_id}::{i}" for i in range(len(chunks))]
        metadatas = [{"doc_id": doc_id, "source": source} for _ in chunks]
        self._col.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)

    def delete(self, doc_id: str) -> None:
        self._col.delete(where={"doc_id": doc_id})

    def query(self, embedding: list[float], k: int = 5) -> list[Hit]:
        res = self._col.query(query_embeddings=[embedding], n_results=k)
        hits: list[Hit] = []
        docs = res.get("documents") or [[]]
        metas = res.get("metadatas") or [[]]
        dists = res.get("distances") or [[]]
        for doc, meta, dist in zip(docs[0], metas[0], dists[0]):
            hits.append(Hit(doc_id=meta["doc_id"], chunk=doc, score=1.0 - float(dist), source=meta["source"]))
        return hits
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_vector.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/index/vector.py backend/tests/test_vector.py
git commit -m "feat: 向量索引 VectorIndex（Chroma 持久化）"
```

---

## Task 7: 全文索引 FullTextIndex（SQLite FTS5）

**Files:**
- Create: `backend/app/index/fulltext.py`
- Test: `backend/tests/test_fulltext.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_fulltext.py
from app.index.fulltext import FullTextIndex

def test_add_and_query(tmp_path):
    fi = FullTextIndex(tmp_path / "fts.db")
    fi.add("doc1.md", ["docker 常用命令 容器"], source="doc1.md")
    fi.add("doc2.md", ["番茄炒蛋 菜谱"], source="doc2.md")
    hits = fi.query("docker", k=5)
    assert any(h.doc_id == "doc1.md" for h in hits)
    assert all(h.doc_id != "doc2.md" for h in hits)

def test_delete(tmp_path):
    fi = FullTextIndex(tmp_path / "fts.db")
    fi.add("doc1.md", ["docker"], source="doc1.md")
    fi.delete("doc1.md")
    assert fi.query("docker", k=5) == []

def test_reindex_replaces(tmp_path):
    fi = FullTextIndex(tmp_path / "fts.db")
    fi.add("doc1.md", ["旧词"], source="doc1.md")
    fi.delete("doc1.md")
    fi.add("doc1.md", ["新词"], source="doc1.md")
    assert fi.query("旧词", k=5) == []
    assert any(h.doc_id == "doc1.md" for h in fi.query("新词", k=5))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\pytest tests/test_fulltext.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 fulltext.py**

中文场景用 FTS5 的 `trigram` 分词器（SQLite 3.34+ 内置），无需外部分词。

```python
# app/index/fulltext.py
from __future__ import annotations
import sqlite3
from pathlib import Path
from app.index.types import Hit


class FullTextIndex:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks "
            "USING fts5(doc_id, source, body, tokenize='trigram')"
        )
        self.conn.commit()

    def add(self, doc_id: str, chunks: list[str], *, source: str) -> None:
        for c in chunks:
            self.conn.execute(
                "INSERT INTO chunks(doc_id, source, body) VALUES (?, ?, ?)",
                (doc_id, source, c),
            )
        self.conn.commit()

    def delete(self, doc_id: str) -> None:
        self.conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        self.conn.commit()

    def query(self, text: str, k: int = 5) -> list[Hit]:
        text = text.strip()
        if not text:
            return []
        rows = self.conn.execute(
            "SELECT doc_id, source, body, bm25(chunks) AS rank "
            "FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
            (text, k),
        ).fetchall()
        hits: list[Hit] = []
        for doc_id, source, body, rank in rows:
            hits.append(Hit(doc_id=doc_id, chunk=body, score=-float(rank), source=source))
        return hits
```

注意：FTS5 的 `MATCH` 对特殊字符敏感，`trigram` 分词器要求查询串至少 3 字符；`query` 中对过短查询由调用方（检索引擎）补充关键词，此处直接透传。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_fulltext.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/index/fulltext.py backend/tests/test_fulltext.py
git commit -m "feat: 全文索引 FullTextIndex（SQLite FTS5 trigram）"
```

---

## Task 8: 索引协调器 Indexer

**Files:**
- Create: `backend/app/index/indexer.py`
- Test: `backend/tests/test_indexer.py`

职责：对一篇文档做统一的 (重)索引/移除，协调向量与全文；embedding 用注入的 LLMClient。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_indexer.py
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.models.llm import FakeLLMClient

def _make(tmp_path):
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(embed_dim=8)
    return Indexer(vi, fi, llm), vi, fi

def test_reindex_adds_to_both(tmp_path):
    idx, vi, fi = _make(tmp_path)
    idx.reindex_doc("doc1.md", "docker 容器常用命令，如何启动和停止")
    assert any(h.doc_id == "doc1.md" for h in fi.query("docker", k=5))
    q = FakeLLMClient(embed_dim=8).embed(["docker"])[0]
    assert any(h.doc_id == "doc1.md" for h in vi.query(q, k=5))

def test_reindex_twice_replaces(tmp_path):
    idx, vi, fi = _make(tmp_path)
    idx.reindex_doc("doc1.md", "旧内容关于苹果")
    idx.reindex_doc("doc1.md", "新内容关于香蕉")
    assert fi.query("苹果", k=5) == []
    assert any(h.doc_id == "doc1.md" for h in fi.query("香蕉", k=5))

def test_remove_doc(tmp_path):
    idx, vi, fi = _make(tmp_path)
    idx.reindex_doc("doc1.md", "docker 内容")
    idx.remove_doc("doc1.md")
    assert fi.query("docker", k=5) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\pytest tests/test_indexer.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 indexer.py**

```python
# app/index/indexer.py
from __future__ import annotations
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.chunk import chunk_text
from app.models.llm import LLMClient


class Indexer:
    def __init__(self, vector: VectorIndex, fulltext: FullTextIndex, llm: LLMClient):
        self.vector = vector
        self.fulltext = fulltext
        self.llm = llm

    def reindex_doc(self, doc_id: str, text: str) -> None:
        self.remove_doc(doc_id)
        chunks = chunk_text(text)
        if not chunks:
            return
        embeddings = self.llm.embed(chunks)
        self.vector.add(doc_id, chunks, embeddings, source=doc_id)
        self.fulltext.add(doc_id, chunks, source=doc_id)

    def remove_doc(self, doc_id: str) -> None:
        self.vector.delete(doc_id)
        self.fulltext.delete(doc_id)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_indexer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/index/indexer.py backend/tests/test_indexer.py
git commit -m "feat: 索引协调器 Indexer（向量+全文统一重建）"
```

---

## Task 9: 待确认问题存储 PendingStore

**Files:**
- Create: `backend/app/engine/pending.py`
- Test: `backend/tests/test_pending.py`

职责：当组织引擎判断"重叠但拿不准"时，创建一个待用户确认的问题（含候选选项与暂存内容），持久化到 `.kb/pending.json`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_pending.py
from app.engine.pending import PendingStore

def test_create_and_get(tmp_path):
    ps = PendingStore(tmp_path / "pending.json")
    qid = ps.create(
        question="这条内容和已有《docker 命令》重叠，如何处理？",
        options=[{"id": "merge", "label": "合并进 docker 命令"},
                 {"id": "new", "label": "新建文档"}],
        payload={"content": "docker logs 用法", "candidate": "技术/docker/常用命令.md"},
    )
    q = ps.get(qid)
    assert q["status"] == "open"
    assert q["payload"]["content"] == "docker logs 用法"

def test_list_open(tmp_path):
    ps = PendingStore(tmp_path / "pending.json")
    ps.create("q1", [{"id": "a", "label": "A"}], {})
    qid2 = ps.create("q2", [{"id": "a", "label": "A"}], {})
    ps.resolve(qid2, "a")
    open_qs = ps.list_open()
    assert len(open_qs) == 1 and open_qs[0]["question"] == "q1"

def test_resolve_sets_choice(tmp_path):
    ps = PendingStore(tmp_path / "pending.json")
    qid = ps.create("q", [{"id": "merge", "label": "M"}], {"x": 1})
    q = ps.resolve(qid, "merge")
    assert q["status"] == "resolved" and q["choice"] == "merge"

def test_persistence_across_instances(tmp_path):
    path = tmp_path / "pending.json"
    ps = PendingStore(path)
    qid = ps.create("q", [{"id": "a", "label": "A"}], {})
    ps2 = PendingStore(path)
    assert ps2.get(qid)["question"] == "q"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\pytest tests/test_pending.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 pending.py**

```python
# app/engine/pending.py
from __future__ import annotations
import json
import uuid
from pathlib import Path


class PendingStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({})

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def create(self, question: str, options: list[dict], payload: dict) -> str:
        data = self._read()
        qid = uuid.uuid4().hex[:12]
        data[qid] = {
            "id": qid,
            "question": question,
            "options": options,
            "payload": payload,
            "status": "open",
            "choice": None,
        }
        self._write(data)
        return qid

    def get(self, qid: str) -> dict:
        return self._read()[qid]

    def list_open(self) -> list[dict]:
        return [q for q in self._read().values() if q["status"] == "open"]

    def resolve(self, qid: str, choice: str) -> dict:
        data = self._read()
        data[qid]["status"] = "resolved"
        data[qid]["choice"] = choice
        self._write(data)
        return data[qid]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_pending.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/pending.py backend/tests/test_pending.py
git commit -m "feat: 待确认问题存储 PendingStore"
```

---

## Task 10: 检索引擎 Retriever（混合检索 + 组织回答）

**Files:**
- Create: `backend/app/engine/retriever.py`
- Test: `backend/tests/test_retriever.py`

职责：混合召回（向量 + 全文，按 doc 去重合并），再用大模型基于片段生成带来源的回答。附件命中的判定：若命中的 doc_id 指向 `attachments/` 下的可读文件，则把该文件加入 `attachments`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_retriever.py
from app.engine.retriever import Retriever
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.models.llm import FakeLLMClient

def _setup(tmp_path, chat_responses):
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(chat_responses=chat_responses, embed_dim=8)
    idx = Indexer(vi, fi, llm)
    idx.reindex_doc("技术/docker/常用命令.md", "docker ps 查看容器，docker logs 看日志")
    idx.reindex_doc("生活/菜谱.md", "番茄炒蛋做法")
    retr = Retriever(vi, fi, llm)
    return retr

def test_search_hybrid_finds_relevant(tmp_path):
    retr = _setup(tmp_path, [])
    hits = retr.search("docker 日志", k=5)
    assert any(h.doc_id == "技术/docker/常用命令.md" for h in hits)

def test_search_dedups_by_doc(tmp_path):
    retr = _setup(tmp_path, [])
    hits = retr.search("docker", k=10)
    ids = [h.doc_id for h in hits]
    assert len(ids) == len(set(ids))  # 每个 doc 只出现一次

def test_answer_returns_sources(tmp_path):
    retr = _setup(tmp_path, ["docker logs 用于查看容器日志。"])
    ans = retr.answer("怎么看 docker 日志")
    assert "docker" in ans.text.lower()
    assert "技术/docker/常用命令.md" in ans.sources

def test_answer_attaches_readable_file(tmp_path):
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(chat_responses=["见附件方案。"], embed_dim=8)
    idx = Indexer(vi, fi, llm)
    idx.reindex_doc("技术/docker/attachments/部署方案.pdf", "kubernetes 部署方案详细步骤")
    retr = Retriever(vi, fi, llm)
    ans = retr.answer("部署方案")
    assert "技术/docker/attachments/部署方案.pdf" in ans.attachments
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\pytest tests/test_retriever.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 retriever.py**

```python
# app/engine/retriever.py
from __future__ import annotations
from dataclasses import dataclass
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.types import Hit
from app.models.llm import LLMClient

_ATTACH_MARKER = "/attachments/"


@dataclass
class Answer:
    text: str
    sources: list[str]
    attachments: list[str]


class Retriever:
    def __init__(self, vector: VectorIndex, fulltext: FullTextIndex, llm: LLMClient):
        self.vector = vector
        self.fulltext = fulltext
        self.llm = llm

    def search(self, query: str, k: int = 5) -> list[Hit]:
        q_emb = self.llm.embed([query])[0]
        vec_hits = self.vector.query(q_emb, k=k)
        ft_hits = self.fulltext.query(query, k=k)
        # 按 doc_id 去重，保留每个 doc 的最高分片段
        best: dict[str, Hit] = {}
        for h in vec_hits + ft_hits:
            cur = best.get(h.doc_id)
            if cur is None or h.score > cur.score:
                best[h.doc_id] = h
        merged = sorted(best.values(), key=lambda h: h.score, reverse=True)
        return merged[:k]

    def answer(self, query: str, k: int = 5) -> Answer:
        hits = self.search(query, k=k)
        if not hits:
            return Answer(text="我没有找到相关内容。", sources=[], attachments=[])
        context = "\n\n".join(f"[来源: {h.source}]\n{h.chunk}" for h in hits)
        messages = [
            {"role": "system", "content": (
                "你是知识库助手。只依据提供的资料回答；资料中没有就明确说没有，不要编造。"
                "回答简洁，并在末尾不必重复来源（系统会单独展示）。"
            )},
            {"role": "user", "content": f"资料：\n{context}\n\n问题：{query}"},
        ]
        text = self.llm.chat(messages, big=True)
        sources = list(dict.fromkeys(h.source for h in hits))
        attachments = [s for s in sources if _ATTACH_MARKER in s]
        return Answer(text=text, sources=sources, attachments=attachments)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_retriever.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/retriever.py backend/tests/test_retriever.py
git commit -m "feat: 检索引擎 Retriever（混合检索 + 带来源回答）"
```

---

## Task 11: 组织引擎 Organizer（写入流水线）

**Files:**
- Create: `backend/app/engine/organizer.py`
- Test: `backend/tests/test_organizer.py`

职责：实现写入流水线——理解（小模型）→ 找关联（Retriever.search）→ 决策放置（小模型，输出 JSON）→ 若 ambiguous 则创建 PendingStore 问题；否则写/合并/追加 → git commit → changelog → 重建索引。还实现 `resolve_pending`（用户答复后落地）。

小模型的"决策"输出约定为 JSON：

```json
{"action":"new|merge|append","rel_path":"技术/docker/常用命令.md","title":"...","category":"技术/docker","tags":["docker"],"ambiguous":false,"reason":"..."}
```

- [ ] **Step 1: 写失败测试**

```python
# tests/test_organizer.py
import json
from app.engine.organizer import Organizer
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.storage.repo import KnowledgeRepo
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.models.llm import FakeLLMClient


def _make(tmp_path, chat_responses):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(chat_responses=chat_responses, embed_dim=8)
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm)
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
    org = Organizer(repo=repo, retriever=retr, indexer=idx, pending=pending, llm=llm)
    return org, repo, pending


def test_ingest_new_doc(tmp_path):
    decision = json.dumps({"action": "new", "rel_path": "技术/docker/常用命令.md",
                           "title": "常用命令", "category": "技术/docker",
                           "tags": ["docker"], "ambiguous": False, "reason": "全新主题"})
    # chat 调用顺序：1)理解摘要 2)决策JSON
    org, repo, pending = _make(tmp_path, ["docker 命令摘要", decision])
    result = org.ingest_text("docker ps 用来查看容器")
    assert result.status == "saved"
    assert result.rel_path == "技术/docker/常用命令.md"
    doc = repo.read_doc("技术/docker/常用命令.md")
    assert "docker ps" in doc.body

def test_ingest_ambiguous_creates_question(tmp_path):
    decision = json.dumps({"action": "merge", "rel_path": "技术/docker/常用命令.md",
                           "title": "常用命令", "category": "技术/docker",
                           "tags": ["docker"], "ambiguous": True, "reason": "可能与已有重叠"})
    org, repo, pending = _make(tmp_path, ["摘要", decision])
    result = org.ingest_text("docker logs 看日志")
    assert result.status == "question"
    assert result.question_id is not None
    assert len(pending.list_open()) == 1

def test_ingest_records_changelog(tmp_path):
    decision = json.dumps({"action": "new", "rel_path": "a.md", "title": "A",
                           "category": "", "tags": [], "ambiguous": False, "reason": "r"})
    org, repo, pending = _make(tmp_path, ["摘要", decision])
    org.ingest_text("内容")
    changelog = (repo.root / ".kb" / "changelog.md").read_text(encoding="utf-8")
    assert "a.md" in changelog

def test_resolve_pending_merge(tmp_path):
    decision = json.dumps({"action": "merge", "rel_path": "技术/docker/常用命令.md",
                           "title": "常用命令", "category": "技术/docker",
                           "tags": ["docker"], "ambiguous": True, "reason": "重叠"})
    org, repo, pending = _make(tmp_path, ["摘要", decision])
    # 先建一个已有文档以便 merge 追加
    repo.write_doc("技术/docker/常用命令.md", {"title": "常用命令"}, "docker ps\n", commit_msg="seed")
    result = org.ingest_text("docker logs 看日志")
    qid = result.question_id
    org.resolve_pending(qid, "merge")
    doc = repo.read_doc("技术/docker/常用命令.md")
    assert "docker logs" in doc.body
    assert pending.get(qid)["status"] == "resolved"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\pytest tests/test_organizer.py -v`
Expected: FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 实现 organizer.py**

```python
# app/engine/organizer.py
from __future__ import annotations
import json
from dataclasses import dataclass
from app.storage.repo import KnowledgeRepo
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.index.indexer import Indexer
from app.models.llm import LLMClient


@dataclass
class PlacementDecision:
    action: str
    rel_path: str
    title: str
    category: str
    tags: list[str]
    ambiguous: bool
    reason: str


@dataclass
class IngestResult:
    status: str
    rel_path: str | None
    question_id: str | None
    message: str


class Organizer:
    def __init__(self, repo: KnowledgeRepo, retriever: Retriever,
                 indexer: Indexer, pending: PendingStore, llm: LLMClient):
        self.repo = repo
        self.retriever = retriever
        self.indexer = indexer
        self.pending = pending
        self.llm = llm

    # ---------- 主流程 ----------
    def ingest_text(self, content: str) -> IngestResult:
        summary = self._understand(content)
        related = self.retriever.search(summary or content, k=5)
        decision = self._decide(content, summary, related)

        if decision.ambiguous:
            qid = self.pending.create(
                question=f"这条内容可能与《{decision.rel_path}》重叠：{decision.reason}。如何处理？",
                options=[
                    {"id": "merge", "label": f"合并进 {decision.rel_path}"},
                    {"id": "new", "label": "新建独立文档"},
                ],
                payload={"content": content, "decision": decision.__dict__},
            )
            return IngestResult(status="question", rel_path=None, question_id=qid,
                                message="需要你确认如何归置这条内容。")

        self._apply(decision, content)
        return IngestResult(status="saved", rel_path=decision.rel_path,
                            question_id=None, message=f"已保存到 {decision.rel_path}")

    def resolve_pending(self, qid: str, choice: str) -> IngestResult:
        q = self.pending.get(qid)
        content = q["payload"]["content"]
        d = q["payload"]["decision"]
        decision = PlacementDecision(**{**d, "action": "merge" if choice == "merge" else "new",
                                        "ambiguous": False})
        self._apply(decision, content)
        self.pending.resolve(qid, choice)
        return IngestResult(status="saved", rel_path=decision.rel_path,
                            question_id=None, message=f"已按你的选择保存到 {decision.rel_path}")

    # ---------- 内部步骤 ----------
    def _understand(self, content: str) -> str:
        messages = [
            {"role": "system", "content": "用一句话概括这条内容的主题，便于检索。"},
            {"role": "user", "content": content},
        ]
        return self.llm.chat(messages)

    def _decide(self, content: str, summary: str, related) -> PlacementDecision:
        related_desc = "\n".join(f"- {h.source}: {h.chunk[:80]}" for h in related) or "（无相关文档）"
        messages = [
            {"role": "system", "content": (
                "你是知识库组织员。根据新内容和已有相关文档，决定如何归置。"
                "只输出 JSON，字段：action(new|merge|append), rel_path(目标md相对路径,以.md结尾), "
                "title, category(目录,如 技术/docker,可空), tags(数组), ambiguous(bool,重叠但拿不准时true), reason。"
                "若与某已有文档明显是同一主题应 merge/append；全新主题用 new；拿不准是否重叠时 ambiguous=true。"
            )},
            {"role": "user", "content": f"新内容：{content}\n摘要：{summary}\n相关文档：\n{related_desc}"},
        ]
        raw = self.llm.chat(messages)
        data = self._parse_json(raw)
        return PlacementDecision(
            action=data.get("action", "new"),
            rel_path=data.get("rel_path") or "未分类/note.md",
            title=data.get("title", "未命名"),
            category=data.get("category", ""),
            tags=data.get("tags", []),
            ambiguous=bool(data.get("ambiguous", False)),
            reason=data.get("reason", ""),
        )

    @staticmethod
    def _parse_json(raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.startswith("json"):
                raw = raw[4:]
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start : end + 1]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _apply(self, decision: PlacementDecision, content: str) -> None:
        rel_path = decision.rel_path
        exists = False
        try:
            self.repo.read_doc(rel_path)
            exists = True
        except FileNotFoundError:
            exists = False

        if decision.action in ("merge", "append") and exists:
            self.repo.append_doc(rel_path, f"\n{content}\n",
                                 commit_msg=f"merge: 追加内容到 {rel_path}")
            verb = "追加到"
        else:
            self.repo.write_doc(rel_path,
                                meta={"title": decision.title, "tags": decision.tags, "source": "chat"},
                                body=f"{content}\n",
                                commit_msg=f"add: 新建 {rel_path}")
            verb = "创建"

        # 重建该文档索引（正文）
        doc = self.repo.read_doc(rel_path)
        self.indexer.reindex_doc(rel_path, doc.body)
        self.repo.log_change(f"{verb} {rel_path}：{decision.reason or decision.title}",
                             commit_msg=f"chore: changelog for {rel_path}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_organizer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/organizer.py backend/tests/test_organizer.py
git commit -m "feat: 组织引擎 Organizer（写入流水线 + C/D 介入）"
```

---

## Task 12: 依赖装配与 FastAPI 应用

**Files:**
- Create: `backend/app/deps.py`
- Create: `backend/app/main.py`
- Create: `backend/app/api/routes.py`
- Test: `backend/tests/conftest.py`
- Test: `backend/tests/test_api.py`

职责：把各组件装配起来，暴露 HTTP 端点。测试用 `FakeLLMClient` 覆盖依赖，走 FastAPI `TestClient`，全程不联网。

端点：
- `POST /api/ingest` body `{text}` → IngestResult
- `POST /api/ask` body `{query}` → Answer
- `POST /api/upload` multipart `file` (+ 可选 `category`) → 存附件 + 索引 + 摘要入 md
- `GET /api/download?path=` → 返回原始文件
- `GET /api/tree` → md 列表
- `GET /api/doc?path=` → 单篇 md 内容
- `GET /api/questions` → 待确认问题
- `POST /api/questions/{qid}/resolve` body `{choice}` → IngestResult

- [ ] **Step 1: 写 conftest + 失败测试**

```python
# tests/conftest.py
import json
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app import deps
from app.models.llm import FakeLLMClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    # 用 tmp 目录 + FakeLLM 覆盖依赖
    from app.config import Settings
    settings = Settings(kb_path=tmp_path / "knowledge")
    fake_decision = json.dumps({"action": "new", "rel_path": "技术/note.md",
                                "title": "笔记", "category": "技术", "tags": ["t"],
                                "ambiguous": False, "reason": "全新"})
    llm = FakeLLMClient(chat_responses=["摘要", fake_decision] * 20, embed_dim=8)
    app = create_app(settings=settings, llm=llm)
    return TestClient(app)
```

```python
# tests/test_api.py
def test_ingest_then_ask(client):
    r = client.post("/api/ingest", json={"text": "docker ps 查看容器"})
    assert r.status_code == 200
    assert r.json()["status"] == "saved"

    r2 = client.post("/api/ask", json={"query": "docker"})
    assert r2.status_code == 200
    body = r2.json()
    assert "sources" in body and "text" in body

def test_tree_lists_docs(client):
    client.post("/api/ingest", json={"text": "内容一"})
    r = client.get("/api/tree")
    assert r.status_code == 200
    assert any(p.endswith(".md") for p in r.json()["docs"])

def test_upload_and_download(client):
    files = {"file": ("plan.txt", b"kubernetes 部署方案", "text/plain")}
    r = client.post("/api/upload", files=files, data={"category": "技术/docker"})
    assert r.status_code == 200
    path = r.json()["attachment"]
    assert path.endswith("attachments/plan.txt")
    r2 = client.get("/api/download", params={"path": path})
    assert r2.status_code == 200
    assert r2.content == b"kubernetes 部署方案"

def test_doc_endpoint(client):
    client.post("/api/ingest", json={"text": "内容 X"})
    tree = client.get("/api/tree").json()["docs"]
    r = client.get("/api/doc", params={"path": tree[0]})
    assert r.status_code == 200
    assert "body" in r.json()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv\Scripts\pytest tests/test_api.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3a: 实现 deps.py（依赖容器）**

```python
# app/deps.py
from __future__ import annotations
from dataclasses import dataclass
from app.config import Settings
from app.models.llm import LLMClient, OpenAILLMClient
from app.storage.repo import KnowledgeRepo
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.engine.retriever import Retriever
from app.engine.pending import PendingStore
from app.engine.organizer import Organizer


@dataclass
class Container:
    settings: Settings
    llm: LLMClient
    repo: KnowledgeRepo
    indexer: Indexer
    retriever: Retriever
    pending: PendingStore
    organizer: Organizer


def build_container(settings: Settings, llm: LLMClient | None = None) -> Container:
    llm = llm or OpenAILLMClient(settings)
    repo = KnowledgeRepo(settings.kb_path)
    index_dir = settings.kb_path / ".kb" / "index"
    vector = VectorIndex(index_dir / "vec")
    fulltext = FullTextIndex(index_dir / "fts.db")
    indexer = Indexer(vector, fulltext, llm)
    retriever = Retriever(vector, fulltext, llm)
    pending = PendingStore(settings.kb_path / ".kb" / "pending.json")
    organizer = Organizer(repo=repo, retriever=retriever, indexer=indexer,
                          pending=pending, llm=llm)
    return Container(settings=settings, llm=llm, repo=repo, indexer=indexer,
                     retriever=retriever, pending=pending, organizer=organizer)
```

- [ ] **Step 3b: 实现 api/routes.py**

```python
# app/api/routes.py
from __future__ import annotations
import io
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api")


class IngestBody(BaseModel):
    text: str


class AskBody(BaseModel):
    query: str


class ResolveBody(BaseModel):
    choice: str


def _c(request: Request):
    return request.app.state.container


@router.post("/ingest")
def ingest(body: IngestBody, request: Request):
    result = _c(request).organizer.ingest_text(body.text)
    return result.__dict__


@router.post("/ask")
def ask(body: AskBody, request: Request):
    ans = _c(request).retriever.answer(body.query)
    return ans.__dict__


@router.post("/upload")
async def upload(request: Request, file: UploadFile = File(...), category: str = Form("未分类")):
    c = _c(request)
    data = await file.read()
    rel = c.repo.save_attachment(category, file.filename, data,
                                 commit_msg=f"add attachment {file.filename}")
    # 抽取文本并索引（可读类文件）
    abs_path = c.repo._abs(rel)
    from app.index.extract import extract_text
    text = extract_text(abs_path)
    if text.strip():
        c.indexer.reindex_doc(rel, text)
    c.repo.log_change(f"上传附件 {rel}", commit_msg=f"chore: changelog upload {file.filename}")
    return {"attachment": rel, "indexed": bool(text.strip())}


@router.get("/download")
def download(path: str, request: Request):
    try:
        data = _c(request).repo.get_attachment(path)
    except FileNotFoundError:
        raise HTTPException(404, "文件不存在")
    filename = path.rsplit("/", 1)[-1]
    return StreamingResponse(io.BytesIO(data), media_type="application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/tree")
def tree(request: Request):
    return {"docs": _c(request).repo.list_tree()}


@router.get("/doc")
def doc(path: str, request: Request):
    try:
        d = _c(request).repo.read_doc(path)
    except FileNotFoundError:
        raise HTTPException(404, "文档不存在")
    return {"rel_path": d.rel_path, "meta": d.meta, "body": d.body}


@router.get("/questions")
def questions(request: Request):
    return {"questions": _c(request).pending.list_open()}


@router.post("/questions/{qid}/resolve")
def resolve(qid: str, body: ResolveBody, request: Request):
    result = _c(request).organizer.resolve_pending(qid, body.choice)
    return result.__dict__
```

- [ ] **Step 3c: 实现 main.py**

```python
# app/main.py
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import Settings, get_settings
from app.models.llm import LLMClient
from app.deps import build_container
from app.api.routes import router


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="对话式知识管家")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )
    app.state.container = build_container(settings, llm=llm)
    app.include_router(router)
    return app


app = create_app()
```

注意：`app = create_app()` 在模块导入时会构建真实的 `OpenAILLMClient`（不发请求，仅初始化）。测试通过 `create_app(settings=..., llm=FakeLLMClient())` 覆盖，不触发该行。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 5: 跑全量后端测试**

Run: `.venv\Scripts\pytest -q`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/deps.py backend/app/main.py backend/app/api/routes.py backend/tests/conftest.py backend/tests/test_api.py
git commit -m "feat: FastAPI 装配与全部 HTTP 端点"
```

---

## Task 13: 前端 React 聊天界面

**Files:**
- Create: `frontend/`（Vite React TS 脚手架）
- Create: `frontend/src/api.ts`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/components/Chat.tsx`
- Create: `frontend/src/components/Sidebar.tsx`
- Create: `frontend/.env`（`VITE_API_BASE=http://localhost:8000`）

前端 UI 逻辑用手动验证为主（不引入前端测试框架，保持 MVP 精简）。

- [ ] **Step 1: 脚手架**

Run: `npm create vite@latest frontend -- --template react-ts && cd frontend && npm install`
Expected: 生成 `frontend/`，依赖安装成功。

- [ ] **Step 2: 写 API 封装 `src/api.ts`**

```typescript
const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export async function ingest(text: string) {
  const r = await fetch(`${BASE}/api/ingest`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return r.json();
}

export async function ask(query: string) {
  const r = await fetch(`${BASE}/api/ask`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  return r.json();
}

export async function uploadFile(file: File, category: string) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("category", category);
  const r = await fetch(`${BASE}/api/upload`, { method: "POST", body: fd });
  return r.json();
}

export async function getTree() {
  const r = await fetch(`${BASE}/api/tree`);
  return r.json();
}

export async function getQuestions() {
  const r = await fetch(`${BASE}/api/questions`);
  return r.json();
}

export async function resolveQuestion(qid: string, choice: string) {
  const r = await fetch(`${BASE}/api/questions/${qid}/resolve`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ choice }),
  });
  return r.json();
}

export function downloadUrl(path: string) {
  return `${BASE}/api/download?path=${encodeURIComponent(path)}`;
}
```

- [ ] **Step 3: 写 `src/components/Chat.tsx`**

```tsx
import { useState } from "react";
import { ingest, ask, uploadFile, downloadUrl } from "../api";

type Msg = { role: "user" | "assistant"; text: string; sources?: string[]; attachments?: string[] };

export function Chat() {
  const [mode, setMode] = useState<"remember" | "recall">("remember");
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);

  async function send() {
    if (!input.trim()) return;
    const text = input;
    setMsgs((m) => [...m, { role: "user", text }]);
    setInput("");
    if (mode === "remember") {
      const r = await ingest(text);
      setMsgs((m) => [...m, { role: "assistant", text: r.message }]);
    } else {
      const r = await ask(text);
      setMsgs((m) => [...m, { role: "assistant", text: r.text, sources: r.sources, attachments: r.attachments }]);
    }
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const r = await uploadFile(f, "未分类");
    setMsgs((m) => [...m, { role: "assistant", text: `已保存文件：${r.attachment}` }]);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: 8 }}>
        <button onClick={() => setMode("remember")} disabled={mode === "remember"}>记录</button>
        <button onClick={() => setMode("recall")} disabled={mode === "recall"}>提问</button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
        {msgs.map((m, i) => (
          <div key={i} style={{ margin: "8px 0", textAlign: m.role === "user" ? "right" : "left" }}>
            <div style={{ display: "inline-block", padding: "8px 12px", borderRadius: 8,
                          background: m.role === "user" ? "#daf1ff" : "#f0f0f0" }}>
              {m.text}
              {m.sources && m.sources.length > 0 && (
                <div style={{ fontSize: 12, color: "#666", marginTop: 6 }}>
                  来源：{m.sources.join("、")}
                </div>
              )}
              {m.attachments && m.attachments.map((a) => (
                <div key={a}><a href={downloadUrl(a)}>下载附件：{a.split("/").pop()}</a></div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", padding: 8, gap: 8 }}>
        <input value={input} onChange={(e) => setInput(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && send()}
               placeholder={mode === "remember" ? "告诉我要记住的内容…" : "问我任何已记录的内容…"}
               style={{ flex: 1, padding: 8 }} />
        <label style={{ padding: 8, cursor: "pointer" }}>
          📎<input type="file" hidden onChange={onFile} />
        </label>
        <button onClick={send}>发送</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 写 `src/components/Sidebar.tsx`（目录浏览 + 待确认问题）**

```tsx
import { useEffect, useState } from "react";
import { getTree, getQuestions, resolveQuestion } from "../api";

export function Sidebar() {
  const [docs, setDocs] = useState<string[]>([]);
  const [questions, setQuestions] = useState<any[]>([]);

  async function refresh() {
    setDocs((await getTree()).docs);
    setQuestions((await getQuestions()).questions);
  }
  useEffect(() => { refresh(); }, []);

  return (
    <div style={{ width: 280, borderRight: "1px solid #eee", padding: 12, overflowY: "auto" }}>
      <h4>待我确认</h4>
      {questions.length === 0 && <div style={{ color: "#999" }}>无</div>}
      {questions.map((q) => (
        <div key={q.id} style={{ marginBottom: 12, fontSize: 13 }}>
          <div>{q.question}</div>
          {q.options.map((o: any) => (
            <button key={o.id} onClick={async () => { await resolveQuestion(q.id, o.id); refresh(); }}
                    style={{ marginRight: 6, marginTop: 4 }}>{o.label}</button>
          ))}
        </div>
      ))}
      <h4 style={{ marginTop: 16 }}>知识库目录</h4>
      {docs.map((d) => <div key={d} style={{ fontSize: 13, padding: "2px 0" }}>{d}</div>)}
      <button onClick={refresh} style={{ marginTop: 12 }}>刷新</button>
    </div>
  );
}
```

- [ ] **Step 5: 写 `src/App.tsx`**

```tsx
import { Chat } from "./components/Chat";
import { Sidebar } from "./components/Sidebar";

export default function App() {
  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "system-ui" }}>
      <Sidebar />
      <div style={{ flex: 1 }}><Chat /></div>
    </div>
  );
}
```

- [ ] **Step 6: 手动验证**

Run（两个终端）：
- 后端：`cd backend && .venv\Scripts\uvicorn app.main:app --reload --port 8000`
- 前端：`cd frontend && npm run dev`

打开前端 URL，验证：①「记录」模式发一条内容 → 侧栏目录出现新 md；②「提问」模式问相关内容 → 得到回答与来源；③上传一个 txt → 提示已保存 → 提问能命中并给下载链接。
Expected: 三个场景都通过（需在 `backend/.env` 配好真实 OpenAI 兼容模型 key 才能得到智能回答）。

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat: React 聊天前端（记录/提问/上传/目录/待确认）"
```

---

## Task 14: 端到端联调与样例验证

**Files:**
- Create: `backend/.env.example`
- Create: `README.md`
- Create: `backend/tests/test_eval_smoke.py`

- [ ] **Step 1: 写 `.env.example`**

```
KB_PATH=./knowledge
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
SMALL_MODEL=gpt-4o-mini
BIG_MODEL=gpt-4o
EMBED_MODEL=text-embedding-3-small
```

- [ ] **Step 2: 写去重行为冒烟测试（用 FakeLLM 驱动 merge 分支）**

```python
# tests/test_eval_smoke.py
import json
from app.config import Settings
from app.deps import build_container
from app.models.llm import FakeLLMClient

def test_second_similar_note_merges(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge")
    d1 = json.dumps({"action": "new", "rel_path": "技术/docker/常用命令.md",
                     "title": "常用命令", "category": "技术/docker", "tags": ["docker"],
                     "ambiguous": False, "reason": "新主题"})
    d2 = json.dumps({"action": "merge", "rel_path": "技术/docker/常用命令.md",
                     "title": "常用命令", "category": "技术/docker", "tags": ["docker"],
                     "ambiguous": False, "reason": "同为 docker 命令"})
    llm = FakeLLMClient(chat_responses=["摘要1", d1, "摘要2", d2], embed_dim=8)
    c = build_container(settings, llm=llm)
    c.organizer.ingest_text("docker ps 查看容器")
    c.organizer.ingest_text("docker logs 查看日志")
    doc = c.repo.read_doc("技术/docker/常用命令.md")
    assert "docker ps" in doc.body and "docker logs" in doc.body  # 合并到同一文档，避免重复文件
```

- [ ] **Step 3: 运行测试确认通过**

Run: `.venv\Scripts\pytest tests/test_eval_smoke.py -v`
Expected: PASS

- [ ] **Step 4: 写 README（启动说明）**

内容包含：项目简介、后端启动（venv、装依赖、配 `.env`、`uvicorn app.main:app`）、前端启动（`npm install && npm run dev`）、数据目录说明（`knowledge/` 可直接浏览/编辑、git 历史、`.kb/changelog.md`）。

- [ ] **Step 5: 跑全量测试**

Run: `cd backend && .venv\Scripts\pytest -q`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/.env.example backend/tests/test_eval_smoke.py README.md
git commit -m "docs: 环境样例、去重冒烟测试与 README"
```

---

## 自检（Self-Review）结果

**1. Spec 覆盖：**
- 数据主权（md+目录+可读可编辑）→ Task 4（KnowledgeRepo，纯文件+frontmatter）。✅
- git 版本化/changelog（C+D 的 D）→ Task 4 `_commit`/`log_change`，各引擎调用。✅
- 重叠拿不准问用户（C）→ Task 9 PendingStore + Task 11 ambiguous 分支 + Task 12 questions 端点 + Task 13 侧栏。✅
- 混合检索（D）→ Task 6/7/8/10。✅
- 带来源回答/找不到不编造 → Task 10。✅
- 附件存取 + 可读文件抽取入索引 + 原件返回 → Task 5 extract、Task 12 upload/download、Task 10 附件命中。✅
- 大小模型分工 → Task 2 `chat(big=...)`；组织用小模型，回答用大模型。✅
- OpenAI 兼容/可插拔 → Task 1/2。✅
- Web 聊天 MVP → Task 13。✅
- 验证/测试 → 各任务 TDD + Task 14 冒烟。✅
- 第二期（园丁巡检/审核/联网/生图）、第三期（桌面/微信飞书）→ 明确排除在本计划外，后续单独出计划。✅

**2. 占位符扫描：** 无 TBD/TODO；所有代码步骤均含完整代码。README 正文以要点描述（非代码文件，可接受）。

**3. 类型一致性：** `Hit`、`Document`、`Answer`、`PlacementDecision`、`IngestResult` 跨任务签名一致；`reindex_doc(doc_id, text)`、`search(query,k)`、`answer(query)`、`ingest_text`、`resolve_pending(qid,choice)`、`save_attachment(rel_dir,filename,data,*,commit_msg)`、`get_attachment(rel_path)` 全程统一。`_ATTACH_MARKER="/attachments/"` 与 `save_attachment` 生成的路径一致。

---

## 未决/后续（不阻塞 MVP）

- 单用户假设；多用户鉴权后续再加。
- Chroma 首次导入较重；如需更轻可后续替换 LanceDB（接口已隔离在 `vector.py`）。
- FTS5 `trigram` 对超短查询（<3 字符）可能召回为空，由向量侧兜底。
- 大模型"审核"环节（写入流水线第 5 步）在 MVP 中留作第二期强化，当前由小模型决策直接落地 + git 可回滚兜底。
