from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from openai import OpenAI

from app.config import Settings
from app.logging_config import get_logger
from app.models.candidate import ModelCandidate, ModelChain
from app.models.cooldown import CooldownStore, classify_error, shared_cooldown_store
from app.models.router import NoCandidateAvailable, Selection, select_candidate
from app.models.thinking import thinking_request_kwargs
from app.models.vision import (
    attachment_signing_secret,
    build_user_content_with_images,
    is_image_file,
    is_image_path,
)

_log = get_logger("llm")

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
    model_name: str | None = None
    candidate_id: str | None = None
    failover: bool | None = None
    skipped: list[tuple[str, str]] | None = None


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


def _chain_from_big(big: bool) -> ModelChain:
    """兼容旧 API：`big=True` → chat 链，`big=False` → utility 链。"""
    return "chat" if big else "utility"


def _messages_need_image(messages: list[dict], *, kb_path: Path | None = None) -> bool:
    root = Path(kb_path) if kb_path is not None else None
    for m in messages:
        atts = m.get("attachments")
        if isinstance(atts, list):
            for p in atts:
                if not isinstance(p, str):
                    continue
                if root is not None:
                    abs_p = (root / p).resolve()
                    if abs_p.is_file() and is_image_file(abs_p):
                        return True
                if is_image_path(p):
                    return True
        content = m.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


class OpenAILLMClient:
    def __init__(
        self,
        settings: Settings,
        usage_recorder: "UsageRecorder | None" = None,
        cooldown: CooldownStore | None = None,
    ):
        self.settings = settings
        self.usage_recorder = usage_recorder
        kb = Path(settings.kb_path)
        from app.models.cooldown import cooldown_path_for_kb

        # 同 kb 路径共用 store，禁止旁路另起内存实例
        self.cooldown = cooldown or shared_cooldown_store(cooldown_path_for_kb(kb))
        self.last_selection: Selection | None = None
        self._embed = OpenAI(
            api_key=settings.embed_api_key or settings.openai_api_key,
            base_url=settings.embed_base_url or settings.openai_base_url,
        )
        self._client_cache: dict[tuple[str, str], OpenAI] = {}

    def rebind_settings(self, settings: Settings) -> None:
        """热更新 settings，保留同一 CooldownStore。"""
        self.settings = settings
        self._embed = OpenAI(
            api_key=settings.embed_api_key or settings.openai_api_key,
            base_url=settings.embed_base_url or settings.openai_base_url,
        )
        self._client_cache.clear()

    def _client_for(self, candidate: ModelCandidate) -> OpenAI:
        base = (candidate.base_url or self.settings.openai_base_url or "").rstrip("/")
        key = candidate.api_key or self.settings.openai_api_key
        cache_key = (base, key or "")
        client = self._client_cache.get(cache_key)
        if client is None:
            client = OpenAI(api_key=key, base_url=base)
            self._client_cache[cache_key] = client
        return client

    def _record(self, **kwargs) -> None:
        if self.usage_recorder is None:
            return
        try:
            self.usage_recorder.record(**kwargs)
        except Exception:
            _log.exception("usage record failed")

    @staticmethod
    def _cached_tokens_from_usage(usage: Any) -> int | None:
        from app.engine.usage.normalize import cached_tokens_from_usage

        return cached_tokens_from_usage(usage)

    @staticmethod
    def _usage_from_resp(
        resp: Any,
    ) -> tuple[int | None, int | None, int | None, int | None, bool]:
        from app.engine.usage.normalize import usage_from_resp

        return usage_from_resp(resp)

    def _signing_secret(self) -> str:
        return attachment_signing_secret(self.settings)

    def _materialize(self, messages: list[dict], candidate: ModelCandidate) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            msg = dict(m)
            attachments = msg.pop("attachments", None)
            if msg.get("role") == "user" and attachments:
                text = msg.get("content")
                if not isinstance(text, str):
                    text = str(text or "")
                msg["content"] = build_user_content_with_images(
                    text,
                    list(attachments),
                    candidate=candidate,
                    kb_path=Path(self.settings.kb_path),
                    public_base_url=self.settings.public_base_url,
                    signing_secret=self._signing_secret(),
                )
            out.append(msg)
        return out

    def _select(
        self,
        *,
        big: bool,
        messages: list[dict],
        exclude_ids: set[str] | None = None,
    ) -> Selection:
        chain = _chain_from_big(big)
        require_image = _messages_need_image(
            messages, kb_path=Path(self.settings.kb_path)
        )
        sel = select_candidate(
            self.settings,
            chain,
            self.cooldown,
            require_image=require_image,
            exclude_ids=exclude_ids,
        )
        self.last_selection = sel
        return sel

    def _next_after_failure(
        self,
        *,
        failed_id: str,
        exc: BaseException,
        attempted: set[str],
    ) -> None:
        """记录失败并加入本轮排除集；下次 _select 须带 exclude_ids=attempted。"""
        self.cooldown.record_failure(failed_id, classify_error(exc), error=str(exc))
        attempted.add(failed_id)

    def chat(self, messages: list[dict], *, big: bool = False, temperature: float = 0.2) -> str:
        chain = _chain_from_big(big)
        role = chain
        attempted: set[str] = set()
        last_exc: BaseException | None = None
        while True:
            try:
                sel = self._select(big=big, messages=messages, exclude_ids=attempted)
            except NoCandidateAvailable:
                if last_exc:
                    raise last_exc
                raise
            cand = sel.candidate
            client = self._client_for(cand)
            model = cand.model
            api_messages = self._materialize(messages, cand)
            t0 = time.monotonic()
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": api_messages,
                "temperature": temperature,
            }
            kwargs.update(thinking_request_kwargs(cand, enable=cand.thinking))
            try:
                resp = client.chat.completions.create(**kwargs)
            except BaseException as e:
                last_exc = e
                self._record(
                    model=model,
                    kind="chat",
                    role=role,
                    status="error",
                    error=str(e),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
                self._next_after_failure(failed_id=cand.id, exc=e, attempted=attempted)
                continue
            self.cooldown.record_success(cand.id)
            pt, ct, tt, cache, known = self._usage_from_resp(resp)
            self._record(
                model=model,
                kind="chat",
                role=role,
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=tt,
                cache_tokens=cache,
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
        chain = _chain_from_big(big)
        role = chain
        attempted: set[str] = set()
        last_exc: BaseException | None = None
        while True:
            try:
                sel = self._select(big=big, messages=messages, exclude_ids=attempted)
            except NoCandidateAvailable:
                if last_exc:
                    raise last_exc
                raise
            cand = sel.candidate
            client = self._client_for(cand)
            model = cand.model
            api_messages = self._materialize(messages, cand)
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": api_messages,
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools
            kwargs.update(thinking_request_kwargs(cand, enable=cand.thinking))
            t0 = time.monotonic()
            try:
                resp = client.chat.completions.create(**kwargs)
            except BaseException as e:
                last_exc = e
                self._record(
                    model=model,
                    kind="chat_tools",
                    role=role,
                    status="error",
                    error=str(e),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
                self._next_after_failure(failed_id=cand.id, exc=e, attempted=attempted)
                continue
            self.cooldown.record_success(cand.id)
            pt, ct, tt, cache, known = self._usage_from_resp(resp)
            self._record(
                model=model,
                kind="chat_tools",
                role=role,
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=tt,
                cache_tokens=cache,
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
        chain = _chain_from_big(big)
        role = chain
        attempted: set[str] = set()
        last_exc: BaseException | None = None

        while True:
            try:
                sel = self._select(big=big, messages=messages, exclude_ids=attempted)
            except NoCandidateAvailable:
                if last_exc:
                    raise last_exc
                raise
            cand = sel.candidate

            yield ChatStreamChunk(
                model_name=cand.model,
                candidate_id=cand.id,
                failover=sel.failover,
                skipped=list(sel.skipped),
            )

            client = self._client_for(cand)
            model = cand.model
            api_messages = self._materialize(messages, cand)
            stream_id = uuid.uuid4().hex[:8]
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": api_messages,
                "temperature": temperature,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if tools:
                kwargs["tools"] = tools
            kwargs.update(thinking_request_kwargs(cand, enable=cand.thinking))

            _log.info(
                "llm stream start id=%s model=%s chain=%s messages=%d tools=%d failover=%s",
                stream_id,
                model,
                chain,
                len(messages),
                len(tools),
                sel.failover,
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
            usage_cache: int | None = None
            usage_known = False
            produced_output = False

            try:
                try:
                    stream = client.chat.completions.create(**kwargs)
                except TypeError as e:
                    # 仅当确为 stream_options 不被接受时剥掉重试；其它 TypeError 原样抛出
                    err = str(e)
                    if "stream_options" in kwargs and "stream_options" in err:
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
                except Exception as e:
                    err = str(e)
                    if "stream_options" in kwargs and (
                        "stream_options" in err or "include_usage" in err
                    ):
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
                        cached = self._cached_tokens_from_usage(u)
                        if cached is not None:
                            usage_cache = cached
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
                        produced_output = True
                        think_parts.append(reasoning)
                        think_chars += len(reasoning)
                        yield ChatStreamChunk(think_delta=reasoning)
                    if delta.content:
                        produced_output = True
                        content_parts.append(delta.content)
                        content_chars += len(delta.content)
                        yield ChatStreamChunk(text_delta=delta.content)
                    for tcd in delta.tool_calls or []:
                        produced_output = True
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
                    "llm stream error id=%s model=%s ms=%d chunks=%d err=%s",
                    stream_id,
                    model,
                    elapsed_ms,
                    chunk_count,
                    e,
                    exc_info=True,
                )
                self._record(
                    model=model,
                    kind="stream_tools",
                    role=role,
                    status="error",
                    error=str(e),
                    duration_ms=elapsed_ms,
                )
                last_exc = e
                if produced_output:
                    self.cooldown.record_failure(cand.id, classify_error(e), error=str(e))
                    raise
                self._next_after_failure(failed_id=cand.id, exc=e, attempted=attempted)
                continue

            self.cooldown.record_success(cand.id)
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
            content = "".join(content_parts) or None
            if tc_acc and not tool_calls:
                _log.warning(
                    "llm stream id=%s model=%s truncated tool_calls slots=%s",
                    stream_id,
                    model,
                    {
                        k: {
                            "id": v["id"],
                            "name": v["name"],
                            "args_len": len(v["arguments"] or ""),
                        }
                        for k, v in tc_acc.items()
                    },
                )
            _log.info(
                "llm stream end id=%s model=%s ms=%d chunks=%d content_chars=%d "
                "think_chars=%d tool_calls=%d finish_reason=%s",
                stream_id,
                model,
                elapsed_ms,
                chunk_count,
                content_chars,
                think_chars,
                len(tool_calls),
                finish_reason,
            )
            self._record(
                model=model,
                kind="stream_tools",
                role=role,
                prompt_tokens=usage_prompt,
                completion_tokens=usage_completion,
                total_tokens=usage_total,
                cache_tokens=usage_cache,
                tokens_known=usage_known,
                status="ok",
                duration_ms=elapsed_ms,
            )
            yield ChatStreamChunk(
                result=ChatWithToolsResult(content=content, tool_calls=tool_calls),
                model_name=model,
                candidate_id=cand.id,
                failover=sel.failover,
            )
            return

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
                pt, _, tt, _, known = self._usage_from_resp(resp)
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
        self.last_selection = None

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
