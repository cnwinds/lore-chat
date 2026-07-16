# 部署就绪：登录 / 导入导出 / 配置热更新 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Lore Chat 补齐单用户登录门禁、知识库 zip 导出/导入（含覆盖前备份）、以及除 `KB_PATH` 外的配置界面热更新，使实例可安全部署与迁移。

**Architecture:** 应用内一体方案。密码与会话落在 `KB_PATH/.kb/`；运行配置落在 `.kb/settings.json` 并由 `SettingsStore` 热替换客户端；导入导出通过 `backup` 模块打 zip（排除 FTS/向量），覆盖模式先备份到 `KB_PATH` 旁的 `lorechat-backups/`。Auth 中间件拦全部 `/api/*`（白名单除外）。

**Tech Stack:** Python 3.12 / FastAPI / pytest / bcrypt；React 19 + TypeScript + Vite；既有 Docker Compose + Nginx。

**Spec:** [2026-07-16-deploy-auth-backup-settings-design.md](../specs/2026-07-16-deploy-auth-backup-settings-design.md)

## Global Constraints

- 单用户门禁，不做多账号/角色
- `KB_PATH` 不可通过设置 API 修改
- 导出排除 `.kb/index/vec/`、`fts.db`、`conversation_fts.db` 等可重建索引
- 导入模式：`empty_only` | `overwrite`；覆盖前必须自动备份
- 除 `KB_PATH` 外可编辑配置全部热更新（无需重启）
- 所有新 API 需登录（`/api/auth/status|setup|login` 与 `/api/health` 除外）
- TDD：每个任务先写失败测试 → 实现 → 通过 → 提交
- Windows 开发机用 PowerShell；pytest 在 `backend` 目录执行

## 范围说明

本计划按 **Phase A → B → C** 顺序交付，每一 Phase 结束后产品可独立验证。不要并行打乱依赖。

| Phase | 交付 | 可验证结果 |
|-------|------|------------|
| A | 登录门禁 + 健康检查 | 未登录 401；设密/登录后可用；Docker health 不依赖鉴权 |
| B | SettingsStore + 设置 UI | 改 Key/模型立即生效；`KB_PATH` 只读 |
| C | 导出/导入 + 重建索引 | 空库导入、覆盖备份回滚、索引可重建 |

---

## File Structure（将创建 / 修改）

**Backend — 新建**

| 文件 | 职责 |
|------|------|
| `backend/app/auth/__init__.py` | 包导出 |
| `backend/app/auth/passwords.py` | bcrypt 哈希与校验 |
| `backend/app/auth/store.py` | `AuthStore`：读写 `.kb/auth.json` |
| `backend/app/auth/sessions.py` | `SessionStore`：session id ↔ 过期时间 |
| `backend/app/auth/middleware.py` | 鉴权中间件 + 白名单 |
| `backend/app/auth/routes.py` | `/api/auth/*` |
| `backend/app/settings_store.py` | env + `.kb/settings.json` 合并与热更新 |
| `backend/app/backup/__init__.py` | 包 |
| `backend/app/backup/manifest.py` | manifest 读写与 format_version |
| `backend/app/backup/export_kb.py` | 导出 zip |
| `backend/app/backup/import_kb.py` | 空判定、备份、导入、回滚 |
| `backend/app/backup/lock.py` | 维护写锁 |
| `backend/app/backup/reindex.py` | 全量重建文档/会话索引入口 |
| `backend/app/api/admin_routes.py` | `/api/admin/settings|export|import|reindex` |
| `backend/tests/test_auth_*.py` 等 | 见各 Task |

**Backend — 修改**

| 文件 | 变更 |
|------|------|
| `backend/requirements.txt` | 增加 `bcrypt==4.*` |
| `backend/app/main.py` | 挂载 auth/admin 路由；CORS；health；中间件 |
| `backend/app/deps.py` | Container 可挂 `settings_store`；支持 `rebuild_runtime` |
| `backend/app/config.py` | 可选：`session_ttl_days`；明确哪些字段可写入 settings.json |
| `backend/tests/conftest.py` | `client` fixture 自动 setup+登录 |
| `docker-compose.yml` | health → `/api/health`；可选 backups volume |

**Frontend — 新建 / 修改**

| 文件 | 职责 |
|------|------|
| `frontend/src/api.ts` | `credentials: 'include'`；auth/admin API |
| `frontend/src/components/auth/SetupPage.tsx` | 首次设密 |
| `frontend/src/components/auth/LoginPage.tsx` | 登录 |
| `frontend/src/components/settings/SettingsPanel.tsx` | 配置 / 改密 / 导入导出 |
| `frontend/src/App.tsx` | 门禁状态机 |
| `frontend/src/components/Sidebar.tsx` | 设置入口 |
| `frontend/src/styles`（或既有 css） | 门页与设置面板样式，贴合现有主题变量 |

---

# Phase A — 登录门禁

### Task A1: 密码哈希与 AuthStore

**Files:**
- Create: `backend/app/auth/__init__.py`
- Create: `backend/app/auth/passwords.py`
- Create: `backend/app/auth/store.py`
- Test: `backend/tests/test_auth_store.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces:
  - `hash_password(password: str) -> str`
  - `verify_password(password: str, password_hash: str) -> bool`
  - `class AuthStore`:
    - `__init__(self, kb_path: Path)`
    - `is_setup_required(self) -> bool`
    - `set_password(self, password: str) -> None`  # 仅当未设密，否则 raise `AuthAlreadySetupError`
    - `change_password(self, old_password: str, new_password: str) -> None`
    - `verify(self, password: str) -> bool`

- [ ] **Step 1: 添加依赖**

在 `backend/requirements.txt` 追加一行：

```
bcrypt==4.*
```

安装：

```bash
cd backend
pip install "bcrypt==4.*"
```

- [ ] **Step 2: 写失败测试**

```python
# backend/tests/test_auth_store.py
import pytest
from pathlib import Path

from app.auth.passwords import hash_password, verify_password
from app.auth.store import AuthAlreadySetupError, AuthStore


def test_hash_and_verify_roundtrip():
    h = hash_password("secret-pass-1")
    assert h != "secret-pass-1"
    assert verify_password("secret-pass-1", h)
    assert not verify_password("wrong", h)


def test_auth_store_setup_and_verify(tmp_path: Path):
    store = AuthStore(tmp_path)
    assert store.is_setup_required() is True
    store.set_password("admin-pass-123")
    assert store.is_setup_required() is False
    assert (tmp_path / ".kb" / "auth.json").is_file()
    assert store.verify("admin-pass-123")
    assert not store.verify("nope")


def test_auth_store_rejects_second_setup(tmp_path: Path):
    store = AuthStore(tmp_path)
    store.set_password("admin-pass-123")
    with pytest.raises(AuthAlreadySetupError):
        store.set_password("other")


def test_change_password(tmp_path: Path):
    store = AuthStore(tmp_path)
    store.set_password("old-pass-1234")
    store.change_password("old-pass-1234", "new-pass-5678")
    assert store.verify("new-pass-5678")
    assert not store.verify("old-pass-1234")
```

- [ ] **Step 3: 跑测试确认失败**

```bash
cd backend
python -m pytest tests/test_auth_store.py -v
```

Expected: FAIL（`ModuleNotFoundError: app.auth`）

- [ ] **Step 4: 实现**

```python
# backend/app/auth/__init__.py
from app.auth.store import AuthAlreadySetupError, AuthStore

__all__ = ["AuthStore", "AuthAlreadySetupError"]
```

```python
# backend/app/auth/passwords.py
from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("ascii")
        )
    except (ValueError, TypeError):
        return False
```

```python
# backend/app/auth/store.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.auth.passwords import hash_password, verify_password

_MIN_LEN = 8


class AuthAlreadySetupError(Exception):
    pass


class AuthError(Exception):
    pass


class AuthStore:
    def __init__(self, kb_path: Path) -> None:
        self._path = Path(kb_path) / ".kb" / "auth.json"

    def _read(self) -> dict | None:
        if not self._path.is_file():
            return None
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def is_setup_required(self) -> bool:
        data = self._read()
        return not (data and data.get("password_hash"))

    def set_password(self, password: str) -> None:
        if self.is_setup_required() is False:
            raise AuthAlreadySetupError("password already set")
        if len(password) < _MIN_LEN:
            raise AuthError(f"password must be at least {_MIN_LEN} characters")
        self._write(
            {
                "password_hash": hash_password(password),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def verify(self, password: str) -> bool:
        data = self._read()
        if not data or not data.get("password_hash"):
            return False
        return verify_password(password, data["password_hash"])

    def change_password(self, old_password: str, new_password: str) -> None:
        if not self.verify(old_password):
            raise AuthError("old password incorrect")
        if len(new_password) < _MIN_LEN:
            raise AuthError(f"password must be at least {_MIN_LEN} characters")
        self._write(
            {
                "password_hash": hash_password(new_password),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
```

- [ ] **Step 5: 跑测试确认通过**

```bash
cd backend
python -m pytest tests/test_auth_store.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/auth backend/tests/test_auth_store.py
git commit -m "feat(auth): add password hashing and AuthStore"
```

---

### Task A2: SessionStore

**Files:**
- Create: `backend/app/auth/sessions.py`
- Test: `backend/tests/test_auth_sessions.py`

**Interfaces:**
- Produces:
  - `class SessionStore`:
    - `__init__(self, kb_path: Path, ttl_days: int = 7)`
    - `create(self) -> str`  # returns session_id
    - `validate(self, session_id: str | None) -> bool`
    - `revoke(self, session_id: str | None) -> None`
  - 持久化：`{kb_path}/.kb/sessions.json`（`{session_id: {expires_at}}`）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_auth_sessions.py
import time
from pathlib import Path

from app.auth.sessions import SessionStore


def test_create_and_validate(tmp_path: Path):
    store = SessionStore(tmp_path, ttl_days=7)
    sid = store.create()
    assert store.validate(sid) is True
    assert store.validate("nope") is False
    assert store.validate(None) is False


def test_revoke(tmp_path: Path):
    store = SessionStore(tmp_path, ttl_days=7)
    sid = store.create()
    store.revoke(sid)
    assert store.validate(sid) is False


def test_expired_session_invalid(tmp_path: Path, monkeypatch):
    store = SessionStore(tmp_path, ttl_days=0)  # 立即过期：实现用 ttl_seconds 更易测
    # 若实现仅支持天数，可用 monkeypatch 把 now 拨到未来
    sid = store.create()
    # 强制把 expires_at 写到过去
    import json
    path = tmp_path / ".kb" / "sessions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[sid]["expires_at"] = "2000-01-01T00:00:00+00:00"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert store.validate(sid) is False
```

- [ ] **Step 2: 跑失败**

```bash
cd backend
python -m pytest tests/test_auth_sessions.py -v
```

Expected: FAIL（ImportError）

- [ ] **Step 3: 实现 SessionStore**

```python
# backend/app/auth/sessions.py
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path


class SessionStore:
    def __init__(self, kb_path: Path, ttl_days: int = 7) -> None:
        self._path = Path(kb_path) / ".kb" / "sessions.json"
        self._ttl = timedelta(days=ttl_days)

    def _read(self) -> dict:
        if not self._path.is_file():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def create(self) -> str:
        sid = secrets.token_urlsafe(32)
        data = self._read()
        data[sid] = {
            "expires_at": (datetime.now(timezone.utc) + self._ttl).isoformat()
        }
        self._write(data)
        return sid

    def validate(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        data = self._read()
        entry = data.get(session_id)
        if not entry:
            return False
        expires = datetime.fromisoformat(entry["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            data.pop(session_id, None)
            self._write(data)
            return False
        # 滑动过期
        data[session_id] = {
            "expires_at": (datetime.now(timezone.utc) + self._ttl).isoformat()
        }
        self._write(data)
        return True

    def revoke(self, session_id: str | None) -> None:
        if not session_id:
            return
        data = self._read()
        if session_id in data:
            data.pop(session_id)
            self._write(data)
```

- [ ] **Step 4: 跑通过并提交**

```bash
cd backend
python -m pytest tests/test_auth_sessions.py -v
```

```bash
git add backend/app/auth/sessions.py backend/tests/test_auth_sessions.py
git commit -m "feat(auth): add SessionStore with sliding expiry"
```

---

### Task A3: Auth 路由 + 中间件 + health + CORS + conftest 登录

**Files:**
- Create: `backend/app/auth/middleware.py`
- Create: `backend/app/auth/routes.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/deps.py`（Container 增加 `auth_store` / `session_store`，或在 lifespan 挂到 `app.state`）
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_auth_api.py`
- Modify: `docker-compose.yml`（healthcheck URL）

**Interfaces:**
- Cookie 名：`lorechat_session`
- 白名单路径前缀精确匹配：
  - `GET /api/health`
  - `GET /api/auth/status`
  - `POST /api/auth/setup`
  - `POST /api/auth/login`
- Produces JSON：
  - status: `{ "setup_required": bool, "authenticated": bool }`
- 错误体：`{"detail": str, "code": str}`（如 `auth_required`、`setup_required`、`already_setup`、`invalid_password`）

**Consumes:** `AuthStore`, `SessionStore`（A1/A2）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_auth_api.py
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.models.llm import FakeLLMClient


def _raw_client(tmp_path):
    settings = Settings(kb_path=tmp_path / "knowledge")
    app = create_app(settings=settings, llm=FakeLLMClient(embed_dim=8))
    return TestClient(app)


def test_health_public(tmp_path):
    with _raw_client(tmp_path) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_tree_requires_auth(tmp_path):
    with _raw_client(tmp_path) as c:
        r = c.get("/api/tree")
        assert r.status_code == 401
        assert r.json()["code"] == "auth_required"


def test_setup_login_logout_flow(tmp_path):
    with _raw_client(tmp_path) as c:
        st = c.get("/api/auth/status").json()
        assert st["setup_required"] is True
        assert st["authenticated"] is False

        r = c.post("/api/auth/setup", json={"password": "admin-pass-123"})
        assert r.status_code == 200
        assert c.cookies.get("lorechat_session")

        st2 = c.get("/api/auth/status").json()
        assert st2["setup_required"] is False
        assert st2["authenticated"] is True

        assert c.get("/api/tree").status_code == 200

        r2 = c.post("/api/auth/setup", json={"password": "another-pass"})
        assert r2.status_code == 403

        c.post("/api/auth/logout")
        assert c.get("/api/tree").status_code == 401

        bad = c.post("/api/auth/login", json={"password": "wrong-password"})
        assert bad.status_code == 401

        ok = c.post("/api/auth/login", json={"password": "admin-pass-123"})
        assert ok.status_code == 200
        assert c.get("/api/tree").status_code == 200
```

- [ ] **Step 2: 跑失败**

```bash
cd backend
python -m pytest tests/test_auth_api.py -v
```

Expected: FAIL（404/无 middleware）

- [ ] **Step 3: 实现 routes + middleware，并改 main/deps/conftest**

要点（实现时按此契约，勿偏离）：

1. `build_container` 或 lifespan 内创建 `AuthStore(settings.kb_path)`、`SessionStore(settings.kb_path)`，挂到 `app.state.auth_store` / `app.state.session_store`（也可放进 Container）。
2. `AuthMiddleware`：若 path 在白名单则放行；否则读 cookie `lorechat_session`，`session_store.validate` 失败则返回 401 JSON。
3. `POST /api/auth/setup`：`set_password` → `create` session → `Set-Cookie`（httponly, samesite=lax, path=/）。
4. `GET /api/health`：`{"status":"ok"}`，无需登录。
5. CORS：`allow_origins` 改为可配置；默认在无 `CORS_ORIGINS` 时用 `allow_origin_regex` 匹配 localhost，或 Docker 同域时前端不跨域——**最低要求**：`allow_credentials=True`，且不要再 `allow_origins=["*"]` 与 credentials 组合。本地 Vite 开发：设置 `CORS_ORIGINS=http://localhost:5173`（写入 config 可选字段）。
6. `conftest.py` 的 `client` fixture 在 yield 前：

```python
    with TestClient(app) as client:
        r = client.post("/api/auth/setup", json={"password": "test-password-123"})
        assert r.status_code == 200, r.text
        yield client
```

若 `setup_required` 已 false（极少），改为 login。

7. `docker-compose.yml` healthcheck 改为：

```yaml
test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"]
```

`auth/routes.py` 骨架：

```python
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE = "lorechat_session"


@router.get("/status")
def auth_status(request: Request):
    auth = request.app.state.auth_store
    sessions = request.app.state.session_store
    sid = request.cookies.get(COOKIE)
    return {
        "setup_required": auth.is_setup_required(),
        "authenticated": sessions.validate(sid),
    }
# setup / login / logout / change-password 同理
```

中间件伪代码：

```python
PUBLIC = {
    ("GET", "/api/health"),
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/setup"),
    ("POST", "/api/auth/login"),
}

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        key = (request.method, request.url.path)
        if key in PUBLIC or request.url.path == "/api/health":
            return await call_next(request)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        sid = request.cookies.get(COOKIE)
        if not request.app.state.session_store.validate(sid):
            return JSONResponse(
                status_code=401,
                content={"detail": "authentication required", "code": "auth_required"},
            )
        return await call_next(request)
```

注意：中间件必须在 lifespan 之后能读到 `app.state.*`；`TestClient` 会触发 lifespan。把 store 的创建放在 `create_app` 里、挂 middleware 之前即可（不必等 lifespan）：

```python
app.state.auth_store = AuthStore(_settings.kb_path)
app.state.session_store = SessionStore(_settings.kb_path)
```

- [ ] **Step 4: 跑 auth 测试 + 全量 API 冒烟**

```bash
cd backend
python -m pytest tests/test_auth_api.py tests/test_api.py -q
```

Expected: PASS（conftest 已自动登录，既有 API 测试应仍绿）

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth backend/app/main.py backend/app/deps.py backend/tests/conftest.py backend/tests/test_auth_api.py docker-compose.yml
git commit -m "feat(auth): gate /api with session cookie and public health"
```

---

### Task A4: 前端登录 / 设密门禁

**Files:**
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/components/auth/SetupPage.tsx`
- Create: `frontend/src/components/auth/LoginPage.tsx`
- Modify: `frontend/src/App.tsx`
- 样式：复用现有 CSS 变量，可为门页加少量 class

**Interfaces:**
- `apiFetch` / 所有 `fetch`：`credentials: "include"`
- 新增：`getAuthStatus`, `setupAuth`, `login`, `logout`
- `App` 状态：`"loading" | "setup" | "login" | "app"`

- [ ] **Step 1: 改 `apiFetch` 默认带 cookie**

在 `api.ts` 的 `apiFetch` 与所有裸 `fetch`（含 `/api/chat`）加上：

```typescript
credentials: "include",
```

并增加：

```typescript
export type AuthStatus = {
  setup_required: boolean;
  authenticated: boolean;
};

export function getAuthStatus() {
  return apiFetch<AuthStatus>("/api/auth/status");
}

export function setupAuth(password: string) {
  return apiFetch<{ ok: boolean }>("/api/auth/setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
}

export function login(password: string) {
  return apiFetch<{ ok: boolean }>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
}

export function logout() {
  return apiFetch<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
}
```

对 `apiFetch`：若 `r.status === 401`，抛出带标记的错误或派发自定义事件，供 App 切回 login（可选：`throw Object.assign(new Error(...), { status: 401 })`）。

- [ ] **Step 2: SetupPage / LoginPage**

极简表单：密码 + 确认（仅 setup）+ 提交。中文文案：「设置管理员密码」「登录」。密码最少 8 位，前端先校验。

- [ ] **Step 3: App 门禁**

```tsx
// App.tsx 顶部逻辑示意
const [gate, setGate] = useState<"loading" | "setup" | "login" | "app">("loading");

useEffect(() => {
  getAuthStatus()
    .then((s) => {
      if (s.setup_required) setGate("setup");
      else if (!s.authenticated) setGate("login");
      else setGate("app");
    })
    .catch(() => setGate("login"));
}, []);

if (gate === "loading") return null;
if (gate === "setup")
  return <SetupPage onDone={() => setGate("app")} />;
if (gate === "login")
  return <LoginPage onDone={() => setGate("app")} />;
// 原 AppShell ...
```

- [ ] **Step 4: 手动验证**

```bash
# 终端1
cd backend && uvicorn app.main:app --reload --port 8000
# 终端2
cd frontend && npm run dev
```

浏览器：首次打开应设密；刷新应登录；登录后树与聊天可用；登出后 401。

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(auth): add setup/login gate and credentialed API calls"
```

**Phase A 完成标准：** 未登录无法调业务 API；Docker health 用 `/api/health`；前端有完整门禁。

---

# Phase B — 配置热更新

### Task B1: SettingsStore（合并 + 持久化 + 脱敏）

**Files:**
- Create: `backend/app/settings_store.py`
- Test: `backend/tests/test_settings_store.py`
- Modify: `backend/app/config.py`（导出可编辑字段集合）

**Interfaces:**
- Produces:
  - `EDITABLE_SETTING_KEYS: frozenset[str]` — 含模型/密钥/检索等，**不含** `kb_path`
  - `SECRET_SETTING_KEYS: frozenset[str]` — API key 类
  - `class SettingsStore`:
    - `__init__(self, kb_path: Path, base: Settings)`
    - `get(self) -> Settings`  # 当前生效
    - `public_dict(self) -> dict`  # 密钥脱敏
    - `update(self, patch: dict) -> Settings`  # 校验、写 json、返回新 Settings
  - 文件：`{kb_path}/.kb/settings.json`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_settings_store.py
from pathlib import Path
from app.config import Settings
from app.settings_store import SettingsStore, EDITABLE_SETTING_KEYS


def test_kb_path_not_editable():
    assert "kb_path" not in EDITABLE_SETTING_KEYS


def test_load_defaults_then_override(tmp_path: Path):
    base = Settings(kb_path=tmp_path, openai_api_key="sk-base", small_model="m1")
    store = SettingsStore(tmp_path, base)
    assert store.get().small_model == "m1"
    store.update({"small_model": "m2", "openai_api_key": "sk-new-key-xxxx"})
    assert store.get().small_model == "m2"
    assert store.get().openai_api_key == "sk-new-key-xxxx"
    assert (tmp_path / ".kb" / "settings.json").is_file()
    # 重新加载
    store2 = SettingsStore(tmp_path, base)
    assert store2.get().small_model == "m2"


def test_public_dict_masks_secrets(tmp_path: Path):
    base = Settings(kb_path=tmp_path, openai_api_key="sk-abcdefghijklmnop")
    store = SettingsStore(tmp_path, base)
    pub = store.public_dict()
    assert pub["openai_api_key"] != "sk-abcdefghijklmnop"
    assert pub["openai_api_key"].endswith("mnop")
    assert "kb_path" in pub


def test_update_rejects_kb_path(tmp_path: Path):
    base = Settings(kb_path=tmp_path)
    store = SettingsStore(tmp_path, base)
    try:
        store.update({"kb_path": "/tmp/other"})
        assert False, "expected error"
    except ValueError as e:
        assert "kb_path" in str(e).lower() or "not editable" in str(e).lower()


def test_omitted_secret_keeps_previous(tmp_path: Path):
    base = Settings(kb_path=tmp_path, openai_api_key="sk-keep-me-1234")
    store = SettingsStore(tmp_path, base)
    store.update({"openai_api_key": "sk-keep-me-1234"})
    store.update({"small_model": "x", "openai_api_key": ""})  # 空字符串表示保持
    # 约定：空字符串或 "__UNCHANGED__" 表示不改密钥；二选一，实现与测试必须一致
    assert store.get().openai_api_key == "sk-keep-me-1234"
```

**密钥保持约定（锁定）：** PUT 时若密钥字段为 `null`、`""` 或省略，则保持原值；只有非空新字符串才替换。

- [ ] **Step 2: 跑失败 → 实现 → 跑通过**

实现要点：

```python
def _mask(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}***{value[-4:]}"
```

`update`：过滤未知键；拒绝 `kb_path`；对 `Settings` 做一遍 pydantic 校验（构造临时 Settings 或 `model_validate`）；原子写 json。

- [ ] **Step 3: Commit**

```bash
git add backend/app/settings_store.py backend/app/config.py backend/tests/test_settings_store.py
git commit -m "feat(settings): add SettingsStore with masked public view"
```

---

### Task B2: Settings API + 热替换 Container 客户端

**Files:**
- Create: `backend/app/api/admin_routes.py`（先只做 settings；C 阶段再加 export/import）
- Modify: `backend/app/main.py`（include admin router；创建 SettingsStore）
- Modify: `backend/app/deps.py`：增加 `rebuild_llm_clients(container, settings) -> None` 或 `swap_settings(app, new_settings)`
- Test: `backend/tests/test_admin_settings_api.py`

**Interfaces:**
- `GET /api/admin/settings` → `public_dict()`
- `PUT /api/admin/settings` body: partial dict → 更新并热替换
- `POST /api/auth/change-password`（若 A3 未做则本任务补上）
- 热替换：至少替换 `container.settings`、`container.llm`（及依赖 settings 的 search/fetcher 若从 settings 读 key）

- [ ] **Step 1: 写失败测试**

```python
def test_get_and_put_settings(client):
    r = client.get("/api/admin/settings")
    assert r.status_code == 200
    body = r.json()
    assert "kb_path" in body
    assert "small_model" in body

    r2 = client.put("/api/admin/settings", json={"small_model": "hot-model-1"})
    assert r2.status_code == 200
    assert r2.json()["small_model"] == "hot-model-1"

    r3 = client.get("/api/admin/settings")
    assert r3.json()["small_model"] == "hot-model-1"


def test_put_rejects_kb_path(client):
    r = client.put("/api/admin/settings", json={"kb_path": "/x"})
    assert r.status_code == 422
```

- [ ] **Step 2: 实现热替换**

在 `deps.py` 增加：

```python
def apply_settings(container: Container, settings: Settings, llm: LLMClient | None = None) -> None:
    container.settings = settings
    if llm is not None:
        container.llm = llm
    else:
        container.llm = OpenAILLMClient(settings)
    # 若 WebSearch / Agent 缓存了 key，在此同步；否则确保它们每次从 container.settings 读取
```

`PUT` 处理器：

```python
new_settings = store.update(patch)
apply_settings(request.app.state.container, new_settings)
return store.public_dict()
```

检查 `OpenAILLMClient` / `WebSearch` 是否在构造时固化 key：若固化，必须在 `apply_settings` 重建对应对象并写回 container / agent。

- [ ] **Step 3: 跑测试并提交**

```bash
cd backend
python -m pytest tests/test_admin_settings_api.py tests/test_settings_store.py -q
```

```bash
git add backend/app/api/admin_routes.py backend/app/main.py backend/app/deps.py backend/tests/test_admin_settings_api.py
git commit -m "feat(settings): admin settings API with hot client swap"
```

---

### Task B3: 前端设置面板（配置 + 改密）

**Files:**
- Create: `frontend/src/components/settings/SettingsPanel.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`（底部「设置」按钮）
- Modify: `frontend/src/api.ts`（`getSettings`, `putSettings`, `changePassword`）
- Modify: `frontend/src/App.tsx` 或 `AppShell`（控制面板开关）

- [ ] **Step 1: API 封装**

```typescript
export function getSettings() {
  return apiFetch<Record<string, unknown>>("/api/admin/settings");
}

export function putSettings(patch: Record<string, unknown>) {
  return apiFetch<Record<string, unknown>>("/api/admin/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export function changePassword(old_password: string, new_password: string) {
  return apiFetch<{ ok: boolean }>("/api/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_password, new_password }),
  });
}
```

- [ ] **Step 2: SettingsPanel UI**

分组表单（先覆盖高频项即可，其余可进「高级」折叠）：

- 模型：`small_model`, `big_model`, `embed_model` + 各 base_url
- 密钥：`openai_api_key` 等；展示脱敏值；编辑时空输入=不修改
- 检索：`min_vector_score`, `rrf_k`, `lane_candidate_k`
- Agent：`agent_max_tool_calls`, `agent_parallel_tools`, `agent_max_parallel`
- 只读：`kb_path`
- 改密表单

保存调用 `putSettings`；成功 toast 或 inline「已保存并生效」。

- [ ] **Step 3: 侧栏入口**

在 `sidebar-footer` 的 `ThemeToggle` 旁加「设置」按钮，打开面板（drawer 或全屏 overlay，贴合现有 CSS，避免新设计体系）。

- [ ] **Step 4: 手动验证热更新**

改 `small_model` 保存后，不重启后端，发一条聊天，确认请求打到新模型（可用错误的模型名观察快速失败作为信号）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(settings): add settings panel with hot-apply and password change"
```

**Phase B 完成标准：** 设置页可改参数并立即生效；密钥脱敏；`KB_PATH` 不可改。

---

# Phase C — 导出 / 导入

### Task C1: 维护锁 + 空库判定

**Files:**
- Create: `backend/app/backup/lock.py`
- Create: `backend/app/backup/empty.py`
- Test: `backend/tests/test_backup_empty_lock.py`

**Interfaces:**
- `class MaintenanceLock`:
  - `acquire(self, reason: str) -> None`  # 不可重入则 raise `MaintenanceActiveError`
  - `release(self) -> None`
  - `is_active(self) -> bool`
  - `reason(self) -> str | None`
- `is_kb_empty(kb_path: Path, system_layer_dir: str = "系统") -> bool`  
  规则（与 spec 一致）：
  - 若 `conversations.db` 存在且有任意 conversation 行 → 非空
  - 若存在用户 Markdown：`list_tree` 中去掉 `系统/` 前缀后仍有路径 → 非空
  - 若存在 attachments 文件 → 非空
  - 否则空

- [ ] **Step 1: 写测试并实现**

```python
def test_empty_fresh(tmp_path):
    assert is_kb_empty(tmp_path) is True

def test_non_empty_with_doc(tmp_path):
    p = tmp_path / "技术"
    p.mkdir()
    (p / "a.md").write_text("# a\n", encoding="utf-8")
    assert is_kb_empty(tmp_path) is False

def test_lock_blocks_second_acquire():
    lock = MaintenanceLock()
    lock.acquire("export")
    with pytest.raises(MaintenanceActiveError):
        lock.acquire("import")
    lock.release()
    lock.acquire("import")
    lock.release()
```

挂锁到 `app.state.maintenance_lock`。在写路径中间件或依赖中：若 lock active 且 method 会写，返回 503/`code=maintenance`。**最低要求：** chat/ingest/doc PUT/upload/import/export 检查锁；只读 GET tree/doc 在 export 期间可放行（export 用只读快照更佳）。

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(backup): add maintenance lock and empty-kb detection"
```

---

### Task C2: 导出 zip

**Files:**
- Create: `backend/app/backup/manifest.py`
- Create: `backend/app/backup/export_kb.py`
- Modify: `backend/app/api/admin_routes.py`
- Test: `backend/tests/test_backup_export.py`

**Interfaces:**
- `FORMAT_VERSION = 1`
- `build_export_zip(kb_path: Path, dest: Path | BinaryIO) -> None`
- 排除名（目录或文件后缀匹配）：
  - `.kb/index/vec`
  - `fts.db`, `conversation_fts.db`
  - `*.db-wal`, `*.db-shm`（导出前对 sqlite 尽量 `PRAGMA wal_checkpoint(TRUNCATE)`，若可打开）
- `GET /api/admin/export` → `StreamingResponse` / `FileResponse`，`Content-Disposition: attachment; filename="lorechat-kb-YYYYMMDD.zip"`

- [ ] **Step 1: 写失败测试**

```python
import zipfile
from pathlib import Path
from app.backup.export_kb import build_export_zip

def test_export_includes_docs_excludes_index(tmp_path: Path):
    kb = tmp_path / "kb"
    (kb / "技术").mkdir(parents=True)
    (kb / "技术" / "a.md").write_text("# hi\n", encoding="utf-8")
    idx = kb / ".kb" / "index"
    (idx / "vec").mkdir(parents=True)
    (idx / "vec" / "dummy.bin").write_bytes(b"x")
    (idx / "fts.db").write_bytes(b"sqlite")
    (kb / ".kb" / "auth.json").write_text('{"password_hash":"x"}', encoding="utf-8")

    out = tmp_path / "out.zip"
    build_export_zip(kb, out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert any(n.endswith("技术/a.md") or n.endswith("技术\\a.md") for n in names)
    assert any("auth.json" in n for n in names)
    assert any(n.endswith("manifest.json") for n in names)
    assert not any("fts.db" in n for n in names)
    assert not any("/vec/" in n.replace("\\", "/") or n.replace("\\", "/").endswith("/vec") for n in names if "vec" in n)
```

- [ ] **Step 2: 实现并加 API 测试**

```python
def test_export_api_requires_auth_and_returns_zip(client, tmp_path):
    # client 已登录；写入一篇文档可通过 ingest 或直接写 kb
    r = client.get("/api/admin/export")
    assert r.status_code == 200
    assert "zip" in r.headers.get("content-type", "")
```

注意：TestClient 的 kb 在 fixture 的 tmp_path；直接写文件到 `settings.kb_path`。

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(backup): export knowledge base zip without rebuildable indexes"
```

---

### Task C3: 导入（empty_only / overwrite + 备份回滚）

**Files:**
- Create: `backend/app/backup/import_kb.py`
- Modify: `backend/app/api/admin_routes.py`
- Modify: `docker-compose.yml`（可选 volume `/data/backups`）
- Test: `backend/tests/test_backup_import.py`

**Interfaces:**
- `backup_dir_for(kb_path: Path) -> Path`  
  默认：`kb_path.parent / "lorechat-backups"`；可用 env `BACKUP_DIR` 覆盖（Docker 设 `/data/backups`）
- `import_kb(kb_path, zip_path, mode: Literal["empty_only","overwrite"], *, system_layer_dir) -> ImportResult`
- `ImportResult`: `ok`, `backup_path: Path | None`, `message`
- 覆盖流程：
  1. `build_export_zip` 当前库 → backups
  2. 清空 kb_path 内容（保留目录本身）
  3. 解压 zip（校验 manifest `format_version`）
  4. 失败则从 backup 解压回滚
- `POST /api/admin/import`：multipart `file` + form `mode`
- 导入成功后调用 `request.app.state.container` **重建**：关闭旧 DB/Chroma 句柄并 `build_container` 替换（与 settings 热替换类似，但是整容器重建）

- [ ] **Step 1: 写测试**

```python
def test_import_empty_only_rejects_non_empty(tmp_path):
    ...

def test_import_empty_only_ok(tmp_path):
    ...

def test_overwrite_creates_backup_and_replaces(tmp_path):
    ...

def test_overwrite_rollback_on_bad_zip(tmp_path):
    # 备份后解压故意失败 → 原内容恢复
    ...
```

- [ ] **Step 2: 实现容器重建**

```python
def remount_container(app, settings, llm=None):
    app.state.container = build_container(settings, llm=llm)
    app.state.auth_store = AuthStore(settings.kb_path)
    app.state.session_store = SessionStore(settings.kb_path)
    app.state.settings_store = SettingsStore(settings.kb_path, settings)
```

导入后会话 cookie 仍有效（sessions.json 若在包内被覆盖，以包内为准——与「密码随库迁移」一致）。

- [ ] **Step 3: API 测试 + Commit**

```bash
git commit -m "feat(backup): import with empty_only and overwrite-with-backup"
```

---

### Task C4: 重建索引 + 前端导入导出 UI

**Files:**
- Create: `backend/app/backup/reindex.py`
- Modify: `backend/app/api/admin_routes.py` — `POST /api/admin/reindex`
- Modify: `frontend/src/components/settings/SettingsPanel.tsx` — 导出按钮、导入（mode 单选 + 覆盖确认）、重建索引
- Modify: `frontend/src/api.ts`
- Test: `backend/tests/test_backup_reindex.py`

**Interfaces:**
- `reindex_all(container) -> dict` 统计：`docs_indexed`, `conversations_fts`, `conversations_vector`（vector 可先标记 skipped 若太重，但 spec 要求可重建——应调用现有 indexer + conversation_backfill 入口）
- 文档：遍历 `repo.list_tree()`，读正文，`indexer.reindex_doc`
- 会话：调用 `app.engine.conversation_backfill` 中已有函数（抽出 `backfill_fts` / `backfill_vectors` 若尚不可 import）

- [ ] **Step 1: 后端 reindex 测试**

导入一个不含 index 的 zip 后，`POST /api/admin/reindex` 返回 200，且随后检索不再空（可用 ingest+ask 或直接查 FTS）。

- [ ] **Step 2: 前端**

- 「导出知识库」：`window.location` 或 `fetch` blob 下载 `/api/admin/export`
- 「导入」：`<input type="file">` + radio `empty_only` / `overwrite`；选 overwrite 时二次确认文案：「将先自动备份现有知识库，再覆盖。确定？」
- 「重建索引」按钮
- 导入/导出中禁用聊天输入（可选：听维护错误提示）

导出下载示例：

```typescript
export async function downloadExport() {
  const r = await fetch(`${BASE}/api/admin/export`, { credentials: "include" });
  if (!r.ok) throw new Error("导出失败");
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `lorechat-kb.zip`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function importKb(file: File, mode: "empty_only" | "overwrite") {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("mode", mode);
  const r = await fetch(`${BASE}/api/admin/import`, {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  if (!r.ok) { /* parse error */ throw new Error(...); }
  return r.json();
}
```

- [ ] **Step 3: Docker backups（可选但推荐）**

```yaml
# docker-compose.yml
environment:
  KB_PATH: /data/knowledge
  BACKUP_DIR: /data/backups
volumes:
  - knowledge-data:/data/knowledge
  - backup-data:/data/backups
```

- [ ] **Step 4: 全量回归**

```bash
cd backend
python -m pytest tests/test_auth_api.py tests/test_admin_settings_api.py tests/test_backup_export.py tests/test_backup_import.py tests/test_backup_reindex.py tests/test_api.py -q
```

- [ ] **Step 5: Commit**

```bash
git add backend frontend docker-compose.yml
git commit -m "feat(backup): reindex API and settings UI for export/import"
```

**Phase C 完成标准：** 导出包无索引；空库导入成功；覆盖先备份；重建后可检索。

---

## 实施后自检清单（对照 spec）

| Spec 要求 | Task |
|-----------|------|
| 首次设密引导 | A3, A4 |
| Cookie session 拦全部 API（含 SSE） | A3, A4 |
| `/api/health` 公开放行 | A3 |
| CORS 收紧 + credentials | A3 |
| settings.json 热更新，不含 kb_path | B1, B2, B3 |
| 密钥脱敏与空值保持 | B1, B3 |
| 导出含不可重建 .kb，排除 vec/fts | C2 |
| empty_only + overwrite | C3 |
| 覆盖前自动备份、失败回滚 | C3 |
| 导入后重建索引 | C4 |
| 改密 | A3 或 B2/B3 |

---

## 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-07-16-deploy-auth-backup-settings.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每任务开新子代理，任务间评审，迭代快  
2. **Inline Execution** — 本会话用 executing-plans 按任务推进，设检查点  

选哪种？
