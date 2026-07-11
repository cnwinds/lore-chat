from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from openai import OpenAI

from app.config import Settings


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatWithToolsResult:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ChatStreamChunk:
    """流式增量：text_delta 为逐块文字；final 轮携带完整 result（含 tool_calls）。"""

    text_delta: str | None = None
    result: ChatWithToolsResult | None = None


@runtime_checkable
class LLMClient(Protocol):
    def chat(self, messages: list[dict], *, big: bool = False, temperature: float = 0.2) -> str: ...
    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> ChatWithToolsResult: ...
    def stream_chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> Iterator[ChatStreamChunk]: ...
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

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> ChatWithToolsResult:
        client = self._big if big else self._small
        model = self.settings.big_model if big else self.settings.small_model
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            kwargs["tools"] = tools
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments or "{}"),
                    )
                )
        return ChatWithToolsResult(content=msg.content, tool_calls=tool_calls)

    def stream_chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> Iterator[ChatStreamChunk]:
        client = self._big if big else self._small
        model = self.settings.big_model if big else self.settings.small_model
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        stream = client.chat.completions.create(**kwargs)

        content_parts: list[str] = []
        # 按 index 跨块累积 tool_calls（OpenAI 流式把 name/arguments 分片发送）
        tc_acc: dict[int, dict[str, Any]] = {}
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content_parts.append(delta.content)
                yield ChatStreamChunk(text_delta=delta.content)
            for tcd in delta.tool_calls or []:
                slot = tc_acc.setdefault(
                    tcd.index, {"id": None, "name": None, "arguments": ""}
                )
                if tcd.id:
                    slot["id"] = tcd.id
                if tcd.function:
                    if tcd.function.name:
                        slot["name"] = tcd.function.name
                    if tcd.function.arguments:
                        slot["arguments"] += tcd.function.arguments

        tool_calls: list[ToolCall] = []
        for idx in sorted(tc_acc):
            slot = tc_acc[idx]
            if not slot["name"]:
                continue
            try:
                args = json.loads(slot["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCall(id=slot["id"] or f"call_{idx}", name=slot["name"], arguments=args)
            )
        content = "".join(content_parts) or None
        yield ChatStreamChunk(
            result=ChatWithToolsResult(content=content, tool_calls=tool_calls)
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # DashScope text-embedding 等接口单次 batch 上限通常为 10
        batch_size = 10
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = self._embed.embeddings.create(
                model=self.settings.embed_model, input=batch
            )
            out.extend(d.embedding for d in resp.data)
        return out


class FakeLLMClient:
    """测试用：脚本化 chat 返回；embed 基于哈希产生确定性向量。"""

    def __init__(
        self,
        chat_responses: list[str] | None = None,
        tool_responses: list[dict] | None = None,
        embed_dim: int = 16,
    ):
        self.chat_responses = list(chat_responses or [])
        self.tool_responses = list(tool_responses or [])
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

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> ChatWithToolsResult:
        self.calls.append({"messages": messages, "big": big, "tools": tools})
        if self._i < len(self.tool_responses):
            entry = self.tool_responses[self._i]
            self._i += 1
            return ChatWithToolsResult(
                content=entry.get("content"),
                tool_calls=list(entry.get("tool_calls") or []),
            )
        return ChatWithToolsResult(content="", tool_calls=[])

    def stream_chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> Iterator[ChatStreamChunk]:
        # 委托给 chat_with_tools，使子类（如 AgentFakeLLM）对其的重写依旧生效
        result = self.chat_with_tools(messages, tools, big=big, temperature=temperature)
        if result.content:
            yield ChatStreamChunk(text_delta=result.content)
        yield ChatStreamChunk(result=result)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            vec = [((h[i % len(h)] / 255.0) * 2 - 1) for i in range(self.embed_dim)]
            vecs.append(vec)
        return vecs
