"""共享夹具。顶部的导入期钩子必须先于应用打开数据库与 git：测试里关掉落盘同步、调低 bcrypt 强度。"""

import os
import sys


def _append_git_config(key: str, value: str) -> None:
    count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
    os.environ[f"GIT_CONFIG_KEY_{count}"] = key
    os.environ[f"GIT_CONFIG_VALUE_{count}"] = value
    os.environ["GIT_CONFIG_COUNT"] = str(count + 1)


_append_git_config("core.fsync", "none")


def _wrap_sqlite_connect(module) -> None:
    if getattr(module, "_lorechat_test_connect_wrapped", False):
        return
    orig_connect = module.connect

    def connect(*args, **kwargs):
        conn = orig_connect(*args, **kwargs)
        conn.execute("PRAGMA synchronous=OFF")
        return conn

    module.connect = connect  # type: ignore[method-assign]
    module._lorechat_test_connect_wrapped = True


import sqlite3 as _stdlib_sqlite3  # noqa: E402

_wrap_sqlite_connect(_stdlib_sqlite3)

import app.sqlite_compat  # noqa: E402, F401

_wrap_sqlite_connect(sys.modules["sqlite3"])

try:
    import pysqlite3.dbapi2 as _pysqlite3_dbapi2

    _wrap_sqlite_connect(_pysqlite3_dbapi2)
    if "pysqlite3" in sys.modules:
        _wrap_sqlite_connect(sys.modules["pysqlite3"])
except ImportError:
    pass

from app.auth import passwords as _passwords  # noqa: E402

_passwords.BCRYPT_ROUNDS = 4

import json  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.models.llm import ChatWithToolsResult, FakeLLMClient, ToolCall  # noqa: E402


def _build_tool_responses() -> list[dict]:
    responses: list[dict] = []
    for i in range(20):
        responses.append(
            {
                "content": None,
                "tool_calls": [
                    ToolCall(
                        id=f"w{i}",
                        name="write_doc",
                        arguments={
                            "text": "",
                            "directory": "未分类",
                            "filename": "ingest.md",
                        },
                    )
                ],
            }
        )
        responses.append({"content": "已录入知识库", "tool_calls": []})
        responses.append(
            {
                "content": None,
                "tool_calls": [
                    ToolCall(id=f"s{i}", name="search_kb", arguments={"query": ""})
                ],
            }
        )
        responses.append({"content": "docker 用于容器管理", "tool_calls": []})
    return responses


class AgentFakeLLM(FakeLLMClient):
    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> ChatWithToolsResult:
        result = super().chat_with_tools(
            messages, tools, big=big, temperature=temperature
        )
        user_text = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )
        if not result.tool_calls:
            return result
        patched: list[ToolCall] = []
        for tc in result.tool_calls:
            args = dict(tc.arguments)
            if tc.name == "write_doc" and not args.get("text"):
                args["text"] = user_text
            if tc.name == "write_doc":
                if "directory" not in args:
                    args["directory"] = "未分类"
                if "filename" not in args:
                    args["filename"] = "ingest.md"
            elif tc.name == "search_kb" and not args.get("query"):
                args["query"] = user_text
            patched.append(ToolCall(id=tc.id, name=tc.name, arguments=args))
        return ChatWithToolsResult(content=result.content, tool_calls=patched)


@pytest.fixture(autouse=True)
def _clear_path_keyed_stores():
    """按知识库路径缓存的单例每个测试后清空，否则每个 tmp_path 都会常驻内存。"""
    yield
    from app.models import cooldown, models_dev

    models_dev._SHARED.clear()
    cooldown._SHARED.clear()


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.config import Settings

    settings = Settings(kb_path=tmp_path / "knowledge")
    fake_decision = json.dumps(
        {
            "action": "new",
            "rel_path": "技术/note.md",
            "title": "笔记",
            "category": "技术",
            "tags": ["t"],
            "ambiguous": False,
            "reason": "全新",
        }
    )
    llm = AgentFakeLLM(
        chat_responses=["摘要", fake_decision] * 20,
        tool_responses=_build_tool_responses(),
        embed_dim=8,
    )
    app = create_app(settings=settings, llm=llm)
    with TestClient(app) as client:
        r = client.post("/api/auth/setup", json={"password": "test-password-123"})
        assert r.status_code == 200, r.text
        yield client
