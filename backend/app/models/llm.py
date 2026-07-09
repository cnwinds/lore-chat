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
