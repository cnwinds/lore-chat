# Demo 运行时 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Lore 在 `DEMO_MODE` 下向匿名访客开放一个硬只读、对话不落库、但仍能看到「写入会发生什么」的公开演示站。

**Architecture:** 一个部署级开关 `DEMO_MODE`；`AuthMiddleware` 解析出 `admin` / `guest` 两种身份；新增 `DemoGuardMiddleware` 按**路由模板白名单**放行 guest 的读请求，其余一律 403；Agent 侧三层防写（工具目录裁剪 → dispatch 硬拒 → `KnowledgeWriter` 只读断言），其中写类工具替换为同名同 schema 的「预览式」实现，返回 `status: "preview_only"` 与完整内容供前端渲染预览卡。

**Tech Stack:** Python 3 / FastAPI / Starlette middleware / pytest；React + TypeScript / Vitest。

## Global Constraints

- 设计依据：`docs/superpowers/specs/2026-08-18-demo-mode-design.md`。与 spec 冲突时以 spec 为准，除非本计划显式标注偏差。
- `DEMO_MODE` 是部署级开关，**必须**加入 `EDITABLE_SETTING_KEYS` 的排除集合，不可经设置页热改。
- 只读门禁**必须**是白名单（默认拒绝）。任何"加个黑名单条目"的实现方式都是错的。
- 访客 session **不得**落盘，**不得**写入 `.kb/sessions.json`。
- guest 读 `GET /api/admin/settings` 时密钥字段必须是 `"***"`，不得保留任何真实片段。
- `admin` 身份不受任何 demo 限制，行为与今天完全一致。
- 现有 cookie 常量是 `COOKIE = "lorechat_session"`（`backend/app/auth/routes.py:10`）；访客 cookie 用 `lorechat_guest`。
- 后端测试：`cd backend && python -m pytest`。前端测试：`cd frontend && npx vitest run`。
- 每个 Task 结束时提交一次。

## 与 spec 的一处偏差（已确认）

spec §6.2 把 `summarize_conversation` 列入「预览式」。实现上它必须有具名会话才有归档对象，而 demo 下访客的对话永远是 ephemeral（`conversation_id` 为 `None`），预览没有落点。**本计划将其归入「移除」类**，由 demo 系统提示说明演示环境不提供整段归档。Task 9 完成后需回写 spec §6.2 的表格。

同样地，spec §6.3 写的「真实跑 `PlacementPlanner`」在 `write_doc` 这条路径上不成立：模型已在工具参数里给出 `directory` + `filename`（见 `CONTEXT.md` 的知识库路径约定），`Organizer.ingest_text` 收到的是 `forced_rel_path`，`PlacementPlanner` 不参与。预览实现因此只复用 `resolve_kb_location` 做路径校验，**不调用 Organizer**（调用它就会写盘）。Task 8 完成后需回写 spec §6.3。

---

## 文件结构

**新建**

| 文件 | 职责 |
|------|------|
| `backend/app/demo/__init__.py` | 包入口，导出 `is_demo_mode` / `Identity` |
| `backend/app/demo/identity.py` | 身份常量与 `resolve_identity(request)` |
| `backend/app/demo/guest_sessions.py` | 进程内访客 session 存储（TTL + 容量上限） |
| `backend/app/demo/guard.py` | `DemoGuardMiddleware` + 路由模板白名单 |
| `backend/app/demo/quota.py` | 访客 / IP / 全站限流计数 |
| `backend/app/demo/redact.py` | guest 视角的设置密钥全量遮蔽 |
| `backend/app/engine/agent/tool_impl/demo_preview.py` | 预览式写工具与被移除工具名单 |
| `frontend/src/hooks/useDemoCapability.ts` | 前端能力判定单一来源 |
| `frontend/src/components/demo/DemoBanner.tsx` | 顶部常驻演示条 |
| `frontend/src/components/demo/DemoPreviewCard.tsx` | 预览卡渲染 |

**修改**

| 文件 | 改动 |
|------|------|
| `backend/app/config.py` | `demo_mode` 字段 + 排除出可编辑集 |
| `backend/app/auth/middleware.py` | 身份解析、demo 下自动签发访客 |
| `backend/app/auth/routes.py` | `POST /api/auth/guest`、`status` 增加 demo 字段、demo 下禁 setup |
| `backend/app/main.py` | 挂 `DemoGuardMiddleware`、`app.state.guest_sessions`、`app.state.demo_quota` |
| `backend/app/api/admin_routes.py` | guest 读设置时二次遮蔽 |
| `backend/app/api/chat_routes.py` | guest 只允许 ephemeral、限流、`ephemeral_from` |
| `backend/app/api/http_deps.py` | `ChatBody.ephemeral_from` |
| `backend/app/engine/chat/session_runner.py` | `stream_ephemeral` 接受 `history` |
| `backend/app/engine/agent/tool_catalog.py` | `select_tools(..., demo=False)` |
| `backend/app/engine/agent/orchestrator.py` | 透传 `demo=self.settings.demo_mode` |
| `backend/app/engine/agent/tool_dispatch.py` | demo 硬拒 + 预览替换 |
| `backend/app/engine/agent/tools.py` | `ToolRegistry(demo_mode=...)` |
| `backend/app/engine/agent/prompts.py` | demo 环境契约段 |
| `backend/app/engine/agent/message_builder.py` | 透传 `demo_mode` |
| `backend/app/engine/knowledge_writer.py` | `read_only` 断言 |
| `backend/app/deps.py` | 构造时传 `demo_mode` / `read_only` |
| `frontend/src/api.ts` | `AuthStatus` 增加 demo 字段、`postGuestSession` |
| `frontend/src/App.tsx` | demo 下跳过登录门 |
| `frontend/src/lib/httpTransport.ts` | 403 `demo_read_only` 全局兜底事件 |

---

## Task 1: DEMO_MODE 配置开关

**Files:**
- Modify: `backend/app/config.py:141-171`
- Create: `backend/app/demo/__init__.py`
- Test: `backend/tests/test_demo_config.py`

**Interfaces:**
- Produces: `Settings.demo_mode: bool`（默认 `False`，env `DEMO_MODE`）

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_demo_config.py`：

```python
from app.config import EDITABLE_SETTING_KEYS, Settings


def test_demo_mode_defaults_to_false():
    assert Settings(kb_path="./knowledge").demo_mode is False


def test_demo_mode_reads_env(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    assert Settings(kb_path="./knowledge").demo_mode is True


def test_demo_mode_is_not_hot_editable():
    """部署级开关：可从设置页热改就等于只读能被 UI 关掉。"""
    assert "demo_mode" not in EDITABLE_SETTING_KEYS
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_demo_config.py -v`
Expected: FAIL，`AttributeError: 'Settings' object has no attribute 'demo_mode'`

- [ ] **Step 3: 实现**

在 `backend/app/config.py` 的 `Settings` 类里，紧跟 `sandbox_mirror_region` 之后加：

```python
    # 公开演示站：访客只读 + 对话不落库。部署级开关，禁止经设置页热改
    demo_mode: bool = False
```

在 `EDITABLE_SETTING_KEYS` 的排除集合里加一行（`"kb_path",` 之后）：

```python
        # 公开演示站开关：热改等于允许从 UI 关掉只读门禁
        "demo_mode",
```

创建 `backend/app/demo/__init__.py`：

```python
"""公开演示站运行时：访客身份、只读门禁、限流。"""

from app.demo.identity import IDENTITY_ADMIN, IDENTITY_GUEST, resolve_identity

__all__ = ["IDENTITY_ADMIN", "IDENTITY_GUEST", "resolve_identity"]
```

创建 `backend/app/demo/identity.py`（本 Task 只放常量，`resolve_identity` 在 Task 3 填充）：

```python
from __future__ import annotations

IDENTITY_ADMIN = "admin"
IDENTITY_GUEST = "guest"
IDENTITY_NONE = "none"


def resolve_identity(request) -> str:
    """读取中间件写入的身份；未经中间件时视为无身份。"""
    return getattr(request.state, "identity", IDENTITY_NONE)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_demo_config.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/config.py backend/app/demo backend/tests/test_demo_config.py
git commit -m "feat(demo): 增加部署级 DEMO_MODE 开关"
```

---

## Task 2: 访客 session 进程内存储

**Files:**
- Create: `backend/app/demo/guest_sessions.py`
- Test: `backend/tests/test_demo_guest_sessions.py`

**Interfaces:**
- Produces:
  - `GuestSessionStore(ttl_seconds: int = 7200, capacity: int = 10000)`
  - `.create(ip: str | None = None) -> str`
  - `.validate(session_id: str | None) -> bool`
  - `.touch_message(session_id: str) -> int`（自增并返回该访客已发消息数）
  - `.message_count(session_id: str) -> int`

**为什么不复用 `SessionStore`：** 现有实现每次 `validate()` 都因滑动过期重写 `.kb/sessions.json`（`backend/app/auth/sessions.py:47-66`）。公开站并发访客会把它写成瓶颈，还会把演示数据目录写脏。

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_demo_guest_sessions.py`：

```python
import time

from app.demo.guest_sessions import GuestSessionStore


def test_create_then_validate():
    store = GuestSessionStore()
    sid = store.create(ip="1.2.3.4")
    assert store.validate(sid) is True


def test_unknown_and_empty_session_is_invalid():
    store = GuestSessionStore()
    assert store.validate("nope") is False
    assert store.validate(None) is False


def test_expired_session_is_invalid():
    store = GuestSessionStore(ttl_seconds=0)
    sid = store.create()
    time.sleep(0.01)
    assert store.validate(sid) is False


def test_capacity_evicts_oldest():
    store = GuestSessionStore(capacity=2)
    first = store.create()
    second = store.create()
    third = store.create()
    assert store.validate(first) is False
    assert store.validate(second) is True
    assert store.validate(third) is True


def test_touch_message_counts_per_session():
    store = GuestSessionStore()
    sid = store.create()
    assert store.touch_message(sid) == 1
    assert store.touch_message(sid) == 2
    assert store.message_count(sid) == 2


def test_store_writes_nothing_to_disk(tmp_path):
    """访客 session 落盘会污染演示知识库并造成并发写竞态。"""
    before = set(tmp_path.rglob("*"))
    store = GuestSessionStore()
    sid = store.create()
    store.validate(sid)
    store.touch_message(sid)
    assert set(tmp_path.rglob("*")) == before
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_demo_guest_sessions.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.demo.guest_sessions'`

- [ ] **Step 3: 实现**

创建 `backend/app/demo/guest_sessions.py`：

```python
from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

DEFAULT_TTL_SECONDS = 2 * 3600
DEFAULT_CAPACITY = 10000


@dataclass
class _GuestSession:
    expires_at: float
    ip: str | None = None
    message_count: int = field(default=0)


class GuestSessionStore:
    """访客 session：只在进程内，不落盘。重启后访客自动重新签发。"""

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        capacity: int = DEFAULT_CAPACITY,
    ) -> None:
        self._ttl = ttl_seconds
        self._capacity = max(1, capacity)
        self._lock = threading.Lock()
        self._sessions: OrderedDict[str, _GuestSession] = OrderedDict()

    def create(self, ip: str | None = None) -> str:
        sid = secrets.token_urlsafe(24)
        with self._lock:
            self._sessions[sid] = _GuestSession(
                expires_at=time.monotonic() + self._ttl, ip=ip
            )
            while len(self._sessions) > self._capacity:
                self._sessions.popitem(last=False)
        return sid

    def validate(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return False
            if entry.expires_at <= time.monotonic():
                self._sessions.pop(session_id, None)
                return False
            return True

    def touch_message(self, session_id: str) -> int:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return 0
            entry.message_count += 1
            return entry.message_count

    def message_count(self, session_id: str) -> int:
        with self._lock:
            entry = self._sessions.get(session_id)
            return entry.message_count if entry else 0
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_demo_guest_sessions.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/demo/guest_sessions.py backend/tests/test_demo_guest_sessions.py
git commit -m "feat(demo): 进程内访客 session 存储"
```

---

## Task 3: 身份解析、访客签发、demo 下关闭 setup

**Files:**
- Modify: `backend/app/auth/middleware.py:9-39`
- Modify: `backend/app/auth/routes.py:38-70`
- Modify: `backend/app/main.py:155-201`
- Modify: `backend/app/demo/identity.py`
- Test: `backend/tests/test_demo_auth.py`

**Interfaces:**
- Consumes: `GuestSessionStore`（Task 2）、`Settings.demo_mode`（Task 1）
- Produces:
  - `request.state.identity ∈ {"admin", "guest", "none"}`
  - cookie 常量 `GUEST_COOKIE = "lorechat_guest"`（在 `backend/app/auth/routes.py`）
  - `POST /api/auth/guest` → `{"ok": True, "role": "guest"}` + Set-Cookie
  - `GET /api/auth/status` → 增加 `"demo": bool` 与 `"role": str`

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_demo_auth.py`：

```python
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.llm import FakeLLMClient


@pytest.fixture
def demo_client(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge", demo_mode=True)
    llm = FakeLLMClient(chat_responses=["ok"] * 20, embed_dim=8)
    app = create_app(settings=settings, llm=llm)
    with TestClient(app) as client:
        yield client


def test_status_reports_demo_and_role(demo_client):
    body = demo_client.get("/api/auth/status").json()
    assert body["demo"] is True
    assert body["role"] in ("none", "guest")


def test_guest_endpoint_issues_cookie(demo_client):
    r = demo_client.post("/api/auth/guest")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "role": "guest"}
    assert "lorechat_guest" in r.cookies


def test_guest_cookie_grants_read_access(demo_client):
    demo_client.post("/api/auth/guest")
    r = demo_client.get("/api/tree")
    assert r.status_code == 200


def test_status_role_is_guest_after_issue(demo_client):
    demo_client.post("/api/auth/guest")
    assert demo_client.get("/api/auth/status").json()["role"] == "guest"


def test_setup_is_forbidden_in_demo(demo_client):
    """否则任何访客都能抢先把自己设成管理员。"""
    r = demo_client.post("/api/auth/setup", json={"password": "hijack-me-12345"})
    assert r.status_code == 403
    assert r.json()["code"] == "demo_setup_disabled"


def test_guest_endpoint_absent_outside_demo(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge")
    llm = FakeLLMClient(chat_responses=["ok"] * 20, embed_dim=8)
    app = create_app(settings=settings, llm=llm)
    with TestClient(app) as client:
        assert client.post("/api/auth/guest").status_code == 403


def test_guest_sessions_do_not_touch_sessions_json(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge", demo_mode=True)
    llm = FakeLLMClient(chat_responses=["ok"] * 20, embed_dim=8)
    app = create_app(settings=settings, llm=llm)
    with TestClient(app) as client:
        client.post("/api/auth/guest")
        client.get("/api/tree")
    assert not (tmp_path / "knowledge" / ".kb" / "sessions.json").exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_demo_auth.py -v`
Expected: FAIL，`KeyError: 'demo'` 与 404 / 401

- [ ] **Step 3: 实现 — 访客 cookie 与路由**

在 `backend/app/auth/routes.py` 顶部常量区（第 10-11 行附近）加：

```python
GUEST_COOKIE = "lorechat_guest"
_GUEST_COOKIE_MAX_AGE_SECONDS = 2 * 3600
```

在同文件加一个 helper 与新路由（放在 `auth_status` 之前）：

```python
def _demo_enabled(request: Request) -> bool:
    return bool(request.app.state.settings_store.get().demo_mode)


@router.post("/guest")
def auth_guest(request: Request, response: Response):
    if not _demo_enabled(request):
        return Response(
            status_code=403,
            content='{"detail": "demo mode disabled", "code": "demo_disabled"}',
            media_type="application/json",
        )
    guests = request.app.state.guest_sessions
    client = request.client
    sid = guests.create(ip=client.host if client else None)
    response.set_cookie(
        GUEST_COOKIE,
        sid,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=_GUEST_COOKIE_MAX_AGE_SECONDS,
    )
    return {"ok": True, "role": "guest"}
```

改写 `auth_status`：

```python
@router.get("/status")
def auth_status(request: Request):
    auth = request.app.state.auth_store
    sessions = request.app.state.session_store
    sid = request.cookies.get(COOKIE)
    authenticated = sessions.validate(sid)
    demo = _demo_enabled(request)
    role = getattr(request.state, "identity", "none")
    return {
        "setup_required": False if demo else auth.is_setup_required(),
        "authenticated": authenticated,
        "demo": demo,
        "role": role,
    }
```

在 `auth_setup` 函数体最前面插入：

```python
    if _demo_enabled(request):
        return Response(
            status_code=403,
            content='{"detail": "setup disabled in demo", "code": "demo_setup_disabled"}',
            media_type="application/json",
        )
```

- [ ] **Step 4: 实现 — 中间件身份解析**

用下面内容整体替换 `backend/app/auth/middleware.py`：

```python
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.auth.routes import COOKIE, GUEST_COOKIE
from app.demo.identity import IDENTITY_ADMIN, IDENTITY_GUEST, IDENTITY_NONE

PUBLIC_ROUTES = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/api/auth/status"),
        ("POST", "/api/auth/setup"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/guest"),
    }
)

PUBLIC_PREFIXES = (
    ("GET", "/api/attachments/signed/"),
)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.identity = IDENTITY_NONE
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        if request.app.state.session_store.validate(request.cookies.get(COOKIE)):
            request.state.identity = IDENTITY_ADMIN
        elif bool(request.app.state.settings_store.get().demo_mode):
            guests = request.app.state.guest_sessions
            if guests.validate(request.cookies.get(GUEST_COOKIE)):
                request.state.identity = IDENTITY_GUEST

        if (request.method, path) in PUBLIC_ROUTES:
            return await call_next(request)
        for method, prefix in PUBLIC_PREFIXES:
            if request.method == method and path.startswith(prefix):
                return await call_next(request)

        if request.state.identity == IDENTITY_NONE:
            return JSONResponse(
                status_code=401,
                content={"detail": "authentication required", "code": "auth_required"},
            )
        return await call_next(request)
```

- [ ] **Step 5: 实现 — 装配**

在 `backend/app/main.py` 的 `create_app` 里，`app.state.maintenance_lock = MaintenanceLock()` 之后加：

```python
    app.state.guest_sessions = GuestSessionStore()
```

并在文件顶部导入区加：

```python
from app.demo.guest_sessions import GuestSessionStore
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_demo_auth.py -v`
Expected: 7 passed

- [ ] **Step 7: 确认没有回归**

Run: `cd backend && python -m pytest tests/test_auth.py tests/test_api.py -v`
Expected: 全部 passed（若无 `test_auth.py` 则只跑 `test_api.py`）

- [ ] **Step 8: 提交**

```bash
git add backend/app/auth backend/app/main.py backend/app/demo backend/tests/test_demo_auth.py
git commit -m "feat(demo): 访客身份签发与 demo 下关闭 setup"
```

---

## Task 4: DemoGuardMiddleware 白名单门禁

**Files:**
- Create: `backend/app/demo/guard.py`
- Modify: `backend/app/main.py:189-201`
- Test: `backend/tests/test_demo_guard.py`

**Interfaces:**
- Consumes: `request.state.identity`（Task 3）
- Produces:
  - `GUEST_READ_ROUTES: frozenset[tuple[str, str]]`（方法 + **路由模板**）
  - `DemoGuardMiddleware`
  - 拒绝响应：403 `{"detail": "演示环境为只读", "code": "demo_read_only"}`

**为什么按路由模板而不是原始路径匹配：** `/api/conversations/{cid}` 这类带路径参数的接口无法用字面量集合表达。用 Starlette 的 `route.matches(scope)` 拿到模板，既准确，也让"遍历全部路由"的回归测试可以直接对着同一份模板集断言。

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_demo_guard.py`：

```python
import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

from app.config import Settings
from app.demo.guard import GUEST_READ_ROUTES
from app.main import create_app
from app.models.llm import FakeLLMClient


@pytest.fixture
def demo_app(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge", demo_mode=True)
    llm = FakeLLMClient(chat_responses=["ok"] * 40, embed_dim=8)
    return create_app(settings=settings, llm=llm)


@pytest.fixture
def guest(demo_app):
    with TestClient(demo_app) as client:
        client.post("/api/auth/guest")
        yield client


def _api_routes(app) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, Route) or not route.path.startswith("/api/"):
            continue
        for method in sorted(route.methods or set()):
            if method in ("HEAD", "OPTIONS"):
                continue
            out.append((method, route.path))
    return out


def test_whitelist_only_names_real_routes(demo_app):
    """白名单里写错路径会静默失效，必须钉死。"""
    known = set(_api_routes(demo_app))
    unknown = {r for r in GUEST_READ_ROUTES if r not in known}
    assert unknown == set()


def test_every_non_whitelisted_route_is_forbidden_for_guest(demo_app, guest):
    """新增路由默认对访客关闭。这条失败说明有接口意外向公网开放了。"""
    opened: list[tuple[str, str]] = []
    for method, template in _api_routes(demo_app):
        if (method, template) in GUEST_READ_ROUTES:
            continue
        url = template.replace("{cid}", "x").replace("{merge_id}", "x")
        url = url.replace("{qid}", "x").replace("{fact_id}", "x")
        url = url.replace("{path:path}", "x")
        r = guest.request(method, url)
        if r.status_code != 403 or r.json().get("code") != "demo_read_only":
            opened.append((method, template))
    assert opened == []


def test_export_is_blocked_for_guest(guest):
    """导出包含 auth.json 与明文密钥的 settings.json。"""
    r = guest.get("/api/admin/export")
    assert r.status_code == 403
    assert r.json()["code"] == "demo_read_only"


def test_download_zip_is_blocked_for_guest(guest):
    r = guest.get("/api/download-zip")
    assert r.status_code == 403


def test_whitelisted_read_passes(guest):
    assert guest.get("/api/tree").status_code == 200
    assert guest.get("/api/conversations").status_code == 200
    assert guest.get("/api/memory/facts").status_code == 200


def test_admin_is_not_restricted(demo_app):
    """demo 站的管理员走密码登录，行为与非 demo 部署一致。"""
    with TestClient(demo_app) as client:
        sid = demo_app.state.session_store.create()
        client.cookies.set("lorechat_session", sid)
        r = client.put("/api/doc", json={"path": "技术/x.md", "text": "hi"})
        assert r.status_code != 403
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_demo_guard.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.demo.guard'`

- [ ] **Step 3: 实现**

创建 `backend/app/demo/guard.py`：

```python
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Match

from app.demo.identity import IDENTITY_GUEST

# 访客可读路由：方法 + 路由模板。
# 白名单而非黑名单：新增接口默认对访客关闭，忘记加白名单只会让某个只读功能
# 在演示站不可用，而不会把写接口暴露到公网。
GUEST_READ_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/api/auth/status"),
        ("POST", "/api/auth/guest"),
        ("GET", "/api/tree"),
        ("GET", "/api/doc"),
        ("GET", "/api/download"),
        ("GET", "/api/attachments/signed/{path:path}"),
        ("GET", "/api/conversations"),
        ("GET", "/api/conversations/{cid}"),
        ("GET", "/api/conversations/{cid}/events"),
        ("GET", "/api/conversations/{cid}/turns/active/stream"),
        ("GET", "/api/questions"),
        ("GET", "/api/memory/facts"),
        ("GET", "/api/kb/discover-skills"),
        ("GET", "/api/enabled-skills"),
        ("GET", "/api/docs/merge/active"),
        ("GET", "/api/docs/merge/{merge_id}"),
        ("GET", "/api/admin/settings"),
        ("GET", "/api/admin/settings-attention"),
        ("GET", "/api/admin/model-catalog"),
        ("GET", "/api/usage/summary"),
        ("GET", "/api/usage/events"),
        ("GET", "/api/usage/prices"),
        ("GET", "/api/usage/prefs"),
        # 临时提问：guest 只能 ephemeral，由 chat 路由内断言
        ("POST", "/api/chat"),
    }
)


def resolve_route_template(app, scope) -> str | None:
    for route in app.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return getattr(route, "path", None)
    return None


class DemoGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if getattr(request.state, "identity", None) != IDENTITY_GUEST:
            return await call_next(request)
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)
        template = resolve_route_template(request.app, request.scope)
        if template is not None and (request.method, template) in GUEST_READ_ROUTES:
            return await call_next(request)
        return JSONResponse(
            status_code=403,
            content={"detail": "演示环境为只读", "code": "demo_read_only"},
        )
```

在 `backend/app/main.py` 导入区加：

```python
from app.demo.guard import DemoGuardMiddleware
```

中间件挂载顺序改为（`add_middleware` 后加的先执行，所以 Auth 必须在 Guard **之后**添加）：

```python
    app.add_middleware(MaintenanceGuardMiddleware)
    app.add_middleware(DemoGuardMiddleware)
    app.add_middleware(AuthMiddleware)
```

注意这替换了原来的两行 `add_middleware(AuthMiddleware)` / `add_middleware(MaintenanceGuardMiddleware)`：`AuthMiddleware` 必须最先跑（它写 `request.state.identity`），`DemoGuardMiddleware` 紧随其后读它。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_demo_guard.py -v`
Expected: 6 passed

- [ ] **Step 5: 确认没有回归**

Run: `cd backend && python -m pytest -q`
Expected: 全部 passed

- [ ] **Step 6: 提交**

```bash
git add backend/app/demo/guard.py backend/app/main.py backend/tests/test_demo_guard.py
git commit -m "feat(demo): 白名单式访客只读门禁"
```

---

## Task 5: 设置密钥对访客全量遮蔽

**Files:**
- Create: `backend/app/demo/redact.py`
- Modify: `backend/app/api/admin_routes.py:53-69`
- Test: `backend/tests/test_demo_redact.py`

**Interfaces:**
- Produces: `redact_secrets_for_guest(data: dict) -> dict`

**背景：** `SettingsStore.public_dict()` 把密钥脱敏为 `前2位***后4位`（`backend/app/settings_store.py:107-112`）。对匿名公开页面，泄漏真实密钥的头尾仍然是泄漏。

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_demo_redact.py`：

```python
from app.demo.redact import redact_secrets_for_guest


def test_top_level_keys_fully_masked():
    out = redact_secrets_for_guest({"openai_api_key": "sk***cdef", "big_model": "gpt-4o"})
    assert out["openai_api_key"] == "***"
    assert out["big_model"] == "gpt-4o"


def test_nested_chain_keys_fully_masked():
    out = redact_secrets_for_guest(
        {
            "chat_models": [{"id": "a", "model": "gpt-4o", "api_key": "sk***wxyz"}],
            "search_providers": [{"provider": "tavily", "api_key": "tv***1234"}],
            "image_providers": [{"provider": "x", "api_key": "im***5678"}],
        }
    )
    assert out["chat_models"][0]["api_key"] == "***"
    assert out["chat_models"][0]["model"] == "gpt-4o"
    assert out["search_providers"][0]["api_key"] == "***"
    assert out["image_providers"][0]["api_key"] == "***"


def test_none_key_stays_none():
    out = redact_secrets_for_guest({"small_api_key": None})
    assert out["small_api_key"] is None


def test_input_is_not_mutated():
    src = {"openai_api_key": "sk***cdef"}
    redact_secrets_for_guest(src)
    assert src["openai_api_key"] == "sk***cdef"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_demo_redact.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.demo.redact'`

- [ ] **Step 3: 实现**

创建 `backend/app/demo/redact.py`：

```python
from __future__ import annotations

import copy

from app.config import (
    CHAIN_IMAGE_SETTING_KEYS,
    CHAIN_MODEL_SETTING_KEYS,
    CHAIN_SEARCH_SETTING_KEYS,
    LEGACY_SEARCH_SECRET_KEYS,
    SECRET_SETTING_KEYS,
)

FULL_MASK = "***"

_CHAIN_KEYS = CHAIN_MODEL_SETTING_KEYS | CHAIN_SEARCH_SETTING_KEYS | CHAIN_IMAGE_SETTING_KEYS
_TOP_LEVEL_KEYS = SECRET_SETTING_KEYS | LEGACY_SEARCH_SECRET_KEYS


def redact_secrets_for_guest(data: dict) -> dict:
    """把设置里的全部密钥换成常量遮罩，不保留任何真实片段。"""
    out = copy.deepcopy(data)
    for key in _TOP_LEVEL_KEYS:
        if out.get(key) is not None:
            out[key] = FULL_MASK
    for key in _CHAIN_KEYS:
        chain = out.get(key)
        if not isinstance(chain, list):
            continue
        for item in chain:
            if isinstance(item, dict) and item.get("api_key") is not None:
                item["api_key"] = FULL_MASK
    return out
```

在 `backend/app/api/admin_routes.py` 导入区加：

```python
from app.demo.identity import IDENTITY_GUEST
from app.demo.redact import redact_secrets_for_guest
```

在 `get_settings` 的 `return data` 之前插入：

```python
    if getattr(request.state, "identity", None) == IDENTITY_GUEST:
        data = redact_secrets_for_guest(data)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_demo_redact.py -v`
Expected: 4 passed

- [ ] **Step 5: 补一条端到端断言**

在 `backend/tests/test_demo_guard.py` 末尾追加：

```python
def test_guest_settings_leak_no_key_fragment(demo_app, guest):
    demo_app.state.settings_store.get().openai_api_key = "sk-live-abcdefgh1234"
    body = guest.get("/api/admin/settings").json()
    assert body["openai_api_key"] == "***"
    assert "1234" not in str(body)
```

Run: `cd backend && python -m pytest tests/test_demo_guard.py -v`
Expected: 全部 passed

- [ ] **Step 6: 提交**

```bash
git add backend/app/demo/redact.py backend/app/api/admin_routes.py backend/tests/test_demo_redact.py backend/tests/test_demo_guard.py
git commit -m "feat(demo): 访客读取设置时全量遮蔽密钥"
```

---

## Task 6: 访客聊天强制 ephemeral

**Files:**
- Modify: `backend/app/api/chat_routes.py:54-86`
- Test: `backend/tests/test_demo_chat.py`

**Interfaces:**
- Consumes: `IDENTITY_GUEST`
- Produces: guest 带 `conversation_id` 调 `/api/chat` → 403 `demo_read_only`

**为什么放在路由层而不是中间件：** 中间件读请求体后需要重新注入 scope 才能被路由消费，是常见的隐性 bug 源。`/api/chat` 已在白名单内放行，临时性由路由自己断言。

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_demo_chat.py`：

```python
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.llm import FakeLLMClient


@pytest.fixture
def demo_app(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge", demo_mode=True)
    llm = FakeLLMClient(chat_responses=["演示回答"] * 40, embed_dim=8)
    return create_app(settings=settings, llm=llm)


@pytest.fixture
def guest(demo_app):
    with TestClient(demo_app) as client:
        client.post("/api/auth/guest")
        yield client


def test_guest_ephemeral_chat_streams(guest):
    r = guest.post("/api/chat", json={"text": "Lore 是什么"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")


def test_guest_chat_with_conversation_id_is_rejected(guest):
    r = guest.post("/api/chat", json={"text": "hi", "conversation_id": "any"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "demo_read_only"


def test_guest_chat_creates_no_conversation(demo_app, guest):
    guest.post("/api/chat", json={"text": "Lore 是什么"})
    assert guest.get("/api/conversations").json() == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_demo_chat.py -v`
Expected: FAIL，第二条返回 404「对话不存在」而不是 403

- [ ] **Step 3: 实现**

在 `backend/app/api/chat_routes.py` 导入区加：

```python
from app.demo.identity import IDENTITY_GUEST
```

在 `chat()` 函数体内，`c = container(request)` 之后立即插入：

```python
    is_guest = getattr(request.state, "identity", None) == IDENTITY_GUEST
    if is_guest and body.conversation_id:
        raise HTTPException(
            403,
            detail={"code": "demo_read_only", "detail": "演示环境的对话不会被保存"},
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_demo_chat.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/chat_routes.py backend/tests/test_demo_chat.py
git commit -m "feat(demo): 访客聊天强制走临时会话"
```

---

## Task 7: 工具目录裁剪

**Files:**
- Modify: `backend/app/engine/agent/tool_catalog.py:911-956`
- Modify: `backend/app/engine/agent/orchestrator.py:96-105`
- Create: `backend/app/engine/agent/tool_impl/demo_preview.py`（本 Task 只放名单常量）
- Test: `backend/tests/test_demo_tools.py`

**Interfaces:**
- Produces:
  - `DEMO_BLOCKED_TOOLS: frozenset[str]`、`DEMO_PREVIEW_TOOLS: frozenset[str]`（在 `demo_preview.py`）
  - `select_tools(..., demo: bool = False)`

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_demo_tools.py`：

```python
from app.engine.agent.prompts import MODE_DEFAULT
from app.engine.agent.tool_catalog import select_tools
from app.engine.agent.tool_impl.demo_preview import (
    DEMO_BLOCKED_TOOLS,
    DEMO_PREVIEW_TOOLS,
)


def _names(tools):
    return {t["function"]["name"] for t in tools}


def test_demo_catalog_drops_blocked_tools():
    names = _names(
        select_tools(MODE_DEFAULT, web_enabled=True, sandbox_enabled=True, demo=True)
    )
    assert names & DEMO_BLOCKED_TOOLS == set()


def test_demo_catalog_keeps_preview_tools_with_same_names():
    """同名同 schema：提示词与已沉淀的 Skill 方法不必为 demo 改写。"""
    names = _names(select_tools(MODE_DEFAULT, web_enabled=True, demo=True))
    assert DEMO_PREVIEW_TOOLS <= names | {"summarize_conversation"}
    assert "write_doc" in names
    assert "edit_doc" in names
    assert "manage_memory" in names


def test_demo_catalog_keeps_read_tools_and_web_search():
    names = _names(select_tools(MODE_DEFAULT, web_enabled=True, demo=True))
    assert {"search_kb", "read_doc", "list_kb_structure", "recall_memory"} <= names
    assert "web_search" in names


def test_demo_catalog_drops_fetch_url():
    """让匿名访客指定任意 URL 由服务器抓取是 SSRF 面。"""
    assert "fetch_url" not in _names(
        select_tools(MODE_DEFAULT, web_enabled=True, demo=True)
    )


def test_non_demo_catalog_is_unchanged():
    names = _names(select_tools(MODE_DEFAULT, web_enabled=True))
    assert "fetch_url" in names
    assert "write_kb_file" in names
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_demo_tools.py -v`
Expected: FAIL，`ModuleNotFoundError: app.engine.agent.tool_impl.demo_preview`

- [ ] **Step 3: 实现名单**

创建 `backend/app/engine/agent/tool_impl/demo_preview.py`：

```python
"""演示环境的工具替换：写类工具只出预览，高风险与按次计费工具直接移除。"""

from __future__ import annotations

# 移除：SSRF 面（fetch_url）、按次计费（generate_image）、演示站不部署（sandbox_*）、
# 预览价值低于风险（move_entry / delete_kb / write_kb_file）、
# 无归档对象（summarize_conversation：demo 下对话恒为 ephemeral）
DEMO_BLOCKED_TOOLS: frozenset[str] = frozenset(
    {
        "write_kb_file",
        "move_entry",
        "delete_kb",
        "generate_image",
        "fetch_url",
        "summarize_conversation",
        "sandbox_run",
        "sandbox_job_status",
        "sandbox_list_dir",
        "sandbox_read_file",
        "publish_from_sandbox",
        "stage_to_sandbox",
    }
)

# 保留同名同 schema，换成不落盘的预览实现
DEMO_PREVIEW_TOOLS: frozenset[str] = frozenset(
    {
        "write_doc",
        "edit_doc",
        "update_doc_meta",
        "manage_memory",
    }
)
```

- [ ] **Step 4: 实现目录裁剪**

在 `backend/app/engine/agent/tool_catalog.py` 的 `select_tools` 签名末尾加参数：

```python
    demo: bool = False,
```

在 `excluded` 计算之后、`windows = ...` 之前插入：

```python
    if demo:
        from app.engine.agent.tool_impl.demo_preview import DEMO_BLOCKED_TOOLS

        excluded |= DEMO_BLOCKED_TOOLS
```

并在 docstring 的能力门列表里补一行：

```
    - demo=True：移除 DEMO_BLOCKED_TOOLS（详见 tool_impl/demo_preview.py）。
```

在 `backend/app/engine/agent/orchestrator.py` 的 `select_tools(...)` 调用里补一个参数：

```python
            disclosure_windows=self.tools.disclosure_windows,
            demo=bool(getattr(self.settings, "demo_mode", False)),
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_demo_tools.py -v`
Expected: 5 passed

- [ ] **Step 6: 确认没有回归**

Run: `cd backend && python -m pytest tests/test_agent_tools.py tests/test_sandbox_tools.py tests/test_kb_file_tools.py -v`
Expected: 全部 passed

- [ ] **Step 7: 提交**

```bash
git add backend/app/engine/agent backend/tests/test_demo_tools.py
git commit -m "feat(demo): 按 demo 裁剪下发给模型的工具目录"
```

---

## Task 8: 预览式写工具与 dispatch 硬拒

**Files:**
- Modify: `backend/app/engine/agent/tool_impl/demo_preview.py`
- Modify: `backend/app/engine/agent/tool_dispatch.py:88-114`
- Modify: `backend/app/engine/agent/tools.py:45-111`
- Modify: `backend/app/deps.py:129-131`
- Test: `backend/tests/test_demo_preview_tools.py`

**Interfaces:**
- Consumes: `resolve_kb_location`（`app.engine.agent.tool_catalog`）
- Produces:
  - `blocked_result(name: str) -> dict`
  - `preview_write_doc(args: dict) -> dict`
  - `preview_edit_doc(args: dict) -> dict`
  - `preview_update_doc_meta(args: dict) -> dict`
  - `preview_manage_memory(args: dict) -> dict`
  - `demo_tool_result(name: str, args: dict) -> dict | None`（未命中返回 `None`）
  - `ToolRegistry(..., demo_mode: bool = False)`
  - 预览返回值形状：`{"summary", "sources", "status": "preview_only", "preview": {...}}`

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_demo_preview_tools.py`：

```python
import pytest

from app.engine.agent.tool_impl.demo_preview import (
    blocked_result,
    demo_tool_result,
    preview_manage_memory,
    preview_write_doc,
)


def test_write_doc_preview_reports_target_and_content():
    out = preview_write_doc(
        {"directory": "技术/检索", "filename": "选型.md", "text": "正文"}
    )
    assert out["status"] == "preview_only"
    assert out["preview"]["kind"] == "doc"
    assert out["preview"]["path"] == "技术/检索/选型.md"
    assert out["preview"]["content"] == "正文"


def test_write_doc_preview_prepends_context():
    out = preview_write_doc(
        {"directory": "技术", "filename": "a.md", "text": "正文", "context": "背景"}
    )
    assert out["preview"]["content"] == "背景\n\n正文"


def test_write_doc_preview_summary_says_not_persisted():
    """工具返回值必须让模型无法宣称已保存。"""
    out = preview_write_doc({"directory": "技术", "filename": "a.md", "text": "x"})
    assert "未落盘" in out["summary"]


def test_write_doc_preview_propagates_path_error():
    out = preview_write_doc({"directory": "技术", "filename": "a.txt", "text": "x"})
    assert out.get("status") != "preview_only"


def test_manage_memory_preview():
    out = preview_manage_memory({"action": "remember", "content": "偏好结论先行"})
    assert out["status"] == "preview_only"
    assert out["preview"]["kind"] == "memory"
    assert out["preview"]["content"] == "偏好结论先行"


def test_blocked_result_shape():
    out = blocked_result("sandbox_run")
    assert out["error"] == "demo_tool_unavailable"
    assert out["status"] == "failed"


@pytest.mark.parametrize("name", ["sandbox_run", "generate_image", "fetch_url"])
def test_demo_tool_result_blocks(name):
    assert demo_tool_result(name, {})["error"] == "demo_tool_unavailable"


def test_demo_tool_result_passes_through_read_tools():
    assert demo_tool_result("search_kb", {"query": "x"}) is None
```

追加一条集成断言到同文件：

```python
def test_registry_in_demo_never_writes(tmp_path):
    """兜底层：即使模型幻觉出写工具名，也不能落盘。"""
    import asyncio

    from app.config import Settings
    from app.deps import build_container
    from app.models.llm import FakeLLMClient

    settings = Settings(kb_path=tmp_path / "knowledge", demo_mode=True)
    container = build_container(settings, llm=FakeLLMClient(chat_responses=["x"], embed_dim=8))
    out = asyncio.run(
        container.tools.execute(
            "write_kb_file", {"directory": "技术", "filename": "a.sh", "text": "echo"}
        )
    )
    assert out["error"] == "demo_tool_unavailable"
    assert not (tmp_path / "knowledge" / "技术" / "a.sh").exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_demo_preview_tools.py -v`
Expected: FAIL，`ImportError: cannot import name 'blocked_result'`

- [ ] **Step 3: 实现预览实现**

在 `backend/app/engine/agent/tool_impl/demo_preview.py` 的名单常量之后追加：

```python
from app.engine.agent.tool_catalog import resolve_kb_location

_NOT_PERSISTED = "演示环境未落盘"


def blocked_result(name: str) -> dict:
    return {
        "summary": f"演示环境未提供该工具：{name}",
        "sources": [],
        "error": "demo_tool_unavailable",
        "status": "failed",
    }


def preview_write_doc(args: dict) -> dict:
    rel_path, err = resolve_kb_location(args)
    if err:
        return err
    text = args.get("text") or ""
    if args.get("context"):
        text = f"{args['context']}\n\n{text}"
    return {
        "summary": f"{_NOT_PERSISTED}。真实环境会写入：{rel_path}",
        "sources": [],
        "status": "preview_only",
        "preview": {
            "kind": "doc",
            "path": rel_path,
            "write_mode": args.get("write_mode", "auto"),
            "content": text,
        },
    }


def preview_edit_doc(args: dict) -> dict:
    path = (args.get("path") or "").replace("\\", "/").lstrip("/")
    return {
        "summary": f"{_NOT_PERSISTED}。真实环境会局部编辑：{path}",
        "sources": [],
        "status": "preview_only",
        "preview": {
            "kind": "doc_edit",
            "path": path,
            "edits": args.get("edits") or [],
            "insert": args.get("insert"),
        },
    }


def preview_update_doc_meta(args: dict) -> dict:
    path = (args.get("path") or "").replace("\\", "/").lstrip("/")
    return {
        "summary": f"{_NOT_PERSISTED}。真实环境会更新元数据：{path}",
        "sources": [],
        "status": "preview_only",
        "preview": {"kind": "doc_meta", "path": path, "meta": args.get("meta") or {}},
    }


def preview_manage_memory(args: dict) -> dict:
    action = args.get("action") or "remember"
    content = args.get("content") or ""
    return {
        "summary": f"{_NOT_PERSISTED}。真实环境会记住：{content}",
        "sources": [],
        "status": "preview_only",
        "preview": {"kind": "memory", "action": action, "content": content},
    }


_PREVIEW_HANDLERS = {
    "write_doc": preview_write_doc,
    "edit_doc": preview_edit_doc,
    "update_doc_meta": preview_update_doc_meta,
    "manage_memory": preview_manage_memory,
}


def demo_tool_result(name: str, args: dict) -> dict | None:
    """demo 下的工具结果；返回 None 表示按正常路径执行。"""
    if name in DEMO_BLOCKED_TOOLS:
        return blocked_result(name)
    handler = _PREVIEW_HANDLERS.get(name)
    if handler is not None:
        return handler(args)
    return None
```

- [ ] **Step 4: 接进 dispatch**

在 `backend/app/engine/agent/tool_dispatch.py` 的 `dispatch_tool` 函数体最前面插入：

```python
    if getattr(registry, "demo_mode", False):
        from app.engine.agent.tool_impl.demo_preview import demo_tool_result

        demo_out = demo_tool_result(name, args)
        if demo_out is not None:
            return demo_out
```

- [ ] **Step 5: 把 demo_mode 接到 ToolRegistry**

在 `backend/app/engine/agent/tools.py` 的 `ToolRegistry.__init__` 参数末尾加：

```python
        demo_mode: bool = False,
```

在 `self.sandbox_runtime = sandbox_runtime` 之后加：

```python
        self.demo_mode = demo_mode
```

在 `backend/app/deps.py` 里找到构造 `ToolRegistry(...)` 的位置，补上 `demo_mode=settings.demo_mode,`。

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_demo_preview_tools.py -v`
Expected: 9 passed

- [ ] **Step 7: 回写 spec**

把 `docs/superpowers/specs/2026-08-18-demo-mode-design.md` §6.2 表格里的 `summarize_conversation` 从「换成预览式」移到「移除」，并在 §6.3 把「真实跑 `PlacementPlanner`」改为「复用 `resolve_kb_location` 校验模型给出的目标路径」。

- [ ] **Step 8: 提交**

```bash
git add backend/app/engine/agent backend/app/deps.py backend/tests/test_demo_preview_tools.py docs/superpowers/specs/2026-08-18-demo-mode-design.md
git commit -m "feat(demo): 预览式写工具与 dispatch 层硬拒"
```

---

## Task 9: KnowledgeWriter 只读兜底

**Files:**
- Modify: `backend/app/engine/knowledge_writer.py:96-108`
- Modify: `backend/app/deps.py:129-131`
- Test: `backend/tests/test_demo_writer_readonly.py`

**Interfaces:**
- Produces:
  - `KnowledgeWriter(..., read_only: bool = False)`
  - `KnowledgeWriterReadOnly(RuntimeError)`

**为什么还要这一层：** `CONTEXT.md` 已确立 `KnowledgeWriter` 是路径 + git + 索引 + changelog 的唯一写入 seam。在这里断言可以覆盖所有绕过工具层的路径（后台 worker、未来新增的编排代码），成本只有几行。

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_demo_writer_readonly.py`：

```python
import pytest

from app.engine.knowledge_writer import KnowledgeWriter, KnowledgeWriterReadOnly
from app.storage.repo import KnowledgeRepo


@pytest.fixture
def writer(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    return KnowledgeWriter(repo, None, read_only=True)


def test_persist_document_is_refused(writer):
    with pytest.raises(KnowledgeWriterReadOnly):
        writer.persist_document("技术/a.md", {}, "正文", commit_msg="x")


def test_import_entry_is_refused(writer):
    with pytest.raises(KnowledgeWriterReadOnly):
        writer.import_entry(directory="技术", filename="a.png", data=b"x")


def test_move_entry_is_refused(writer):
    with pytest.raises(KnowledgeWriterReadOnly):
        writer.move_entry(from_path="技术/a.md", to_directory="产品")


def test_delete_entry_is_refused(writer):
    with pytest.raises(KnowledgeWriterReadOnly):
        writer.delete_entry("技术/a.md")


def test_update_document_meta_is_refused(writer):
    with pytest.raises(KnowledgeWriterReadOnly):
        writer.update_document_meta("技术/a.md", {"title": "x"})


def test_reads_still_work(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    rw = KnowledgeWriter(repo, None)
    rw.persist_document("技术/a.md", {"title": "A"}, "正文", commit_msg="init")
    ro = KnowledgeWriter(repo, None, read_only=True)
    assert ro.read_entry_bytes("技术/a.md")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_demo_writer_readonly.py -v`
Expected: FAIL，`TypeError: __init__() got an unexpected keyword argument 'read_only'`

- [ ] **Step 3: 实现**

在 `backend/app/engine/knowledge_writer.py` 的 `class KnowledgeWriter` 之前加异常类：

```python
class KnowledgeWriterReadOnly(RuntimeError):
    """只读部署（如公开演示站）下的写入尝试。"""
```

修改 `__init__`：

```python
    def __init__(
        self,
        repo: KnowledgeRepo,
        indexer: Indexer | None = None,
        *,
        skills_dir: str = "技能",
        read_only: bool = False,
    ):
        self.repo = repo
        self.indexer = indexer
        self.skills_dir = skills_dir.replace("\\", "/").strip("/") or "技能"
        self.read_only = read_only

    def _assert_writable(self) -> None:
        if self.read_only:
            raise KnowledgeWriterReadOnly("当前部署为只读，知识库不可写入")
```

在下列方法体的第一行各加一句 `self._assert_writable()`：`persist_document`、`update_document_meta`、`import_entry`、`move_entry`、`delete_entry`。

在 `backend/app/deps.py:129-131` 改为：

```python
    knowledge_writer = KnowledgeWriter(
        repo,
        index.indexer,
        skills_dir=settings.skills_dir,
        read_only=bool(settings.demo_mode),
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_demo_writer_readonly.py -v`
Expected: 6 passed

- [ ] **Step 5: 确认没有回归**

Run: `cd backend && python -m pytest -q`
Expected: 全部 passed

- [ ] **Step 6: 提交**

```bash
git add backend/app/engine/knowledge_writer.py backend/app/deps.py backend/tests/test_demo_writer_readonly.py
git commit -m "feat(demo): KnowledgeWriter 只读断言兜底"
```

---

## Task 10: demo 环境契约系统提示

**Files:**
- Modify: `backend/app/engine/agent/prompts.py`
- Modify: `backend/app/engine/agent/message_builder.py`
- Modify: `backend/app/engine/agent/orchestrator.py:83-95`
- Test: `backend/tests/test_demo_prompt.py`

**Interfaces:**
- Produces:
  - `DEMO_ENVIRONMENT_CONTRACT: str`（`prompts.py`）
  - `build_agent_messages(..., demo_mode: bool = False)`

**写法约束（项目规范 §0）：** 这一段写的是**环境契约**——当前部署是公开只读演示、写类工具只产出预览、对话不会被保存。不写「禁止说已保存」这类针对话术的补丁。工具返回值里的 `preview_only` 与 `_NOT_PERSISTED` 才是确定性保证，提示词只负责让模型理解处境。

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_demo_prompt.py`：

```python
from app.engine.agent.message_builder import build_agent_messages
from app.engine.agent.prompts import DEMO_ENVIRONMENT_CONTRACT, MODE_DEFAULT


def _system_text(messages):
    return "\n".join(m["content"] for m in messages if m.get("role") == "system")


def test_demo_contract_present_when_demo():
    messages = build_agent_messages("你好", mode=MODE_DEFAULT, demo_mode=True)
    assert DEMO_ENVIRONMENT_CONTRACT in _system_text(messages)


def test_demo_contract_absent_by_default():
    messages = build_agent_messages("你好", mode=MODE_DEFAULT)
    assert DEMO_ENVIRONMENT_CONTRACT not in _system_text(messages)


def test_contract_states_environment_not_phrasing_rules():
    """写环境契约，不写话术黑名单——后者只能挡住原句。"""
    assert "演示" in DEMO_ENVIRONMENT_CONTRACT
    assert "预览" in DEMO_ENVIRONMENT_CONTRACT
    assert "不会被保存" in DEMO_ENVIRONMENT_CONTRACT
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_demo_prompt.py -v`
Expected: FAIL，`ImportError: cannot import name 'DEMO_ENVIRONMENT_CONTRACT'`

- [ ] **Step 3: 实现**

在 `backend/app/engine/agent/prompts.py` 末尾加：

```python
DEMO_ENVIRONMENT_CONTRACT = (
    "[运行环境] 当前是公开演示环境。知识库与长期记忆为只读；"
    "写类工具只产出预览，不会真正落盘；本次对话不会被保存。"
    "正常按用户意图使用工具，并如实说明预览与真实写入的区别。"
)
```

在 `backend/app/engine/agent/message_builder.py` 的 `build_agent_messages` 签名里加 `demo_mode: bool = False`，并在拼装 system 消息的位置（紧随基础 SYSTEM_PROMPT 之后）加入：

```python
    if demo_mode:
        system_parts.append(DEMO_ENVIRONMENT_CONTRACT)
```

（`system_parts` 为该函数内既有的 system 段落列表；若变量名不同，按现有实现追加到同一列表。同时在该文件导入 `DEMO_ENVIRONMENT_CONTRACT`。）

在 `backend/app/engine/agent/orchestrator.py` 的 `build_agent_messages(...)` 调用里补：

```python
            attachments=attachments,
            demo_mode=bool(getattr(self.settings, "demo_mode", False)),
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_demo_prompt.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/engine/agent backend/tests/test_demo_prompt.py
git commit -m "feat(demo): 注入演示环境契约系统提示"
```

---

## Task 11: 从预置会话追问（ephemeral_from）

**Files:**
- Modify: `backend/app/api/http_deps.py:54-66`
- Modify: `backend/app/api/chat_routes.py:54-86`
- Modify: `backend/app/engine/chat/session_runner.py:82-106`
- Test: `backend/tests/test_demo_ephemeral_from.py`

**Interfaces:**
- Consumes: `ConversationStore.llm_history(conv)`（`turn_hub.py:237` 同款用法）
- Produces:
  - `ChatBody.ephemeral_from: str | None = None`
  - `ChatSessionRunner.stream_ephemeral(..., history: list[dict] | None = None)`

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_demo_ephemeral_from.py`：

```python
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models.llm import FakeLLMClient


@pytest.fixture
def demo_app(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge", demo_mode=True)
    llm = FakeLLMClient(chat_responses=["演示回答"] * 40, embed_dim=8)
    return create_app(settings=settings, llm=llm)


@pytest.fixture
def seeded_cid(demo_app):
    with TestClient(demo_app) as admin:
        sid = demo_app.state.session_store.create()
        admin.cookies.set("lorechat_session", sid)
        cid = admin.post("/api/conversations", json={"title": "选型"}).json()["id"]
        admin.post(f"/api/conversations/{cid}/messages", json={"role": "user", "text": "向量库怎么选"})
        return cid


def test_ephemeral_from_streams(demo_app, seeded_cid):
    with TestClient(demo_app) as guest:
        guest.post("/api/auth/guest")
        r = guest.post("/api/chat", json={"text": "为什么", "ephemeral_from": seeded_cid})
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")


def test_ephemeral_from_does_not_grow_source_conversation(demo_app, seeded_cid):
    with TestClient(demo_app) as guest:
        guest.post("/api/auth/guest")
        before = len(guest.get(f"/api/conversations/{seeded_cid}").json()["messages"])
        guest.post("/api/chat", json={"text": "为什么", "ephemeral_from": seeded_cid})
        after = len(guest.get(f"/api/conversations/{seeded_cid}").json()["messages"])
        assert after == before


def test_ephemeral_from_unknown_conversation_is_404(demo_app):
    with TestClient(demo_app) as guest:
        guest.post("/api/auth/guest")
        r = guest.post("/api/chat", json={"text": "hi", "ephemeral_from": "missing"})
        assert r.status_code == 404
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_demo_ephemeral_from.py -v`
Expected: FAIL，`ephemeral_from` 被 pydantic 忽略，第二、三条断言不成立

- [ ] **Step 3: 实现 — 请求体**

在 `backend/app/api/http_deps.py` 的 `ChatBody` 里，`reuse_user_message_id` 之后加：

```python
    # 演示站：带上某个已有会话的上下文提问，但不写入该会话
    ephemeral_from: str | None = None
```

- [ ] **Step 4: 实现 — runner**

在 `backend/app/engine/chat/session_runner.py` 的 `stream_ephemeral` 签名末尾加：

```python
        history: list[dict] | None = None,
```

并把 `agent.run(...)` 里的 `history=None` 改为 `history=history`。

- [ ] **Step 5: 实现 — 路由**

在 `backend/app/api/chat_routes.py` 的 `chat()` 中，把「无 conversation_id 走 ephemeral」的分支改为：

```python
    if not body.conversation_id:
        history = None
        if body.ephemeral_from:
            try:
                source = c.conversations.get(body.ephemeral_from)
            except KeyError as e:
                raise HTTPException(404, "对话不存在") from e
            history = c.conversations.llm_history(source)
        return StreamingResponse(
            with_sse_keepalive(
                c.chat_runner.stream_ephemeral(
                    body.text,
                    doc_paths=paths,
                    skill_catalog=skill_catalog,
                    primary_doc=primary,
                    web_enabled=body.web_enabled,
                    history=history,
                )
            ),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_demo_ephemeral_from.py -v`
Expected: 3 passed

- [ ] **Step 7: 提交**

```bash
git add backend/app/api backend/app/engine/chat/session_runner.py backend/tests/test_demo_ephemeral_from.py
git commit -m "feat(demo): 支持从预置会话分叉临时提问"
```

---

## Task 12: 访客限流

**Files:**
- Create: `backend/app/demo/quota.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/chat_routes.py`
- Test: `backend/tests/test_demo_quota.py`

**Interfaces:**
- Produces:
  - `DemoQuota(per_session: int = 20, per_ip_hourly: int = 60, daily_total: int = 2000, max_concurrent: int = 10)`
  - `.acquire(session_id: str, ip: str | None) -> None`，超限抛 `DemoQuotaExceeded(code, message)`
  - `.release() -> None`
  - `DemoQuotaExceeded.code ∈ {"demo_quota_exceeded", "demo_busy"}`

- [ ] **Step 1: 写失败的测试**

创建 `backend/tests/test_demo_quota.py`：

```python
import pytest

from app.demo.quota import DemoQuota, DemoQuotaExceeded


def test_allows_within_session_limit():
    q = DemoQuota(per_session=2)
    q.acquire("s1", "1.1.1.1"); q.release()
    q.acquire("s1", "1.1.1.1"); q.release()


def test_blocks_over_session_limit():
    q = DemoQuota(per_session=1)
    q.acquire("s1", "1.1.1.1"); q.release()
    with pytest.raises(DemoQuotaExceeded) as e:
        q.acquire("s1", "1.1.1.1")
    assert e.value.code == "demo_quota_exceeded"


def test_session_limit_is_per_session():
    q = DemoQuota(per_session=1)
    q.acquire("s1", "1.1.1.1"); q.release()
    q.acquire("s2", "1.1.1.1"); q.release()


def test_blocks_over_ip_hourly_limit():
    q = DemoQuota(per_session=100, per_ip_hourly=1)
    q.acquire("s1", "1.1.1.1"); q.release()
    with pytest.raises(DemoQuotaExceeded) as e:
        q.acquire("s2", "1.1.1.1")
    assert e.value.code == "demo_quota_exceeded"


def test_blocks_over_daily_total():
    q = DemoQuota(per_session=100, per_ip_hourly=100, daily_total=1)
    q.acquire("s1", "1.1.1.1"); q.release()
    with pytest.raises(DemoQuotaExceeded):
        q.acquire("s2", "2.2.2.2")


def test_blocks_over_concurrency_without_release():
    q = DemoQuota(per_session=100, per_ip_hourly=100, max_concurrent=1)
    q.acquire("s1", "1.1.1.1")
    with pytest.raises(DemoQuotaExceeded) as e:
        q.acquire("s2", "2.2.2.2")
    assert e.value.code == "demo_busy"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_demo_quota.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.demo.quota'`

- [ ] **Step 3: 实现**

创建 `backend/app/demo/quota.py`：

```python
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_HOUR = 3600.0
_DAY = 86400.0


class DemoQuotaExceeded(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DemoQuota:
    """演示站成本闸门：全部计数在进程内，重启即清零。"""

    def __init__(
        self,
        per_session: int = 20,
        per_ip_hourly: int = 60,
        daily_total: int = 2000,
        max_concurrent: int = 10,
    ) -> None:
        self._per_session = per_session
        self._per_ip_hourly = per_ip_hourly
        self._daily_total = daily_total
        self._max_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._session_counts: dict[str, int] = defaultdict(int)
        self._ip_hits: dict[str, deque[float]] = defaultdict(deque)
        self._day_hits: deque[float] = deque()
        self._in_flight = 0

    def acquire(self, session_id: str, ip: str | None) -> None:
        now = time.monotonic()
        with self._lock:
            if self._in_flight >= self._max_concurrent:
                raise DemoQuotaExceeded("demo_busy", "演示站正忙，请稍后再试")
            if self._session_counts[session_id] >= self._per_session:
                raise DemoQuotaExceeded(
                    "demo_quota_exceeded", "本次演示的提问额度已用完"
                )
            if ip:
                hits = self._ip_hits[ip]
                while hits and now - hits[0] > _HOUR:
                    hits.popleft()
                if len(hits) >= self._per_ip_hourly:
                    raise DemoQuotaExceeded(
                        "demo_quota_exceeded", "本小时的提问额度已用完"
                    )
            while self._day_hits and now - self._day_hits[0] > _DAY:
                self._day_hits.popleft()
            if len(self._day_hits) >= self._daily_total:
                raise DemoQuotaExceeded(
                    "demo_quota_exceeded", "今天的演示额度已用完"
                )

            self._session_counts[session_id] += 1
            if ip:
                self._ip_hits[ip].append(now)
            self._day_hits.append(now)
            self._in_flight += 1

    def release(self) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
```

在 `backend/app/main.py` 的 `app.state.guest_sessions = GuestSessionStore()` 之后加：

```python
    app.state.demo_quota = DemoQuota()
```

并导入 `from app.demo.quota import DemoQuota`。

- [ ] **Step 4: 接进 chat 路由**

在 `backend/app/api/chat_routes.py` 导入区加：

```python
from app.auth.routes import GUEST_COOKIE
from app.demo.quota import DemoQuotaExceeded
```

在 Task 6 插入的 guest 断言之后追加：

```python
    if is_guest:
        quota = request.app.state.demo_quota
        guest_sid = request.cookies.get(GUEST_COOKIE) or ""
        client = request.client
        try:
            quota.acquire(guest_sid, client.host if client else None)
        except DemoQuotaExceeded as e:
            raise HTTPException(
                429 if e.code == "demo_busy" else 403,
                detail={"code": e.code, "detail": e.message},
            ) from e
```

并把 ephemeral 分支的 `StreamingResponse` 包一层释放逻辑——在 `stream_ephemeral(...)` 外面套一个生成器：

```python
        stream = c.chat_runner.stream_ephemeral(
            body.text,
            doc_paths=paths,
            skill_catalog=skill_catalog,
            primary_doc=primary,
            web_enabled=body.web_enabled,
            history=history,
        )
        if is_guest:
            quota = request.app.state.demo_quota

            async def _released():
                try:
                    async for ev in stream:
                        yield ev
                finally:
                    quota.release()

            stream = _released()
        return StreamingResponse(
            with_sse_keepalive(stream),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )
```

- [ ] **Step 5: 输入长度上限与工具调用预算**

spec §8 还有两条闸门与计数无关，一并在这里落。

在 `backend/app/demo/quota.py` 顶部加常量：

```python
GUEST_MAX_INPUT_CHARS = 2000
GUEST_MAX_TOOL_CALLS = 10
```

在 `backend/app/api/chat_routes.py` 的 guest 分支里，`quota.acquire(...)` 之前加：

```python
        if len(body.text or "") > GUEST_MAX_INPUT_CHARS:
            raise HTTPException(
                400,
                detail={
                    "code": "demo_input_too_long",
                    "detail": f"演示环境单条提问不超过 {GUEST_MAX_INPUT_CHARS} 字",
                },
            )
```

并把导入补成 `from app.demo.quota import GUEST_MAX_INPUT_CHARS, DemoQuotaExceeded`。

工具调用预算落在 orchestrator 侧——在 `backend/app/engine/agent/tool_loop.py` 读取 `settings.agent_max_tool_calls` 的位置改为取较小值：

```python
        max_tool_calls = self.settings.agent_max_tool_calls
        if getattr(self.settings, "demo_mode", False):
            from app.demo.quota import GUEST_MAX_TOOL_CALLS

            max_tool_calls = min(max_tool_calls, GUEST_MAX_TOOL_CALLS)
```

（变量名按该文件现有实现对齐；关键是 demo 下取 `min`，而不是直接覆盖用户配置。）

- [ ] **Step 6: 端到端断言**

在 `backend/tests/test_demo_chat.py` 末尾追加：

```python
def test_guest_hits_session_quota(demo_app, guest):
    demo_app.state.demo_quota._per_session = 1
    assert guest.post("/api/chat", json={"text": "一"}).status_code == 200
    r = guest.post("/api/chat", json={"text": "二"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "demo_quota_exceeded"


def test_guest_input_length_is_capped(guest):
    r = guest.post("/api/chat", json={"text": "长" * 2001})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "demo_input_too_long"


def test_demo_lowers_tool_call_budget(tmp_path):
    from app.config import Settings
    from app.deps import build_container
    from app.demo.quota import GUEST_MAX_TOOL_CALLS
    from app.models.llm import FakeLLMClient

    settings = Settings(kb_path=tmp_path / "kb", demo_mode=True, agent_max_tool_calls=25)
    container = build_container(
        settings, llm=FakeLLMClient(chat_responses=["x"], embed_dim=8)
    )
    assert container.agent._tool_loop.resolve_max_tool_calls() <= GUEST_MAX_TOOL_CALLS
```

若 `tool_loop` 里没有可直接调用的取值方法，把上面这条改为把该逻辑抽成模块级纯函数 `resolve_max_tool_calls(settings) -> int` 并直接测它——**不要**为了测试去断言私有属性。

- [ ] **Step 7: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_demo_quota.py tests/test_demo_chat.py -v`
Expected: 全部 passed

- [ ] **Step 8: 提交**

```bash
git add backend/app/demo/quota.py backend/app/main.py backend/app/api/chat_routes.py backend/app/engine/agent/tool_loop.py backend/tests/test_demo_quota.py backend/tests/test_demo_chat.py
git commit -m "feat(demo): 访客提问限流、输入长度与工具预算闸门"
```

---

## Task 13: 前端 demo 能力判定与免登录进入

**Files:**
- Modify: `frontend/src/api.ts:25-32`
- Create: `frontend/src/hooks/useDemoCapability.ts`
- Create: `frontend/src/hooks/useDemoCapability.test.ts`
- Modify: `frontend/src/App.tsx:1-51`

**Interfaces:**
- Produces:
  - `AuthStatus` 增加 `demo: boolean`、`role: "admin" | "guest" | "none"`
  - `postGuestSession(): Promise<{ ok: boolean; role: string }>`
  - `DemoCapability = { isDemo: boolean; role: string; canWrite: boolean; canPersistChat: boolean }`
  - `resolveDemoCapability(status: AuthStatus): DemoCapability`（纯函数，便于测试）
  - `useDemoCapability(): DemoCapability`

- [ ] **Step 1: 写失败的测试**

创建 `frontend/src/hooks/useDemoCapability.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import { resolveDemoCapability } from "./useDemoCapability";

describe("resolveDemoCapability", () => {
  it("访客只读且对话不落库", () => {
    const cap = resolveDemoCapability({
      setup_required: false,
      authenticated: false,
      demo: true,
      role: "guest",
    });
    expect(cap.isDemo).toBe(true);
    expect(cap.canWrite).toBe(false);
    expect(cap.canPersistChat).toBe(false);
  });

  it("demo 站的管理员不受限", () => {
    const cap = resolveDemoCapability({
      setup_required: false,
      authenticated: true,
      demo: true,
      role: "admin",
    });
    expect(cap.canWrite).toBe(true);
    expect(cap.canPersistChat).toBe(true);
  });

  it("非 demo 部署一切照旧", () => {
    const cap = resolveDemoCapability({
      setup_required: false,
      authenticated: true,
      demo: false,
      role: "admin",
    });
    expect(cap.isDemo).toBe(false);
    expect(cap.canWrite).toBe(true);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/hooks/useDemoCapability.test.ts`
Expected: FAIL，`Failed to resolve import "./useDemoCapability"`

- [ ] **Step 3: 实现 api 层**

在 `frontend/src/api.ts` 里把 `AuthStatus` 改为：

```ts
export type AuthStatus = {
  setup_required: boolean;
  authenticated: boolean;
  demo: boolean;
  role: "admin" | "guest" | "none";
};
```

并在 `getAuthStatus` 之后加：

```ts
export function postGuestSession() {
  return apiFetch<{ ok: boolean; role: string }>("/api/auth/guest", {
    method: "POST",
  });
}
```

- [ ] **Step 4: 实现 hook**

创建 `frontend/src/hooks/useDemoCapability.ts`：

```ts
import { createContext, useContext } from "react";
import type { AuthStatus } from "../api";

export type DemoCapability = {
  isDemo: boolean;
  role: AuthStatus["role"];
  canWrite: boolean;
  canPersistChat: boolean;
};

export const DEFAULT_CAPABILITY: DemoCapability = {
  isDemo: false,
  role: "admin",
  canWrite: true,
  canPersistChat: true,
};

export function resolveDemoCapability(status: AuthStatus): DemoCapability {
  const isGuest = status.demo && status.role === "guest";
  return {
    isDemo: status.demo,
    role: status.role,
    canWrite: !isGuest,
    canPersistChat: !isGuest,
  };
}

export const DemoCapabilityContext =
  createContext<DemoCapability>(DEFAULT_CAPABILITY);

export function useDemoCapability(): DemoCapability {
  return useContext(DemoCapabilityContext);
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/hooks/useDemoCapability.test.ts`
Expected: 3 passed

- [ ] **Step 6: 接进 App 门禁**

在 `frontend/src/App.tsx` 里，把 `useEffect` 中的门禁判定改为：

```tsx
  const [capability, setCapability] = useState<DemoCapability>(DEFAULT_CAPABILITY);

  useEffect(() => {
    getAuthStatus()
      .then(async (s) => {
        if (s.demo && s.role !== "admin") {
          const issued = s.role === "guest" ? s : { ...s, role: "guest" as const };
          if (s.role !== "guest") await postGuestSession();
          setCapability(resolveDemoCapability(issued));
          setGate("app");
          return;
        }
        setCapability(resolveDemoCapability(s));
        if (s.setup_required) setGate("setup");
        else if (!s.authenticated) setGate("login");
        else setGate("app");
      })
      .catch(() => setGate("login"));
  }, []);
```

并把返回的 `<AppMain />` 包进 Provider：

```tsx
  return (
    <DemoCapabilityContext.Provider value={capability}>
      <AppMain />
    </DemoCapabilityContext.Provider>
  );
```

补上导入：

```tsx
import { getAuthStatus, postGuestSession, type SourceRef, type SettingsAttention } from "./api";
import {
  DEFAULT_CAPABILITY,
  DemoCapabilityContext,
  resolveDemoCapability,
  type DemoCapability,
} from "./hooks/useDemoCapability";
```

- [ ] **Step 7: 类型检查与构建**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: 无类型错误，测试全部通过

- [ ] **Step 8: 提交**

```bash
git add frontend/src/api.ts frontend/src/App.tsx frontend/src/hooks/useDemoCapability.ts frontend/src/hooks/useDemoCapability.test.ts
git commit -m "feat(demo): 前端能力判定与访客免登录进入"
```

---

## Task 14: 前端只读 UI 与 403 兜底

**Files:**
- Create: `frontend/src/components/demo/DemoBanner.tsx`
- Modify: `frontend/src/lib/httpTransport.ts`
- Modify: `frontend/src/components/app/AppShell.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/components/doc/DocViewerHeader.tsx`
- Modify: `frontend/src/components/memory/MemoryPanel.tsx`
- Modify: `frontend/src/components/settings/SettingsPanel.tsx`
- Test: `frontend/src/lib/demoReadOnlyError.test.ts`

**Interfaces:**
- Consumes: `useDemoCapability()`（Task 13）
- Produces:
  - `isDemoReadOnlyError(body: unknown): boolean`（`frontend/src/lib/httpTransport.ts` 导出）
  - `window` 事件 `"demo:read-only"`

- [ ] **Step 1: 写失败的测试**

创建 `frontend/src/lib/demoReadOnlyError.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import { isDemoReadOnlyError } from "./httpTransport";

describe("isDemoReadOnlyError", () => {
  it("识别顶层 code", () => {
    expect(isDemoReadOnlyError({ code: "demo_read_only" })).toBe(true);
  });

  it("识别 FastAPI detail 包裹的 code", () => {
    expect(isDemoReadOnlyError({ detail: { code: "demo_read_only" } })).toBe(true);
  });

  it("其他错误不误判", () => {
    expect(isDemoReadOnlyError({ code: "auth_required" })).toBe(false);
    expect(isDemoReadOnlyError(null)).toBe(false);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/lib/demoReadOnlyError.test.ts`
Expected: FAIL，`isDemoReadOnlyError is not a function`

- [ ] **Step 3: 实现错误识别与全局事件**

在 `frontend/src/lib/httpTransport.ts` 加导出：

```ts
export function isDemoReadOnlyError(body: unknown): boolean {
  if (!body || typeof body !== "object") return false;
  const record = body as Record<string, unknown>;
  if (record.code === "demo_read_only") return true;
  const detail = record.detail;
  return (
    !!detail &&
    typeof detail === "object" &&
    (detail as Record<string, unknown>).code === "demo_read_only"
  );
}
```

在该文件处理非 2xx 响应的位置（与现有 `auth:unauthorized` 派发相邻处）加：

```ts
    if (response.status === 403 && isDemoReadOnlyError(parsedBody)) {
      window.dispatchEvent(new CustomEvent("demo:read-only"));
    }
```

- [ ] **Step 4: 实现演示条**

创建 `frontend/src/components/demo/DemoBanner.tsx`：

```tsx
import { useEffect, useState } from "react";
import { useDemoCapability } from "../../hooks/useDemoCapability";

const TOAST_MS = 2600;

export function DemoBanner() {
  const { isDemo, canWrite } = useDemoCapability();
  const [toast, setToast] = useState(false);

  useEffect(() => {
    const onBlocked = () => {
      setToast(true);
      const timer = window.setTimeout(() => setToast(false), TOAST_MS);
      return () => window.clearTimeout(timer);
    };
    window.addEventListener("demo:read-only", onBlocked);
    return () => window.removeEventListener("demo:read-only", onBlocked);
  }, []);

  if (!isDemo || canWrite) return null;

  return (
    <>
      <div className="demo-banner" role="status">
        <span>演示环境 · 只读 · 对话不会被保存</span>
        <a href="https://github.com/cnwinds/lore-chat" target="_blank" rel="noreferrer">
          部署你自己的 Lore
        </a>
      </div>
      {toast && <div className="demo-toast">演示环境不可修改</div>}
    </>
  );
}
```

在 `frontend/src/index.css` 末尾加对应样式（`.demo-banner` 固定在顶部、`.demo-toast` 居中浮层）。

在 `frontend/src/components/app/AppShell.tsx` 的最外层容器内、其余内容之前渲染 `<DemoBanner />`。

- [ ] **Step 5: 关闭写入口**

在下列组件里用 `const { canWrite } = useDemoCapability();` 后按能力隐藏或禁用：

- `Sidebar.tsx`：新建目录/文档、上传、拖拽移动、右键菜单中的写项
- `DocViewerHeader.tsx`：编辑、保存、元数据编辑
- `MemoryPanel.tsx`：确认 / 拒绝 / 编辑 / 遗忘
- `SettingsPanel.tsx`：全部保存按钮、改密、导入导出、重建索引、清冷却

统一写法（不要在各处散写 `if (demo)`，一律经 `canWrite`）：

```tsx
{canWrite && <button onClick={onSave}>保存</button>}
```

- [ ] **Step 6: 运行测试与类型检查**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: 无类型错误，测试全部通过

- [ ] **Step 7: 手工验收**

启动 `DEMO_MODE=1` 的后端与前端，确认：访客进入无需登录；侧栏无新建/上传入口；文档无编辑按钮；记忆面板只读；设置页无保存按钮；用浏览器控制台手动 `fetch("/api/doc", {method:"PUT", ...})` 会弹出「演示环境不可修改」。

- [ ] **Step 8: 提交**

```bash
git add frontend/src
git commit -m "feat(demo): 演示条、只读 UI 与 403 全局兜底"
```

---

## Task 15: 预览卡渲染

**Files:**
- Create: `frontend/src/components/demo/DemoPreviewCard.tsx`
- Modify: `frontend/src/utils/agentStreamProjection.ts`
- Modify: `frontend/src/components/TimelineBlockView.tsx`
- Test: `frontend/src/components/demo/demoPreview.test.ts`

**Interfaces:**
- Consumes: 工具结果 `{"status": "preview_only", "preview": {kind, path, content, ...}}`（Task 8）
- Produces:
  - `DemoPreview = { kind: "doc" | "doc_edit" | "doc_meta" | "memory"; path?: string; content?: string; action?: string }`
  - `extractDemoPreview(toolResult: unknown): DemoPreview | null`

- [ ] **Step 1: 写失败的测试**

创建 `frontend/src/components/demo/demoPreview.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import { extractDemoPreview } from "./DemoPreviewCard";

describe("extractDemoPreview", () => {
  it("提取文档预览", () => {
    const preview = extractDemoPreview({
      status: "preview_only",
      preview: { kind: "doc", path: "技术/检索/选型.md", content: "# 选型" },
    });
    expect(preview).toEqual({
      kind: "doc",
      path: "技术/检索/选型.md",
      content: "# 选型",
    });
  });

  it("提取记忆预览", () => {
    const preview = extractDemoPreview({
      status: "preview_only",
      preview: { kind: "memory", action: "remember", content: "偏好结论先行" },
    });
    expect(preview?.kind).toBe("memory");
    expect(preview?.content).toBe("偏好结论先行");
  });

  it("非预览结果返回 null", () => {
    expect(extractDemoPreview({ status: "ok", summary: "已写入" })).toBeNull();
    expect(extractDemoPreview(null)).toBeNull();
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/components/demo/demoPreview.test.ts`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现**

创建 `frontend/src/components/demo/DemoPreviewCard.tsx`：

```tsx
import { MarkdownContent } from "../MarkdownContent";

export type DemoPreview = {
  kind: "doc" | "doc_edit" | "doc_meta" | "memory";
  path?: string;
  content?: string;
  action?: string;
};

export function extractDemoPreview(toolResult: unknown): DemoPreview | null {
  if (!toolResult || typeof toolResult !== "object") return null;
  const record = toolResult as Record<string, unknown>;
  if (record.status !== "preview_only") return null;
  const preview = record.preview;
  if (!preview || typeof preview !== "object") return null;
  const p = preview as Record<string, unknown>;
  return {
    kind: p.kind as DemoPreview["kind"],
    path: typeof p.path === "string" ? p.path : undefined,
    content: typeof p.content === "string" ? p.content : undefined,
    action: typeof p.action === "string" ? p.action : undefined,
  };
}

const TITLES: Record<DemoPreview["kind"], string> = {
  doc: "将写入",
  doc_edit: "将局部编辑",
  doc_meta: "将更新元数据",
  memory: "将记住",
};

export function DemoPreviewCard({ preview }: { preview: DemoPreview }) {
  return (
    <div className="demo-preview-card">
      <div className="demo-preview-card__head">
        <strong>{TITLES[preview.kind]}</strong>
        {preview.path && <code>{preview.path}</code>}
        <span className="demo-preview-card__badge">演示环境 · 未落盘</span>
      </div>
      {preview.content && (
        <div className="demo-preview-card__body">
          <MarkdownContent text={preview.content} />
        </div>
      )}
    </div>
  );
}
```

在 `frontend/src/index.css` 加 `.demo-preview-card` 相关样式（带边框与浅色底，`__badge` 用弱化色）。

在 `frontend/src/components/TimelineBlockView.tsx` 渲染工具块的分支里，先尝试 `extractDemoPreview(block.result)`，命中则渲染 `<DemoPreviewCard preview={preview} />` 而不是默认的工具结果摘要。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/components/demo/demoPreview.test.ts`
Expected: 3 passed

- [ ] **Step 5: 类型检查与全量测试**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: 无类型错误，测试全部通过

- [ ] **Step 6: 手工验收**

在 `DEMO_MODE=1` 的实例上对访客身份说「帮我把刚才这段整理进知识库」，确认：时间线出现「将写入 …」预览卡、卡内是完整 Markdown、带「未落盘」徽标、知识库树中**没有**新增文件、模型回复中没有宣称已保存。

- [ ] **Step 7: 提交**

```bash
git add frontend/src
git commit -m "feat(demo): 时间线渲染写入预览卡"
```

---

## Task 16: 首访引导与虚构声明

**Files:**
- Create: `frontend/src/components/demo/DemoTour.tsx`
- Create: `frontend/src/components/demo/demoTour.ts`
- Create: `frontend/src/components/demo/demoTour.test.ts`
- Modify: `frontend/src/components/app/AppShell.tsx`
- Modify: `frontend/src/components/demo/DemoBanner.tsx`

**Interfaces:**
- Consumes: `useDemoCapability()`（Task 13）、`manifest.highlight_conversation`（内容线 Task 6 填入，前端经 `GET /api/conversations` 列表首项兜底）
- Produces:
  - `TOUR_STEPS: readonly TourStep[]`，`TourStep = { id: string; title: string; body: string; anchor: string }`
  - `shouldShowTour(isGuest: boolean, seen: string | null): boolean`
  - `TOUR_SEEN_KEY = "lore.demo.tourSeen"`

**为什么需要：** spec §9.2 要求三步引导指向知识库树、高光会话、输入框。访客的注意力只有几十秒，没有引导就只会看到一个空聊天框，前面所有内容投入都白费。

- [ ] **Step 1: 写失败的测试**

创建 `frontend/src/components/demo/demoTour.test.ts`：

```ts
import { describe, expect, it } from "vitest";
import { shouldShowTour, TOUR_STEPS } from "./demoTour";

describe("demo tour", () => {
  it("三步，分别指向目录树、高光会话、输入框", () => {
    expect(TOUR_STEPS).toHaveLength(3);
    expect(TOUR_STEPS.map((s) => s.anchor)).toEqual([
      "kb-tree",
      "highlight-conversation",
      "composer",
    ]);
  });

  it("每步都有标题与正文", () => {
    for (const step of TOUR_STEPS) {
      expect(step.title.trim()).not.toBe("");
      expect(step.body.trim()).not.toBe("");
    }
  });

  it("访客首访才展示", () => {
    expect(shouldShowTour(true, null)).toBe(true);
    expect(shouldShowTour(true, "1")).toBe(false);
    expect(shouldShowTour(false, null)).toBe(false);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/components/demo/demoTour.test.ts`
Expected: FAIL，模块不存在

- [ ] **Step 3: 实现引导数据**

创建 `frontend/src/components/demo/demoTour.ts`：

```ts
export type TourStep = {
  id: string;
  title: string;
  body: string;
  anchor: string;
};

export const TOUR_SEEN_KEY = "lore.demo.tourSeen";

export const TOUR_STEPS: readonly TourStep[] = [
  {
    id: "tree",
    title: "这是聊出来的知识库",
    body: "左侧目录不是手工维护的。每一篇都来自一次真实对话，AI 判断该新建还是归入已有目录。",
    anchor: "kb-tree",
  },
  {
    id: "conversation",
    title: "点开看一次沉淀的全过程",
    body: "这条会话里，Lore 搜了网、比对了来源，最后把结论写成了知识库里的一篇笔记——都能展开看。",
    anchor: "highlight-conversation",
  },
  {
    id: "composer",
    title: "直接问它",
    body: "可以基于这份知识库提问。演示环境的对话不会被保存，放心试。",
    anchor: "composer",
  },
];

export function shouldShowTour(isGuest: boolean, seen: string | null): boolean {
  return isGuest && !seen;
}
```

- [ ] **Step 4: 实现引导组件**

创建 `frontend/src/components/demo/DemoTour.tsx`：逐步高亮 `data-demo-anchor={step.anchor}` 的元素，底部有「下一步 / 跳过」，走完或跳过时写 `localStorage.setItem(TOUR_SEEN_KEY, "1")`。仅当 `shouldShowTour(!canWrite && isDemo, localStorage.getItem(TOUR_SEEN_KEY))` 为真时渲染。

给三个锚点元素加属性：

- `frontend/src/components/Sidebar.tsx` 的目录树容器：`data-demo-anchor="kb-tree"`
- `frontend/src/components/Sidebar.tsx` 的会话列表首项（或 manifest 指定的高光会话行）：`data-demo-anchor="highlight-conversation"`
- `frontend/src/components/chat/ChatInputBar.tsx` 的输入框容器：`data-demo-anchor="composer"`

在 `frontend/src/components/app/AppShell.tsx` 中 `<DemoBanner />` 之后渲染 `<DemoTour />`。

- [ ] **Step 5: 加虚构声明**

在 `frontend/src/components/demo/DemoBanner.tsx` 的返回值里，演示条之后追加一行页脚：

```tsx
      <div className="demo-disclaimer">演示内容为虚构示例，人物与机构均非真实。</div>
```

并在 `frontend/src/index.css` 加 `.demo-disclaimer` 样式（弱化色、小字号、固定在视口底部）。

- [ ] **Step 6: 运行测试与类型检查**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: 全部通过

- [ ] **Step 7: 手工验收**

清掉 `localStorage` 后以访客身份进入，确认三步引导依次高亮目录树、高光会话、输入框；跳过后刷新不再出现；页脚能看到虚构声明。

- [ ] **Step 8: 提交**

```bash
git add frontend/src
git commit -m "feat(demo): 访客首访三步引导与虚构内容声明"
```

---

## Task 17: 全量回归与部署开关文档

**Files:**
- Modify: `backend/.env.example`
- Modify: `README.md`
- Test: 全量

- [ ] **Step 1: 跑全量测试**

Run: `cd backend && python -m pytest -q`
Expected: 全部 passed

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: 全部 passed

- [ ] **Step 2: 补环境变量样例**

在 `backend/.env.example` 末尾加：

```
# 公开演示站：访客免登录只读 + 对话不落库。部署级开关，不能在设置页修改
DEMO_MODE=0
```

- [ ] **Step 3: 补 README 一节**

在 `README.md` 的「更多」表格之前加：

```markdown
## 公开演示模式

设置 `DEMO_MODE=1` 后，实例会对匿名访客开放只读体验：可以浏览知识库、预置会话与记忆面板，可以提问（对话不保存），但所有写操作在 HTTP 与 Agent 工具两层都被拒绝。管理员仍可用密码登录取得完整权限。

演示内容的生产与固化见 [`demo/README.md`](demo/README.md)。
```

- [ ] **Step 4: 提交**

```bash
git add backend/.env.example README.md
git commit -m "docs: 说明 DEMO_MODE 部署开关"
```
