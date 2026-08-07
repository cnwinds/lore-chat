from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from openai import OpenAI

from app.config import Settings
from app.logging_config import get_logger

_log = get_logger("llm")

# 延迟类型，避免循环导入
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.usage.recorder import UsageRecorder



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
    """流式增量：text_delta / think_delta 为逐块文字；final 轮携带完整 result（含 tool_calls）。"""

    text_delta: str | None = None
    think_delta: str | None = None
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


def _delta_reasoning(delta: Any) -> str | None:
    rc = getattr(delta, "reasoning_content", None)
    if isinstance(rc, str) and rc:
        return rc
    return None


class OpenAILLMClient:
    def __init__(
        self,
        settings: Settings,
        usage_recorder: "UsageRecorder | None" = None,
    ):
        self.settings = settings
        self.usage_recorder = usage_recorder
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

    def _record(self, **kwargs) -> None:
        if self.usage_recorder is None:
            return
        try:
            self.usage_recorder.record(**kwargs)
        except Exception:
            _log.exception("usage record failed")

    @staticmethod
    def _usage_from_resp(resp: Any) -> tuple[int | None, int | None, int | None, bool]:
        usage = getattr(resp, "usage", None)
        if usage is None:
            return None, None, None, False
        pt = getattr(usage, "prompt_tokens", None)
        ct = getattr(usage, "completion_tokens", None)
        tt = getattr(usage, "total_tokens", None)
        known = pt is not None or ct is not None or tt is not None
        return pt, ct, tt, known

    def chat(self, messages: list[dict], *, big: bool = False, temperature: float = 0.2) -> str:
        client = self._big if big else self._small
        model = self.settings.big_model if big else self.settings.small_model
        role = "big" if big else "small"
        t0 = time.monotonic()
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, temperature=temperature
            )
        except BaseException as e:
            self._record(
                model=model,
                kind="chat",
                role=role,
                status="error",
                error=str(e),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
            raise
        pt, ct, tt, known = self._usage_from_resp(resp)
        self._record(
            model=model,
            kind="chat",
            role=role,
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=tt,
            tokens_known=known,
            status="ok",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
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
        role = "big" if big else "small"
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            kwargs["tools"] = tools
        t0 = time.monotonic()
        try:
            resp = client.chat.completions.create(**kwargs)
        except BaseException as e:
            self._record(
                model=model,
                kind="chat_tools",
                role=role,
                status="error",
                error=str(e),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
            raise
        pt, ct, tt, known = self._usage_from_resp(resp)
        self._record(
            model=model,
            kind="chat_tools",
            role=role,
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=tt,
            tokens_known=known,
            status="ok",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
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
        role = "big" if big else "small"
        stream_id = uuid.uuid4().hex[:8]
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools

        _log.info(
            "llm stream start id=%s model=%s big=%s messages=%d tools=%d",
            stream_id,
            model,
            big,
            len(messages),
            len(tools),
        )
        t0 = time.monotonic()
        chunk_count = 0
        content_chars = 0
        think_chars = 0
        tool_delta_count = 0
        finish_reason: str | None = None
        content_parts: list[str] = []
        think_parts: list[str] = []
        tc_acc: dict[int, dict[str, Any]] = {}
        usage_prompt: int | None = None
        usage_completion: int | None = None
        usage_total: int | None = None
        usage_known = False

        try:
            try:
                stream = client.chat.completions.create(**kwargs)
            except Exception as e:
                # 部分网关不支持 stream_options；去掉后重试以保可用性
                if "stream_options" in kwargs:
                    _log.warning(
                        "llm stream include_usage unsupported id=%s model=%s err=%s; retry without",
                        stream_id,
                        model,
                        e,
                    )
                    kwargs.pop("stream_options", None)
                    stream = client.chat.completions.create(**kwargs)
                else:
                    raise
            for chunk in stream:
                chunk_count += 1
                u = getattr(chunk, "usage", None)
                if u is not None:
                    usage_prompt = getattr(u, "prompt_tokens", usage_prompt)
                    usage_completion = getattr(u, "completion_tokens", usage_completion)
                    usage_total = getattr(u, "total_tokens", usage_total)
                    usage_known = (
                        usage_prompt is not None
                        or usage_completion is not None
                        or usage_total is not None
                    )
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta
                reasoning = _delta_reasoning(delta)
                if reasoning:
                    think_parts.append(reasoning)
                    think_chars += len(reasoning)
                    yield ChatStreamChunk(think_delta=reasoning)
                if delta.content:
                    content_parts.append(delta.content)
                    content_chars += len(delta.content)
                    yield ChatStreamChunk(text_delta=delta.content)
                for tcd in delta.tool_calls or []:
                    tool_delta_count += 1
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
        except BaseException as e:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            _log.error(
                "llm stream error id=%s model=%s ms=%d chunks=%d content_chars=%d "
                "think_chars=%d tool_deltas=%d partial_tc_slots=%d err=%s",
                stream_id,
                model,
                elapsed_ms,
                chunk_count,
                content_chars,
                think_chars,
                tool_delta_count,
                len(tc_acc),
                e,
                exc_info=True,
            )
            self._record(
                model=model,
                kind="stream_tools",
                role=role,
                prompt_tokens=usage_prompt,
                completion_tokens=usage_completion,
                total_tokens=usage_total,
                tokens_known=usage_known,
                status="error",
                error=str(e),
                duration_ms=elapsed_ms,
            )
            raise

        elapsed_ms = int((time.monotonic() - t0) * 1000)

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

        partial_tc = sum(1 for s in tc_acc.values() if not s.get("name"))
        tool_names = [tc.name for tc in tool_calls]
        content = "".join(content_parts) or None
        think_text = "".join(think_parts) or None

        _log.info(
            "llm stream end id=%s model=%s ms=%d chunks=%d content_chars=%d think_chars=%d "
            "tool_deltas=%d tool_calls=%d tool_names=%s finish_reason=%s partial_tc_slots=%d "
            "usage_known=%s prompt_tokens=%s completion_tokens=%s",
            stream_id,
            model,
            elapsed_ms,
            chunk_count,
            content_chars,
            think_chars,
            tool_delta_count,
            len(tool_calls),
            tool_names,
            finish_reason,
            partial_tc,
            usage_known,
            usage_prompt,
            usage_completion,
        )
        if think_text and _log.isEnabledFor(10):  # DEBUG: 完整思考摘要
            preview = think_text[:500] + ("…" if len(think_text) > 500 else "")
            _log.debug("llm stream id=%s think_preview=%r", stream_id, preview)
        if content and _log.isEnabledFor(10):
            preview = (content or "")[:500] + ("…" if len(content or "") > 500 else "")
            _log.debug("llm stream id=%s content_preview=%r", stream_id, preview)

        if tc_acc and not tool_calls:
            _log.warning(
                "llm stream id=%s model=%s truncated tool_calls slots=%s",
                stream_id,
                model,
                {k: {"id": v["id"], "name": v["name"], "args_len": len(v["arguments"] or "")} for k, v in tc_acc.items()},
            )
        if not content and not tool_calls and think_chars > 0:
            _log.warning(
                "llm stream id=%s model=%s think-only round (no content/tool_calls)",
                stream_id,
                model,
            )
        if not content and not tool_calls and think_chars == 0:
            _log.warning(
                "llm stream id=%s model=%s completely empty result finish_reason=%s",
                stream_id,
                model,
                finish_reason,
            )

        self._record(
            model=model,
            kind="stream_tools",
            role=role,
            prompt_tokens=usage_prompt,
            completion_tokens=usage_completion,
            total_tokens=usage_total,
            tokens_known=usage_known,
            status="ok",
            duration_ms=elapsed_ms,
        )

        yield ChatStreamChunk(
            result=ChatWithToolsResult(content=content, tool_calls=tool_calls)
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self.settings.embed_model
        batch_size = 10
        out: list[list[float]] = []
        t0 = time.monotonic()
        prompt_tokens = 0
        total_tokens = 0
        any_known = False
        try:
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                resp = self._embed.embeddings.create(model=model, input=batch)
                out.extend(d.embedding for d in resp.data)
                pt, _, tt, known = self._usage_from_resp(resp)
                if known:
                    any_known = True
                    if pt is not None:
                        prompt_tokens += pt
                    if tt is not None:
                        total_tokens += tt
                    elif pt is not None:
                        total_tokens += pt
        except BaseException as e:
            self._record(
                model=model,
                kind="embed",
                role="embed",
                status="error",
                error=str(e),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
            raise
        self._record(
            model=model,
            kind="embed",
            role="embed",
            prompt_tokens=prompt_tokens if any_known else None,
            completion_tokens=None,
            total_tokens=total_tokens if any_known else None,
            tokens_known=any_known,
            status="ok",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
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
