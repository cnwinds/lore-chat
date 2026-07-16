import json

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.llm import ChatWithToolsResult, FakeLLMClient, ToolCall


def _build_tool_responses() -> list[dict]:
    responses: list[dict] = []
    for i in range(20):
        responses.append(
            {
                "content": None,
                "tool_calls": [
                    ToolCall(id=f"w{i}", name="write_kb", arguments={"text": ""})
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
            if tc.name == "write_kb" and not args.get("text"):
                args["text"] = user_text
            elif tc.name == "search_kb" and not args.get("query"):
                args["query"] = user_text
            patched.append(ToolCall(id=tc.id, name=tc.name, arguments=args))
        return ChatWithToolsResult(content=result.content, tool_calls=patched)


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
